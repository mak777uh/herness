"""Тесты поиска: разбор RSS/HTML и, главное, отличие выдачи от заглушки (E-0004)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.search import Hit, parse_html, parse_rss, relevance  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


REAL = """<?xml version="1.0"?><rss><channel><title>Bing: nixos 26.05</title>
<item><title>NixOS 26.05 released</title><link>https://nixos.org/blog/announcements</link></item>
<item><title>NixOS 26.05 release notes</title><link>https://nixos.org/manual/release-notes</link></item>
</channel></rss>"""

DECOY = """<?xml version="1.0"?><rss><channel><title>Bing: nixos 26.05</title>
<item><title>Microsoft - Official Home Page</title><link>https://microsoft.com</link></item>
<item><title>Sign in to your account</title><link>https://login.microsoft.com</link></item>
</channel></rss>"""


@case("RSS разбирается в заголовки и ссылки", False)
def _():
    hits = parse_rss(REAL)
    assert len(hits) == 2 and hits[0].url.startswith("https://nixos.org"), hits


@case("релевантная выдача даёт высокую оценку", False)
def _():
    hits = parse_rss(REAL)
    assert relevance(hits, "nixos 26.05") >= 0.5, relevance(hits, "nixos 26.05")


@case("заглушка даёт низкую оценку", False)
def _():
    hits = parse_rss(DECOY)
    assert relevance(hits, "nixos 26.05") < 0.5


@case("HTML-выдача Bing разбирается", False)
def _():
    html = ('<li class="b_algo"><h2><a href="https://example.org/a">Пример</a></h2>'
            '<p>описание</p></li>')
    hits = parse_html(html)
    assert len(hits) == 1 and hits[0].title == "Пример"


@case("пустая выдача не считается релевантной", False)
def _():
    assert relevance([], "что угодно") == 0.0


def main() -> int:
    failed = 0
    for name, should_raise, fn in CASES:
        try:
            fn()
            raised = False
        except AssertionError:
            raised = True
        ok = raised == should_raise
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {name}")
    print(f"\nпоиск: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
