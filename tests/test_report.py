"""Тесты отчёта: отчёт без границ не создаётся, свидетельства видны.

Запуск: python tests/test_report.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.contracts import Claim, ContractError  # noqa: E402
from core.journal import Journal  # noqa: E402
from core.loop import MockProvider, Step, run  # noqa: E402
from core.report import build, write  # noqa: E402
from core.tools import ShellTool  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


def _run_once(root: Path) -> Path:
    journal = Journal(root / "run")
    provider = MockProvider([
        Step(tool={"name": "shell", "args": {"command": "echo report"}}),
        Step(text="готово"),
    ])
    run("проба отчёта", provider, ShellTool(root), journal)
    return root / "run"


@case("отчёт собирается из журнала и содержит артефакт", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _run_once(Path(tmp))
        text = build(run_dir, "проба отчёта", boundaries=("что модель не выдумала",))
        assert "## Свидетельства" in text, text
        assert "artifacts/" in text, text
        assert "что модель не выдумала" in text, text


@case("отчёт без границ не создаётся", True)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _run_once(Path(tmp))
        build(run_dir, "проба отчёта", boundaries=())


@case("утверждения попадают в отчёт и проверяются", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _run_once(Path(tmp))
        claim = Claim(id="C-0001", text="артефакт записан", type="observation", origin="observed",
                      evidence=("artifacts/x",), not_claimed=("что так будет всегда",))
        text = build(run_dir, "проба", claims=[claim], boundaries=("что это единичный прогон",))
        assert "C-0001" in text, text
        assert "observation" in text, text


@case("write создаёт report.md на диске", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _run_once(Path(tmp))
        path = write(run_dir, "проба", boundaries=("граница",))
        assert path.exists() and path.name == "report.md"
        assert "## Что это не доказывает" in path.read_text(encoding="utf-8")


@case("нет журнала — отказ, а не пустой отчёт", True)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp) / "нет", "проба", boundaries=("x",))


def main() -> int:
    failed = 0
    for name, should_raise, fn in CASES:
        try:
            fn()
            raised = False
        except (AssertionError, ContractError):
            raised = True
        ok = raised == should_raise
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {name}")
    print(f"\nотчёт: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
