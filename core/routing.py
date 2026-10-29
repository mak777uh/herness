"""routing — семантическая раскладка задачи по классам и инструментам.

Без эмбеддингов и сети: TF-IDF по описаниям классов и инструментов. Грубо, зато офлайн и
воспроизводимо. Успешный результат дописывается в журнал обучения (learning.jsonl) и может
породить новый класс — но только по накоплению, а не по одному случаю.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEARN = ROOT / "learning.jsonl"
TOKEN = re.compile(r"[\w\-]+", re.UNICODE)


def tokens(text: str) -> list[str]:
    """Грубая нормализация: первые пять символов. Иначе «опубликуй» и «опубликовать» — разные слова."""
    return [t.lower()[:5] for t in TOKEN.findall(text) if len(t) > 2]


def tfidf(docs: dict[str, list[str]]) -> dict[str, dict[str, float]]:
    n = len(docs)
    df: Counter = Counter()
    for toks in docs.values():
        for term in set(toks):
            df[term] += 1
    vectors: dict[str, dict[str, float]] = {}
    for key, toks in docs.items():
        counts = Counter(toks)
        total = sum(counts.values()) or 1
        vectors[key] = {
            term: (counts[term] / total) * math.log((n + 1) / (df[term] + 1)) + 1e-9
            for term in counts
        }
    return vectors


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    num = sum(a[t] * b[t] for t in common)
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


def load_classes() -> list[dict]:
    return json.loads((ROOT / "classes.json").read_text(encoding="utf-8"))["classes"]


def load_tools() -> list[dict]:
    return json.loads((ROOT / "tools.json").read_text(encoding="utf-8"))["tools"]


def route(task: str, top: int = 3) -> list[dict]:
    """Раскладывает задачу по классам: близость описания + какие инструменты там работают."""
    classes = load_classes()
    tools = load_tools()
    docs = {}
    for cls in classes:
        docs[cls["id"]] = tokens(" ".join([cls["name"], cls.get("description", ""), " ".join(cls["actions"])]))
    docs["__task__"] = tokens(task)
    vectors = tfidf(docs)
    task_vec = vectors.pop("__task__")

    out = []
    for cls in classes:
        score = cosine(task_vec, vectors.get(cls["id"], {}))
        if score <= 0:
            continue
        used = [t["name"] for t in tools if cls["id"] in (t.get("classes") or {})]
        out.append({"class": cls["id"], "name": cls["name"], "score": round(score, 3), "tools": used})
    out.sort(key=lambda r: -r["score"])
    return out[:top]


def learn(task: str, tool: str, cls: str | None, ok: bool) -> dict:
    record = {"task": task[:300], "tool": tool, "class": cls, "ok": ok}
    with LEARN.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def load_learning() -> list[dict]:
    if not LEARN.exists():
        return []
    return [json.loads(line) for line in LEARN.read_text(encoding="utf-8").splitlines() if line.strip()]


def propose_classes(min_support: int = 3) -> list[dict]:
    """Новый класс предлагается, когда накопилось ≥N успешных задач вне известных классов."""
    known = {c["id"] for c in load_classes()}
    loose = [r for r in load_learning() if r.get("ok") and (not r.get("class") or r["class"] not in known)]
    if len(loose) < min_support:
        return []
    terms: Counter = Counter()
    for record in loose:
        terms.update(set(tokens(record["task"])))
    common = [t for t, c in terms.most_common(5)]
    return [{"support": len(loose), "shared_terms": common,
             "tools": sorted({r["tool"] for r in loose})}]


