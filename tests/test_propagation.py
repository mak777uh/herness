"""Тесты переноса инструментов между классами.

Запуск: python tests/test_propagation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.propagation import neighbours, similarity, suggest  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


CLASSES = {
    "T-0003": {"read", "write", "run"},
    "T-0004": {"run", "write", "report"},
    "T-0007": {"answer"},
}


@case("близость считается по пересечению действий", False)
def _():
    assert similarity({"run", "write"}, {"run", "write", "report"}) == 2 / 3
    assert similarity({"run"}, {"answer"}) == 0.0


@case("соседом считается только близкий класс", False)
def _():
    near = dict(neighbours(CLASSES, "T-0003", threshold=0.5))
    assert "T-0004" in near, near
    assert "T-0007" not in near, near


@case("перенос предлагается только при выигрыше и близости", False)
def _():
    tool = {"name": "hs py", "classes": {"T-0003": {"status": "active", "advantage": 0.33}}}
    out = suggest(tool, CLASSES)
    assert out and out[0]["to"] == "T-0004", out


@case("без измеренного выигрыша переноса нет", False)
def _():
    tool = {"name": "x", "classes": {"T-0003": {"status": "active", "advantage": None}}}
    assert suggest(tool, CLASSES) == []


@case("уже пробованный класс повторно не предлагается", False)
def _():
    tool = {"name": "x", "classes": {"T-0003": {"status": "active", "advantage": 0.5},
                                     "T-0004": {"status": "trial", "advantage": None}}}
    assert suggest(tool, CLASSES) == []


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
    print(f"\nперенос: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
