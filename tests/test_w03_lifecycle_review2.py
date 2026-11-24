"""E-0069: exact lifecycle diagnostics и wrong-first guard после review2."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from bin import accept  # noqa: E402
from test_accept import journal_bytes  # noqa: E402

CASES: list[tuple[str, callable]] = []

STEP_BEFORE_RESULT = [
    "run/start task: x", "tool/call read a", "step 1, потрачено 0",
    "tool/result ok a", "step 2, потрачено 0", "run/end готово",
]
STEP_BEFORE_CALL = [
    "run/start task: x", "step 1, потрачено 0", "tool/call read a",
    "tool/result ok a", "step 2, потрачено 0", "run/end готово",
]
DUPLICATE_END = [
    "run/start task: x", "step 0, потрачено 0", "run/end готово", "run/end снова",
]
AFTER_END = [
    "run/start task: x", "tool/call read a", "tool/result ok a",
    "step 1, потрачено 0", "run/end готово", "note после",
]
WRONG_FIRST = ["note перед", "run/start task: x", "step 0, потрачено 0", "run/end готово"]
VALID = [
    "run/start task: x", "tool/call read a", "tool/result ok a",
    "step 1, потрачено 0", "tool/call read b", "tool/result ok b",
    "step 2, потрачено 0", "run/end готово",
]


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def event_pairs(lines: list[str]) -> list[tuple[str, str]]:
    return [tuple(line.partition(" ")[::2]) for line in lines]


def lifecycle_problems(lines: list[str]) -> list[str]:
    records = accept.parse_journal(journal_bytes(lines))[0]
    return accept.tool_pairing_problems(accept.events(records))


def assert_exact(lines: list[str], diagnostic: str) -> None:
    problems = lifecycle_problems(lines)
    assert diagnostic in problems, (diagnostic, problems)
    criteria = {
        "task": "x", "require_status": "done-без-опоры", "max_steps": 8,
        "max_allowance": 0.001, "require_commit": True,
    }
    ok, rows = accept.check(criteria, accept.parse_journal(journal_bytes(lines))[0])
    assert not ok, rows


def mutated_pairing(old: str, new: str):
    source = inspect.getsource(accept.tool_pairing_problems)
    assert old in source, "metakontrol не нашёл production-ветку"
    namespace: dict = {}
    exec(source.replace(old, new, 1), namespace)  # noqa: S102 - локальная in-memory mutation
    return namespace["tool_pairing_problems"]


@case("review2 exact step before result with completing step")
def _():
    assert_exact(STEP_BEFORE_RESULT, "step до tool/result")


@case("review2 exact step before call with completing step")
def _():
    assert_exact(STEP_BEFORE_CALL, "step без предшествующего tool/result")


@case("review2 exact duplicate run end")
def _():
    assert_exact(DUPLICATE_END, "повторный run/end")


@case("review2 exact non-end event after run end")
def _():
    assert_exact(AFTER_END, "событие note после run/end")


@case("review2 wrong first event is rejected")
def _():
    assert_exact(WRONG_FIRST, "первое событие note, а не run/start")


@case("review2 missing end remains no-done status")
def _():
    lines = ["run/start task: x"]
    records = accept.parse_journal(journal_bytes(lines))[0]
    ok, rows = accept.check({"task": "x", "require_status": "no-done"}, records)
    assert ok, rows
    assert lifecycle_problems(lines) == [], lifecycle_problems(lines)
    done_ok, done_rows = accept.check({"task": "x", "require_status": "done"}, records)
    assert not done_ok, done_rows


@case("review2 valid call result step lifecycle remains accepted")
def _():
    assert lifecycle_problems(VALID) == [], lifecycle_problems(VALID)
    criteria = {
        "task": "x", "require_status": "done-без-опоры", "max_steps": 8,
        "max_allowance": 0.001, "require_commit": True,
    }
    ok, rows = accept.check(criteria, accept.parse_journal(journal_bytes(VALID))[0])
    assert ok, rows


@case("review2 metakontrol step-position branch removal")
def _():
    fn = mutated_pairing(
        'if phase == "waiting-result":\n                problems.append("step до tool/result")',
        'if False:\n                problems.append("step до tool/result")',
    )
    assert "step до tool/result" not in fn(event_pairs(STEP_BEFORE_RESULT))


@case("review2 metakontrol duplicate-end branch removal")
def _():
    fn = mutated_pairing(
        'if ended:\n                problems.append("повторный run/end")',
        'if False:\n                problems.append("повторный run/end")',
    )
    assert "повторный run/end" not in fn(event_pairs(DUPLICATE_END))


@case("review2 metakontrol after-end branch removal")
def _():
    fn = mutated_pairing(
        'if ended:\n            problems.append(f"событие {kind} после run/end")',
        'if False:\n            problems.append(f"событие {kind} после run/end")',
    )
    assert "событие note после run/end" not in fn(event_pairs(AFTER_END))


@case("review2 metakontrol first-event guard removal")
def _():
    fn = mutated_pairing(
        'if evs[0][0] != "run/start":\n        problems.append(f"первое событие {evs[0][0]}, а не run/start")',
        'if False:\n        problems.append(f"первое событие {evs[0][0]}, а не run/start")',
    )
    assert "первое событие note, а не run/start" not in fn(event_pairs(WRONG_FIRST))


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"[ok] {name}")
    print(f"W03 review2 controls: {len(CASES) - failed}/{len(CASES)} ok; провалов: {failed}")
    return 1 if failed or len(CASES) != 11 else 0


if __name__ == "__main__":
    sys.exit(main())
