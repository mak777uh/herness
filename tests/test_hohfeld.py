"""Тесты проверки границ по Хохфельду: конфликт, совместимость, пустота.

Запуск: python tests/test_hohfeld.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.hohfeld import BoundaryView, check, self_consistency  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


@case("A может X, B тоже может → совместимо", False)
def _():
    a = BoundaryView("A", allow=frozenset({"read"}))
    b = BoundaryView("B", allow=frozenset({"read"}))
    verdict = check(a, b)
    assert verdict.compatible and verdict.status == "совместимо", verdict


@case("A может X, B запрещает X → конфликт", False)
def _():
    a = BoundaryView("A", allow=frozenset({"publish"}))
    b = BoundaryView("B", deny=frozenset({"publish"}))
    verdict = check(a, b)
    assert not verdict.compatible and verdict.status == "конфликт", verdict


@case("B вправе требовать X, A запрещает X → конфликт", False)
def _():
    a = BoundaryView("A", deny=frozenset({"transfer"}))
    b = BoundaryView("B", expects=frozenset({"transfer"}))
    verdict = check(a, b)
    assert not verdict.compatible, verdict


@case("нет пересечения → пусто (мостика нет)", False)
def _():
    a = BoundaryView("A", allow=frozenset({"read"}))
    b = BoundaryView("B", allow=frozenset({"write"}))
    verdict = check(a, b)
    assert verdict.compatible and verdict.status == "пусто", verdict


@case("граница сама себе противоречит", False)
def _():
    view = BoundaryView("A", allow=frozenset({"x"}), deny=frozenset({"x"}))
    verdict = self_consistency(view)
    assert not verdict.compatible, verdict


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
    print(f"\nхохфельд: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
