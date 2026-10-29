"""Тесты выбора типа ответа.

Запуск: python tests/test_reply.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.reply import decide  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


@case("неоднозначный термин → уточнить", False)
def _():
    out = decide("сделай красиво")
    assert out["type"] == "CLARIFY", out


@case("необратимое действие без подтверждения → отказ", False)
def _():
    out = decide("опубликуй релиз")
    assert out["type"] == "REFUSE", out


@case("факт известен только собеседнику → спросить его", False)
def _():
    out = decide("уточни у владельца, что он имел в виду")
    assert out["type"] == "ASK_PEER", out


@case("внешний факт при неясном классе → искать", False)
def _():
    out = decide("какой сейчас курс и новости по рынку")
    assert out["type"] == "SEARCH", out


@case("понятная задача известного класса → исполнять", False)
def _():
    out = decide("посчитай сколько раз встречается слово критерий")
    assert out["type"] == "EXECUTE", out


@case("без совпадений → тоже не догадка", False)
def _():
    out = decide("фыва олдж")
    assert out["type"] in {"EXECUTE", "CLARIFY"}, out
    assert out["score"] == 0.0, out


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
    print(f"\nтип ответа: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
