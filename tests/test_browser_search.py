"""Тесты браузерного поиска: разбор ответа MCP, редиректы, релевантность (без сети)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.browser_search import Hit, _decode, _parse_payload, relevance  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


RAW = '### Result\n"' + json.dumps(json.dumps([
    {"h": "https://nixos.org/manual/nixos/stable/release-notes", "t": "NixOS 26.05 release notes"},
    {"h": "https://duckduckgo.com/about", "t": "About DuckDuckGo privacy"},
]))[1:-1] + '"\n\n### Ran Playwright code\n```js\n...\n```'


@case("ответ MCP разбирается в список ссылок", False)
def _():
    items = _parse_payload(RAW)
    assert len(items) == 2 and items[0]["h"].startswith("https://nixos.org"), items


@case("редирект Google раскрывается", False)
def _():
    url = "https://www.google.com/url?q=https://nixos.org/manual&sa=U"
    assert _decode(url) == "https://nixos.org/manual", _decode(url)


@case("редирект DuckDuckGo раскрывается", False)
def _():
    url = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fnixos.org%2Fmanual"
    assert _decode(url) == "https://nixos.org/manual", _decode(url)


@case("релевантность считается по заголовкам и ссылкам", False)
def _():
    hits = [Hit("NixOS 26.05 release notes", "https://nixos.org/manual")]
    assert relevance(hits, "nixos 26.05 release notes") > 0.7


@case("пустая выдача даёт ноль", False)
def _():
    assert relevance([], "nixos") == 0.0


@case("мусор вместо JSON не ломает разбор", False)
def _():
    assert _parse_payload("### Result\n\"не json\"") == []


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
    print(f"\nбраузер: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
