"""W03: общий lifecycle corpus, ложный PASS и one-shot batch semantics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from bin import accept, journal_batch, journal_event  # noqa: E402
from test_accept import CRITERIA, OK_RUN, journal_bytes, run  # noqa: E402

VECTOR = json.loads((ROOT / "tests/vectors/w03-lifecycle.json").read_text(encoding="utf-8"))
CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def status_rows(events: list[str], expected: str) -> list:
    records = accept.parse_journal(journal_bytes(events))[0]
    return accept.check({"task": "x", "require_status": expected}, records)[1]


def base_with_result(result: str) -> list[str]:
    events = list(OK_RUN)
    events.insert(-1, "tool/call write /mnt/x текст")
    events.insert(-1, f"tool/result {result}")
    events.insert(-1, "step 2, потрачено 0.00010000")
    return events


for row in VECTOR["statuses"]:
    @case(f"shared status: {row['id']}")
    def _(row=row):
        rows = status_rows(row["events"], row["expect"])
        assert all(ok for _, ok, _ in rows), rows

for row in VECTOR["pairing"]:
    @case(f"strict pairing: {row['id']}")
    def _(row=row):
        events = [event for event in row["events"] if event != "run/start"]
        events.insert(0, "run/start task: x")
        projected = [
            event.partition(" ")[::2] for event in events
        ]
        if row["valid"]:
            journal_event.project(projected, "11111111-1111-4111-8111-111111111111")
        elif row["id"] != "step-mismatch":
            try:
                journal_event.project(projected, "11111111-1111-4111-8111-111111111111")
            except journal_event.EventError:
                pass
            else:
                raise AssertionError("host projection приняла нарушение pairing")
        if row["valid"]:
            ok, rows = run({"task": "x", "require_status": "done-без-опоры"}, events)
            assert ok, rows
        else:
            ok, rows = run({"task": "x", "require_status": "done-без-опоры"}, events)
            assert not ok, rows
            assert any("tool/call" in name and not passed for name, passed, _ in rows), rows

for row in VECTOR["authority"]:
    @case(f"structured authority: {row['id']}")
    def _(row=row):
        criteria = dict(CRITERIA, tools=["search", *row["granted"]], must_call=[], must_not_call=[])
        ok, rows = run(criteria, base_with_result(row["result"]))
        assert ok == row["accepted"], rows
        if not row["accepted"]:
            assert any("вне выдачи" in detail for _, passed, detail in rows if not passed), rows
        projection = journal_event.project(
            [("tool/call", "write /mnt/x"), ("tool/result", row["result"])],
            "11111111-1111-4111-8111-111111111111",
        )
        expected_status = "denied" if row["id"] == "structured-refusal" else (
            "ok" if row["result"].startswith("ok") else "error"
        )
        assert projection[-1]["status"] == expected_status, projection

for row in VECTOR["budget"]:
    @case(f"known cost: {row['id']}")
    def _(row=row):
        events = list(OK_RUN)
        cost = row["cost"]
        events[3] = f"step 1, потрачено {cost}" if cost is not None else "step 1"
        criteria = dict(CRITERIA, max_allowance=row["allowance"])
        ok, rows = run(criteria, events)
        assert ok == row["accepted"], rows


@case("unknown-cost не меняет anchored done на PASS")
def _():
    events = list(OK_RUN)
    events.insert(-1, "step/error провайдер не сообщил расход: бюджет проверить нельзя")
    ok, rows = run(CRITERIA, events)
    assert not ok, rows
    assert any("unknown-cost" in detail for _, passed, detail in rows if not passed), rows


@case("batch exception и error возвращают FAIL")
def _():
    assert journal_batch.batch_exit_code([{"status": "error", "error": "boom"}]) == 1
    assert journal_batch.batch_exit_code([{"status": "done"}, {"status": "error"}]) == 1
    assert journal_batch.batch_exit_code([{"status": "done"}]) == 0


@case("fresh bridge возвращается, resume остаётся интерактивным")
def _():
    source = (ROOT / "core-rs/src/main.rs").read_text(encoding="utf-8")
    fresh = source.split('if mode_text == "loop-bridge" {', 1)[1].split('if mode_text == "loop-bridge-resume" {', 1)[0]
    resume = source.split('if mode_text == "loop-bridge-resume" {', 1)[1].split('if mode_text == "loop-resume" {', 1)[0]
    assert "loop_succeeded_with_journal(" in fresh
    assert "&outcome," in fresh
    assert "return if hs_core::loopmod::loop_succeeded(&outcome)" not in fresh
    assert "return ExitCode::FAILURE;" in fresh
    assert "hs-core: система жива, жду" not in fresh
    assert "hs-core: система жива, жду" in resume
    assert "thread::sleep" in resume


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
    print(f"W03 controls: {len(CASES) - failed}/{len(CASES)} ok; провалов: {failed}")
    return 1 if failed or len(CASES) != 32 else 0


if __name__ == "__main__":
    sys.exit(main())
