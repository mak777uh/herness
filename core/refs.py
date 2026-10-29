"""refs — справочник: репозитории портфеля и внешние источники.

Принцип P20: состояние читается из первоисточника, а не из памяти.
Синхронизация тянет ключевые документы в локальный кэш с дайджестом; поиск идёт по кэшу,
поэтому работает без сети и воспроизводимо.

Два вида источников:
  - репозитории владельца (portfolio.json, все документы из общего списка);
  - внешние (sources.json): github-репозиторий или произвольный URL.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "refs-cache"
PORTFOLIO = ROOT / "portfolio.json"
SOURCES = ROOT / "sources.json"
INDEX = CACHE / "index.json"
RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
TOKEN = re.compile(r"[\w\-]+", re.UNICODE)
TAG = re.compile(r"<[^>]+>")
SCRIPT = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_portfolio() -> dict:
    return _load(PORTFOLIO, {"owner": "mak777uh", "docs": [], "repos": []})


def load_sources() -> list[dict]:
    data = _load(SOURCES, {"sources": []})
    return data.get("sources", [])


def save_sources(items: list[dict]) -> None:
    _save(SOURCES, {"sources": items})


def load_index() -> dict:
    return _load(INDEX, {})


def save_index(index: dict) -> None:
    _save(INDEX, index)


def _fetch(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "harness-refs/0.2"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def html_to_text(raw: bytes) -> str:
    """Грубое, но предсказуемое превращение страницы в текст для поиска."""
    text = raw.decode("utf-8", errors="ignore")
    text = SCRIPT.sub(" ", text)
    text = TAG.sub(" ", text)
    text = unescape(text)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()


def _save_doc(src_id: str, doc: str, body: bytes) -> int:
    dest = CACHE / src_id / doc
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    index = load_index()
    index.setdefault(src_id, {})[doc] = {
        "sha": hashlib.sha256(body).hexdigest()[:16],
        "bytes": len(body),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    save_index(index)
    return len(body)


def sync(only: list[str] | None = None) -> dict:
    pf = load_portfolio()
    stats = {"fetched": 0, "missing": 0, "failed": 0, "bytes": 0}

    for repo in pf["repos"]:
        name = repo["name"]
        if only and name not in only:
            continue
        for doc in list(pf["docs"]) + list(repo.get("docs", [])):
            url = RAW.format(owner=pf["owner"], repo=name, branch=repo.get("branch", "main"), path=doc)
            try:
                body = _fetch(url)
            except urllib.error.HTTPError as exc:
                stats["missing" if exc.code == 404 else "failed"] += 1
                continue
            except (urllib.error.URLError, TimeoutError, OSError):
                stats["failed"] += 1
                continue
            stats["bytes"] += _save_doc(name, doc, body)
            stats["fetched"] += 1

    for src in load_sources():
        src_id = src["id"]
        if only and src_id not in only:
            continue
        if src.get("kind") == "github":
            for doc in src.get("docs", ["README.md"]):
                url = RAW.format(owner=src["owner"], repo=src["repo"], branch=src.get("branch", "main"), path=doc)
                try:
                    body = _fetch(url)
                except urllib.error.HTTPError as exc:
                    stats["missing" if exc.code == 404 else "failed"] += 1
                    continue
                except (urllib.error.URLError, TimeoutError, OSError):
                    stats["failed"] += 1
                    continue
                stats["bytes"] += _save_doc(src_id, doc, body)
                stats["fetched"] += 1
        elif src.get("kind") == "url":
            try:
                body = _fetch(src["url"], timeout=20)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
                stats["failed"] += 1
                continue
            text = html_to_text(body).encode("utf-8")
            header = f"# источник: {src['url']}\nполучено: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n\n"
            stats["bytes"] += _save_doc(src_id, "index.md", header.encode("utf-8") + text)
            stats["fetched"] += 1

    return stats


def add(target: str) -> dict:
    """Добавить внешний источник: ссылка на GitHub-репозиторий или произвольный URL."""
    target = target.strip()
    gh = re.match(r"https?://github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$", target)
    items = load_sources()
    if gh:
        owner, repo = gh.group(1), gh.group(2)
        src_id = f"{owner}/{repo}"
        entry = {"id": src_id, "kind": "github", "owner": owner, "repo": repo, "branch": "main",
                 "docs": ["README.md", "AGENTS.md", "ARCHITECTURE.md", "FEATURE_PARITY.md"]}
    else:
        host = re.sub(r"^https?://", "", target).strip("/")
        src_id = re.sub(r"[^\w.\-]+", "_", host) or "url"
        entry = {"id": src_id, "kind": "url", "url": target}
    if any(s["id"] == src_id for s in items):
        return {"added": False, "id": src_id, "reason": "уже есть"}
    items.append(entry)
    save_sources(items)
    return {"added": True, "id": src_id, "kind": entry["kind"]}


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(text)]


def _best_snippet(text: str, query_tokens: list[str]) -> str:
    best, best_hits = "", -1
    for line in text.splitlines():
        low = line.lower()
        hits = sum(1 for t in query_tokens if t in low)
        if hits > best_hits and line.strip():
            best, best_hits = line.strip(), hits
    return best[:240]


def search(query: str, k: int = 8) -> list[dict]:
    qs = _tokens(query)
    if not qs or not CACHE.exists():
        return []
    results = []
    for path in CACHE.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        counts = Counter(_tokens(text))
        if not counts:
            continue
        score = sum(counts.get(t, 0) for t in qs) / (len(counts) ** 0.5)
        if score <= 0:
            continue
        rel = path.relative_to(CACHE)
        results.append({
            "source": rel.parts[0],
            "doc": "/".join(rel.parts[1:]),
            "score": round(score, 2),
            "snippet": _best_snippet(text, qs),
        })
    results.sort(key=lambda r: -r["score"])
    return results[:k]


def summary() -> list[dict]:
    index = load_index()
    rows = []
    for src_id, docs in sorted(index.items()):
        total = sum(d["bytes"] for d in docs.values())
        rows.append({"id": src_id, "docs": len(docs), "bytes": total, "docs_list": sorted(docs)})
    return rows


def render_search(query: str, k: int = 8, as_json: bool = False) -> str:
    hits = search(query, k)
    if as_json:
        return json.dumps({"query": query, "hits": hits}, ensure_ascii=False, indent=2)
    if not hits:
        return f"ничего не найдено по «{query}» (кэш пуст? запустите refs sync)"
    lines = [f"справочник: {len(hits)} совпадений по «{query}»", ""]
    for i, hit in enumerate(hits, 1):
        lines.append(f"{i}. {hit['source']}/{hit['doc']}  (score {hit['score']})")
        lines.append(f"   {hit['snippet']}")
    return "\n".join(lines)

def snapshot() -> dict:
    """Снимок дайджестов: что мы видели в прошлый раз."""
    index = load_index()
    return {src: {doc: meta.get("sha") for doc, meta in docs.items()} for src, docs in index.items()}


def diff(before: dict, after: dict) -> list[dict]:
    """Сравнивает два снимка: появилось, изменилось, исчезло."""
    changes = []
    for src in sorted(set(before) | set(after)):
        old = before.get(src, {})
        new = after.get(src, {})
        for doc in sorted(set(old) | set(new)):
            a, b = old.get(doc), new.get(doc)
            if a is None:
                changes.append({"source": src, "doc": doc, "status": "новый", "from": None, "to": b})
            elif b is None:
                changes.append({"source": src, "doc": doc, "status": "исчез", "from": a, "to": None})
            elif a != b:
                changes.append({"source": src, "doc": doc, "status": "изменился", "from": a, "to": b})
    return changes

