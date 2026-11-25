"""E-0070: balanced W03 lifecycle oracle and acceptance-bypass metakontrol.

Production is unchanged. Each invalid stream is otherwise a valid call→result→step
lifecycle, so removing its guard must produce both an empty helper and acceptance PASS.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from bin import accept, seal as method_seal  # noqa: E402
from test_accept import journal_bytes  # noqa: E402

CASES: list[tuple[str, callable]] = []

WRONG_FIRST = [
    "note перед", "run/start task: x", "tool/call read a",
    "tool/result ok a", "step 1, потрачено 0", "run/end готово",
]
DUPLICATE_END = [
    "run/start task: x", "tool/call read a", "tool/result ok a",
    "step 1, потрачено 0", "run/end готово", "run/end снова",
]
AFTER_END = [
    "run/start task: x", "tool/call read a", "tool/result ok a",
    "step 1, потрачено 0", "run/end готово", "note после",
]
NO_END = [
    "run/start task: x", "tool/call read a", "tool/result ok a",
    "step 1, потрачено 0",
]
VALID = [
    "run/start task: x", "tool/call read a", "tool/result ok a",
    "step 1, потрачено 0", "tool/call read b", "tool/result ok b",
    "step 2, потрачено 0", "run/end готово",
]

FIRST_GUARD = (
    'if evs[0][0] != "run/start":\n'
    '        problems.append(f"первое событие {evs[0][0]}, а не run/start")'
)
END_GUARDS = (
    '        if ended:\n'
    '            problems.append(f"событие {kind} после run/end")\n'
    '        if kind == "run/end":\n'
    '            if ended:\n'
    '                problems.append("повторный run/end")\n'
    '            ended = True'
)
AFTER_END_GUARD = (
    '        if ended:\n'
    '            problems.append(f"событие {kind} после run/end")'
)


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def event_pairs(lines: list[str]) -> list[tuple[str, str]]:
    return [tuple(line.partition(" ")[::2]) for line in lines]


def records(lines: list[str]):
    return accept.parse_journal(journal_bytes(lines))[0]


def lifecycle_problems(lines: list[str]) -> list[str]:
    return accept.tool_pairing_problems(accept.events(records(lines)))


def done_criteria() -> dict:
    return {
        "task": "x", "require_status": "done-без-опоры", "max_steps": 8,
        "max_allowance": 0.001, "require_commit": True,
    }


def assert_exact(lines: list[str], diagnostic: str) -> None:
    problems = lifecycle_problems(lines)
    assert diagnostic in problems, (diagnostic, problems)
    ok, rows = accept.check(done_criteria(), records(lines))
    assert not ok, rows


def mutated_pairing(old: str, new: str):
    source = inspect.getsource(accept.tool_pairing_problems)
    assert old in source, "metakontrol не нашёл production-ветку"
    namespace: dict = {}
    exec(source.replace(old, new, 1), namespace)  # noqa: S102 - in-memory mutation
    return namespace["tool_pairing_problems"]


def acceptance_with_pairing(lines: list[str], pairing) -> bool:
    original = accept.tool_pairing_problems
    try:
        accept.tool_pairing_problems = pairing
        ok, rows = accept.check(done_criteria(), records(lines))
        assert ok, rows
        return True
    finally:
        accept.tool_pairing_problems = original


@case("review3 balanced wrong-first is rejected")
def _():
    assert_exact(WRONG_FIRST, "первое событие note, а не run/start")


@case("review3 wrong-first guard removal reproduces acceptance bypass")
def _():
    fn = mutated_pairing(FIRST_GUARD, FIRST_GUARD.replace('if evs[0][0] != "run/start":', "if False:"))
    assert fn(event_pairs(WRONG_FIRST)) == []
    assert acceptance_with_pairing(WRONG_FIRST, fn)


@case("review3 balanced duplicate-end is rejected")
def _():
    assert_exact(DUPLICATE_END, "повторный run/end")


@case("review3 post-end guards removal reproduces duplicate acceptance bypass")
def _():
    fn = mutated_pairing(END_GUARDS, '        if kind == "run/end":\n            ended = True')
    assert fn(event_pairs(DUPLICATE_END)) == []
    assert acceptance_with_pairing(DUPLICATE_END, fn)


@case("review3 balanced after-end event is rejected")
def _():
    assert_exact(AFTER_END, "событие note после run/end")


@case("review3 after-end guard removal reproduces acceptance bypass")
def _():
    fn = mutated_pairing(AFTER_END_GUARD, AFTER_END_GUARD.replace("if ended:", "if False:"))
    assert fn(event_pairs(AFTER_END)) == []
    assert acceptance_with_pairing(AFTER_END, fn)


@case("review3 balanced missing-end remains no-done")
def _():
    assert lifecycle_problems(NO_END) == []
    ok, rows = accept.check({"task": "x", "require_status": "no-done"}, records(NO_END))
    assert ok, rows
    done_ok, done_rows = accept.check({"task": "x", "require_status": "done"}, records(NO_END))
    assert not done_ok, done_rows


@case("review3 valid lifecycle remains accepted")
def _():
    assert lifecycle_problems(VALID) == []
    ok, rows = accept.check(done_criteria(), records(VALID))
    assert ok, rows


@case("review3 sealed baseline and authorized successor hashes are unchanged")
def _():
    prereg_path = ROOT / "lab/prereg/W03-LIFECYCLE-R1-REVIEW3.json"
    correction_path = ROOT / "lab/prereg/W03-LIFECYCLE-R1-REVIEW3-BASELINE-CORRECTION.json"
    successor_correction_path = ROOT / "lab/prereg/W03-REVIEW3-SUCCESSOR-BASELINE-R1.json"
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    successor_correction = json.loads(successor_correction_path.read_text(encoding="utf-8"))

    # E-0091 разрешает successor только для loopmod.rs и только из sealed E-0090.
    # Исторические E-0070/E-0072 не перепечатываются и остаются исходным baseline.
    successor_path = ROOT / successor_correction["authorized_successor"]["prereg"]
    sealed, message = method_seal.verify(successor_path)
    assert sealed, message
    successor = json.loads(successor_path.read_text(encoding="utf-8"))
    successor_hash = successor["baseline_sha256"]["core-rs/src/loopmod.rs"]
    assert successor_hash == successor_correction["authorized_successor"]["sha256"]
    for path in (prereg_path, correction_path, successor_path):
        sealed, message = method_seal.verify(path)
        assert sealed, message
    for name, expected in successor_correction["baseline_sha256"].items():
        if name == "tests/test_w03_lifecycle_review3.py":
            continue  # этот instrument меняется по E-0091; его baseline запечатан в prereg
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        assert actual == expected, (name, expected, actual)

    baseline = dict(prereg["baseline_sha256"])
    baseline.update(correction["corrected_baseline_sha256"])
    for name, expected in baseline.items():
        if name == "core-rs/src/loopmod.rs":
            expected = successor_hash
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        assert actual == expected, (name, expected, actual)


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
    print(f"W03 review3 controls: {len(CASES) - failed}/{len(CASES)} ok; провалов: {failed}")
    return 1 if failed or len(CASES) != 9 else 0


if __name__ == "__main__":
    sys.exit(main())
