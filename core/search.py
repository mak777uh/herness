"""Поиск для агента: разбор выдачи + проверка релевантности.

Главный урок (E-0004): статус 200 и десять элементов в выдаче ещё не значит, что это ответ на
запрос. Bing без сессии отдаёт заглушку: заголовки не содержат слов запроса. Поэтому результат
всегда несёт оценку релевантности, и `decoy` отличается от `ok`.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field

from . import webfetch

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
STOP = {"the", "and", "for", "not", "with", "how", "what", "why", "linux", "release"}


@dataclass
class Hit:
    title: str
    url: str
    snippet: str = ""


@dataclass
class SearchResult:
    query: str
    kind: str                      # ok / decoy / blocked / error
    hits: list[Hit] = field(default_factory=list)
    relevance: float = 0.0
    status: int = 0
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "query": self.query, "kind": self.kind, "status": self.status,
            "relevance": round(self.relevance, 2), "hits": len(self.hits), "note": self.note,
            "items": [{"title": h.title, "url": h.url} for h in self.hits],
        }


TAGS = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    text = TAGS.sub(" ", text)
    for entity, char in (("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"), ("&lt;", "<"),
                         ("&gt;", ">"), ("&nbsp;", " ")):
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text).strip()


def parse_rss(xml: str, limit: int = 10) -> list[Hit]:
    hits: list[Hit] = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S)[:limit]:
        title_match = re.search(r"<title>(.*?)</title>", item, re.S)
        link_match = re.search(r"<link>(.*?)</link>", item, re.S)
        if not title_match or not link_match:
            continue
        hits.append(Hit(title=_clean(title_match.group(1)), url=link_match.group(1).strip()))
    return hits


def parse_html(html: str, limit: int = 10) -> list[Hit]:
    hits: list[Hit] = []
    for block in re.findall(r'<li class="b_algo".*?</li>', html, re.S)[:limit]:
        link = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not link:
            continue
        hits.append(Hit(title=_clean(link.group(2)), url=link.group(1)))
    return hits


def relevance(hits: list[Hit], query: str) -> float:
    """Доля слов запроса, встречающихся в заголовках и сниппетах."""
    words = [w for w in re.findall(r"[\w.]+", query.lower()) if len(w) > 2 and w not in STOP]
    if not words or not hits:
        return 0.0
    text = " ".join((h.title + " " + h.snippet) for h in hits).lower()
    return sum(1 for word in words if word in text) / len(words)


def search(query: str, limit: int = 10, timeout: int = 25) -> SearchResult:
    """Поиск через Bing (RSS, при неудаче — HTML) с проверкой релевантности."""
    quoted = urllib.parse.quote_plus(query)
    rss = webfetch.fetch(f"https://www.bing.com/search?q={quoted}&format=rss&setlang=en",
                         max_bytes=200_000, timeout=timeout, user_agent=UA)
    hits: list[Hit] = []
    if rss.ok:
        hits = parse_rss(rss.text, limit)
    if not hits:
        html = webfetch.fetch(f"https://www.bing.com/search?q={quoted}&setlang=en",
                              max_bytes=400_000, timeout=timeout, user_agent=UA)
        if not html.ok:
            return SearchResult(query=query, kind="blocked" if html.kind == "blocked" else "error",
                                status=html.status, note=html.error or html.kind)
        hits = parse_html(html.text, limit)
        status = html.status
    else:
        status = rss.status

    score = relevance(hits, query)
    if not hits:
        return SearchResult(query=query, kind="error", status=status, note="выдача пуста")
    kind = "ok" if score >= 0.5 else "decoy"
    note = "" if kind == "ok" else f"релевантность {score:.2f}: выдача не про запрос"
    return SearchResult(query=query, kind=kind, hits=hits, relevance=score, status=status, note=note)
