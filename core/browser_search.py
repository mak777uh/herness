"""Поиск через живой браузер (CDP) — канал, который обходит блокировки.

Идея: браузер пользователя уже прошёл проверки Cloudflare/Google, у него живые cookie и обычный
отпечаток. Мы не изобретаем обход, а используем то, что уже открыто руками.

Требует запущенный Chrome с `--remote-debugging-port` (см. `bin/browser_chrome.ps1`).
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .mcp_client import MCPClient

CLI = r"C:\111\browser-mcp\node_modules\@playwright\mcp\cli.js"
ENDPOINT = "http://127.0.0.1:9222"

ENGINES = {
    "ddg": "https://duckduckgo.com/?q={q}",
    "google": "https://www.google.com/search?q={q}",
    "startpage": "https://www.startpage.com/sp/search?query={q}",
    "bing": "https://www.bing.com/search?q={q}",
}
OWN_HOSTS = {
    "ddg": "duckduckgo.com", "google": "google.", "startpage": "startpage.com", "bing": "bing.com",
}

EXTRACT_JS = """() => JSON.stringify(Array.from(document.querySelectorAll('a[href^="http"]'))
  .map(a => ({h: a.href, t: (a.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 160)}))
  .filter(x => x.t.length > 15).slice(0, 60))"""



CHROME_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)
PROFILE_SRC = pathlib.Path.home() / "AppData/Local/Google/Chrome/User Data"
PROFILE_DST = pathlib.Path(r"C:\111\chrome-cdp")


def port_alive(port: int = 9222, timeout: float = 1.5) -> bool:
    """Отвечает ли Chrome по CDP. Локальные запросы идут мимо прокси из окружения."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/json/version", timeout=timeout):
            return True
    except Exception:  # noqa: BLE001
        return False


def ensure_chrome(port: int = 9222, timeout: float = 25.0) -> tuple[bool, str]:
    """Поднимает Chrome с CDP, если порт закрыт. Копирует cookie, когда они доступны."""
    if port_alive(port):
        return True, "Chrome уже слушает"

    chrome = next((path for path in CHROME_PATHS if pathlib.Path(path).exists()), None)
    if chrome is None:
        return False, "Chrome не найден"

    (PROFILE_DST / "Default" / "Network").mkdir(parents=True, exist_ok=True)
    copied, locked = 0, 0
    for rel in ("Local State", "Default/Preferences", "Default/Secure Preferences",
                "Default/Network/Cookies", "Default/Login Data", "Default/Web Data"):
        source = PROFILE_SRC / rel
        if not source.exists():
            continue
        try:
            shutil.copy2(source, PROFILE_DST / rel)
            copied += 1
        except Exception:  # noqa: BLE001
            locked += 1

    subprocess.Popen([chrome, f"--remote-debugging-port={port}",
                      f"--user-data-dir={PROFILE_DST}", "--no-first-run",
                      "--no-default-browser-check", "about:blank"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_alive(port):
            note = f"Chrome поднят (cookie скопировано {copied}"
            note += f", занято {locked})" if locked else ")"
            return True, note
        time.sleep(0.4)
    return False, "Chrome не поднялся за отведённое время"


def wait_for_links(client: "MCPClient", limit: int = 10, timeout: float = 8.0) -> list[dict]:
    """Опрашивает страницу, пока не появятся ссылки. Быстрее фиксированной паузы."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = client.call("browser_evaluate", {"function": EXTRACT_JS})
        except Exception:  # noqa: BLE001
            time.sleep(0.3)
            continue
        text = "".join(item.get("text", "") for item in result.get("content", [])
                       if item.get("type") == "text")
        items = _parse_payload(text)
        if items:
            return items
        time.sleep(0.3)
    return []


@dataclass
class Hit:
    title: str
    url: str


@dataclass
class BrowserResult:
    query: str
    engine: str
    kind: str                      # ok / empty / blocked / error
    hits: list[Hit] = field(default_factory=list)
    relevance: float = 0.0
    note: str = ""

    def to_dict(self) -> dict:
        return {"query": self.query, "engine": self.engine, "kind": self.kind,
                "relevance": round(self.relevance, 2), "hits": len(self.hits), "note": self.note,
                "items": [{"title": h.title, "url": h.url} for h in self.hits]}


def _parse_payload(text: str) -> list[dict]:
    """Ответ browser_evaluate: `### Result` и JSON-строка, завёрнутая в кавычки.

    Двойное декодирование: сначала внешняя строка-обёртка, потом сам массив.
    """
    marker = text.find("### Result")
    body = text[marker + len("### Result"):].strip() if marker >= 0 else text.strip()
    # отрезаем служебный хвост вроде "\n```js ..."
    for tail in ("\n### ", "\n```"):
        if tail in body:
            body = body.split(tail)[0]
    body = body.strip()

    candidates = []
    if body.startswith('"'):
        try:
            candidates.append(json.loads(body))
        except json.JSONDecodeError:
            pass
    start, end = body.find("["), body.rfind("]")
    if start >= 0 and end > start:
        candidates.append(body[start:end + 1])

    for candidate in candidates:
        if isinstance(candidate, str):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
        else:
            parsed = candidate
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def _decode(url: str) -> str:
    """Раскрывает редиректы поисковиков: google /url?q=, ddg /l/?uddg=."""
    if "google." in url and "/url?" in url:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q")
        if query:
            return query[0]
    if "duckduckgo.com/l/" in url:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("uddg")
        if query:
            return query[0]
    return url


def relevance(hits: list[Hit], query: str) -> float:
    words = [w for w in re.findall(r"[\w.]+", query.lower()) if len(w) > 2]
    if not words or not hits:
        return 0.0
    text = " ".join(h.title + " " + h.url for h in hits).lower()
    return sum(1 for word in words if word in text) / len(words)


def search(query: str, engine: str = "ddg", limit: int = 10,
           endpoint: str = ENDPOINT, wait: float = 8.0, ensure: bool = False) -> BrowserResult:
    if engine not in ENGINES:
        return BrowserResult(query, engine, "error", note=f"неизвестный движок {engine}")
    if ensure:
        alive, note = ensure_chrome(int(endpoint.rsplit(":", 1)[-1]))
        if not alive:
            return BrowserResult(query, engine, "error", note=note)
    client = MCPClient(["node", CLI, "--cdp-endpoint", endpoint], cwd=r"C:\111\browser-mcp")
    items: list[dict] = []
    try:
        client.initialize()
        url = ENGINES[engine].format(q=urllib.parse.quote_plus(query))
        client.call("browser_navigate", {"url": url})
        items = wait_for_links(client, limit, timeout=wait)
        page = _page_text(client)
    except Exception as exc:  # noqa: BLE001
        return BrowserResult(query, engine, "error", note=f"{type(exc).__name__}: {str(exc)[:100]}")
    finally:
        client.close()

    if any(marker in page.lower() for marker in ("captcha", "подозрительный трафик",
                                                 "проверки безопасности", "unusual traffic")):
        return BrowserResult(query, engine, "blocked", note="страница-заглушка вместо выдачи")

    own = OWN_HOSTS[engine]
    hits: list[Hit] = []
    seen: set[str] = set()
    for item in items:
        target = _decode(item.get("h", ""))
        host = urllib.parse.urlparse(target).netloc.lower()
        if not host or own in host or target in seen:
            continue
        seen.add(target)
        hits.append(Hit(title=item.get("t", "").strip()[:160], url=target))
        if len(hits) >= limit:
            break

    if not hits:
        return BrowserResult(query, engine, "empty", note="ссылок в выдаче не найдено")
    score = relevance(hits, query)
    kind = "ok" if score >= 0.5 else "empty"
    return BrowserResult(query, engine, kind, hits=hits, relevance=score,
                         note="" if kind == "ok" else f"релевантность {score:.2f}")


def _page_text(client: MCPClient) -> str:
    try:
        result = client.call("browser_evaluate",
                             {"function": "() => document.body.innerText.slice(0, 2000)"})
        return "".join(item.get("text", "") for item in result.get("content", [])
                       if item.get("type") == "text")
    except Exception:  # noqa: BLE001
        return ""
