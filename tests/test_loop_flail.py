"""Тесты детектора барахтания: цикл обязан останавливаться сам."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.journal import Journal  # noqa: E402
from core.loop import MockProvider, Step, run  # noqa: E402
from core.tools import ToolOutput  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


class FailingTool:
    """Инструмент, который всегда отказывает."""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, command: str) -> ToolOutput:
        self.calls += 1
        return ToolOutput(b"", b"boom", 1)

    def dispatch(self, name: str, args: dict) -> ToolOutput:
        return self.run(str(args))


class EchoTool:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, command: str) -> ToolOutput:
        self.calls += 1
        return ToolOutput(b"ok", b"", 0)

    def dispatch(self, name: str, args: dict) -> ToolOutput:
        return self.run(str(args))


def make_journal(name: str) -> Journal:
    directory = ROOT / "runs" / name
    directory.mkdir(parents=True, exist_ok=True)
    return Journal(directory)


@case("три отказа подряд останавливают цикл со статусом flail", False)
def _():
    provider = MockProvider(script=[Step(tool={"name": "shell", "args": {"command": "x"}})] * 5)
    journal = make_journal("test-flail-fails")
    result = run("тест", provider, FailingTool(), journal, max_steps=10)
    assert result["status"] == "flail" and result["steps"] <= 4, result


@case("три одинаковых вызова останавливают цикл со статусом flail", False)
def _():
    step = Step(tool={"name": "shell", "args": {"command": "same"}})
    provider = MockProvider(script=[step] * 5)
    journal = make_journal("test-flail-same")
    result = run("тест", provider, EchoTool(), journal, max_steps=10)
    assert result["status"] == "flail", result


@case("обычный ход не считается барахтанием", False)
def _():
    provider = MockProvider(script=[
        Step(tool={"name": "shell", "args": {"command": "a"}}),
        Step(tool={"name": "shell", "args": {"command": "b"}}),
        Step(text="готово"),
    ])
    journal = make_journal("test-flail-ok")
    result = run("тест", provider, EchoTool(), journal, max_steps=10)
    assert result["status"] == "done", result


@case("бюджет исчерпан — причина записана в журнал", False)
def _():
    provider = MockProvider(script=[Step(tool={"name": "shell", "args": {"command": str(i)}})
                                    for i in range(10)])
    journal = make_journal("test-flail-budget")
    result = run("тест", provider, EchoTool(), journal, max_steps=2)
    events = (ROOT / "runs" / "test-flail-budget" / "events.jsonl").read_text(encoding="utf-8")
    assert result["status"] in ("budget", "flail") and "run/budget" in events or "run/flail" in events, events[-200:]


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
    print(f"\nцикл: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
