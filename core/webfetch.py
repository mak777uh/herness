"""fetch — сетевой инструмент агента: HTTP, а не браузер.

Правила из ADR-0032:
* лимит байтов и времени — у страницы может быть 50 МБ;
* отказ источника (403/429/капча) отличается от «страницы нет»;
* локальные адреса идут мимо прокси, внешние — через прокси, если он задан;
* результат описывает себя: статус, вид, байты, обрезка, кодировка.
"""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

CAPTCHA_MARKERS = (
    "captcha", "just a moment", "cf-challenge", "challenge-platform",
    "attention required", "access denied", "robot check",
)
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


@dataclass
class WebResult:
    url: str
    status: int
    kind: str            # ok / blocked / not_found / error
    bytes_read: int = 0
    truncated: bool = False
    content_type: str = ""
    charset: str = "utf-8"
    text: str = ""
    error: str = ""
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.kind == "ok"

    def to_dict(self) -> dict:
        return {
            "url": self.url, "status": self.status, "kind": self.kind,
            "bytes": self.bytes_read, "truncated": self.truncated,
            "content_type": self.content_type, "charset": self.charset,
            "error": self.error, "note": self.note,
        }


def _proxy_for(host: str, explicit: str | None) -> str | None:
    """Локальные адреса — напрямую; внешние — через явный прокси или переменные окружения."""
    if host in LOOPBACK:
        return None
    if explicit:
        return explicit
    return os.environ.get("HARNESS_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")


def _classify(status: int, body: str) -> str:
    if status == 404:
        return "not_found"
    if status in (401, 402, 403, 429, 503):
        return "blocked"
    lowered = body[:4000].lower()
    if any(marker in lowered for marker in CAPTCHA_MARKERS):
        return "blocked"
    if 200 <= status < 300:
        return "ok"
    return "error"


def fetch(url: str, max_bytes: int = 200_000, timeout: int = 20,
          proxy: str | None = None, user_agent: str = "herness/1.0") -> WebResult:
    """Забирает URL с лимитом и классификацией результата."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return WebResult(url=url, status=0, kind="error", error="только http/https")

    proxy_url = _proxy_for(parsed.hostname or "", proxy)
    handlers = [urllib.request.ProxyHandler({} if proxy_url is None else {"http": proxy_url, "https": proxy_url})]
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,*/*"})

    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read(max_bytes).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        kind = _classify(exc.code, body)
        return WebResult(url=url, status=exc.code, kind=kind, bytes_read=len(body),
                         content_type=exc.headers.get("Content-Type", "") if exc.headers else "",
                         text=body[:2000], error=f"HTTP {exc.code}")
    except urllib.error.URLError as exc:
        return WebResult(url=url, status=0, kind="error", error=f"сеть: {exc.reason}")
    except Exception as exc:  # noqa: BLE001
        return WebResult(url=url, status=0, kind="error", error=type(exc).__name__ + ": " + str(exc)[:120])

    truncated = len(raw) > max_bytes
    raw = raw[:max_bytes]
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type)
    if match:
        charset = match.group(1).lower()
    try:
        text = raw.decode(charset, "replace")
    except LookupError:
        text = raw.decode("utf-8", "replace")
    kind = _classify(status, text)
    note = "обрезано по лимиту" if truncated else ""
    return WebResult(url=url, status=status, kind=kind, bytes_read=len(raw), truncated=truncated,
                     content_type=content_type, charset=charset, text=text, note=note)


def robots_allows(url: str, timeout: int = 10) -> tuple[bool, str]:
    """Грубая проверка robots.txt: запрещён ли путь для всех."""
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    result = fetch(robots_url, max_bytes=50_000, timeout=timeout)
    if not result.ok:
        return True, "robots.txt не получен — считаем разрешённым"
    path = parsed.path or "/"
    blocked_agents = False
    for line in result.text.splitlines():
        line = line.strip().lower()
        if line.startswith("user-agent:"):
            blocked_agents = line.split(":", 1)[1].strip() == "*"
        elif blocked_agents and line.startswith("disallow:"):
            rule = line.split(":", 1)[1].strip()
            if rule and path.startswith(rule):
                return False, f"robots.txt запрещает {rule}"
    return True, "robots.txt не запрещает"
