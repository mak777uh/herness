"""Тесты аудита: заметка без воспроизводящего случая не является находкой.

Запуск: python tests/test_audit.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import audit  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


def _write(root: Path, name: str, text: str) -> None:
    target = root / "inbox" / "harness"
    target.mkdir(parents=True, exist_ok=True)
    (target / name).write_text(text, encoding="utf-8")


GOOD = """from: a
to: harness
about: x
severity: high
repro: python bin/hs.py gates
finding: гейт пропускает заметку без repro
would_change: если гейт начнёт падать
"""

NO_REPRO = """from: a
to: harness
about: x
severity: low
finding: мне не нравится
would_change: ничего
"""

NO_FROM = """to: harness
about: x
finding: что-то
"""


@case("заметка с repro — находка", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, "a.md", GOOD)
        data = audit.summary(root)
        assert len(data["findings"]) == 1, data
        assert not data["opinions"]


@case("заметка без repro — мнение, не находка", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, "b.md", NO_REPRO)
        data = audit.summary(root)
        assert len(data["opinions"]) == 1, data
        assert not data["findings"]


@case("заметка без обязательного поля — некорректна", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, "c.md", NO_FROM)
        data = audit.summary(root)
        assert len(data["invalid"]) == 1, data
        assert audit.problems(root), "нет замечаний по некорректной заметке"


@case("повторы группируются", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, "d1.md", GOOD)
        _write(root, "d2.md", GOOD)
        data = audit.summary(root)
        assert len(data["findings"]) == 2, data
        assert data["repeats"] and data["repeats"][0][1] == 2, data["repeats"]


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
    print(f"\nаудит: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
