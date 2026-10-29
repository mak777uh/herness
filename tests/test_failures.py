"""Тесты корпуса отказов: случай без полей не принимается.

Запуск: python tests/test_failures.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import failures  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


GOOD = """id: F-0001
date: 2026-10-29
what: выдумана посылка
class: invented-premise
principle: AGENTS 1c
detect: правило 1c
test: вопрос до действий
"""

NO_TEST = """id: F-0002
date: 2026-10-29
what: что-то
class: x
principle: y
detect: z
"""

BAD_ID = """id: 1
date: 2026-10-29
what: что-то
class: x
principle: y
detect: z
test: t
"""


def _write(root: Path, name: str, text: str) -> None:
    folder = root / "lab" / "failures"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


@case("полный случай проходит без замечаний", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, "F-0001.md", GOOD)
        assert failures.problems(root) == [], failures.problems(root)
        assert failures.summary(root)["total"] == 1


@case("случай без способа проверки — замечание", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, "F-0002.md", NO_TEST)
        issues = failures.problems(root)
        assert any("test" in i for i in issues), issues


@case("плохой идентификатор — замечание", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, "bad.md", BAD_ID)
        issues = failures.problems(root)
        assert any("F-0000" in i for i in issues), issues


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
    print(f"\nотказы: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
