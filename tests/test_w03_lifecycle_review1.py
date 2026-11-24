"""E-0068: непосредственные controls substantive findings независимых W03 review."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from bin import accept, journal_event  # noqa: E402
from test_accept import CRITERIA, OK_RUN, journal_bytes, run  # noqa: E402

SESSION = "11111111-1111-4111-8111-111111111111"
CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def order_events(middle: list[str]) -> list[str]:
    return ["run/start task: x", *middle, "run/end готово"]


def check_order(events: list[str]) -> tuple[bool, list]:
    criteria = {
        "task": "x", "require_status": "done-без-опоры", "max_steps": 8,
        "max_allowance": 0.001, "require_commit": True,
    }
    return run(criteria, events)


def with_tool_result(result: str) -> list[str]:
    events = list(OK_RUN)
    events.insert(-1, "tool/call write /mnt/x текст")
    events.insert(-1, f"tool/result {result}")
    events.insert(-1, "step 2, потрачено 0.00010000")
    return events


def refusal_controls(result: str, expected_accept: bool, expected_status: str) -> None:
    criteria = dict(CRITERIA, tools=["search"], must_call=[], must_not_call=[])
    ok, rows = run(criteria, with_tool_result(result))
    assert ok is expected_accept, rows
    projected = journal_event.project(
        [("tool/call", "write /mnt/x"), ("tool/result", result)], SESSION,
    )
    assert projected[-1]["status"] == expected_status, projected


@case("review1 exact structured grant refusal")
def _():
    refusal_controls(
        "err S6_CLOSURE_BREACH: инструмент write не выдан в этом прогоне", True, "denied",
    )


@case("review1 structured code with wrong reason")
def _():
    refusal_controls(
        "err S6_CLOSURE_BREACH: путь вне корня", False, "error",
    )


@case("review1 structured code with wrong tool")
def _():
    refusal_controls(
        "err S6_CLOSURE_BREACH: инструмент read не выдан в этом прогоне", False, "error",
    )


@case("review1 exact structured refusal with suffix")
def _():
    refusal_controls(
        "err S6_CLOSURE_BREACH: инструмент write не выдан в этом прогоне лишнее", False, "error",
    )


@case("review1 legacy unstructured refusal")
def _():
    refusal_controls(
        "err инструмент write не выдан в этом прогоне", False, "error",
    )


@case("review1 short unknown-cost marker")
def _():
    events = list(OK_RUN)
    events.insert(-1, "step/error не сообщил расход")
    ok, rows = run(CRITERIA, events)
    assert not ok, rows
    assert any("unknown-cost" in detail for _, passed, detail in rows if not passed), rows
    assert accept.check({"task": "x", "require_status": "unknown-cost"},
                        accept.parse_journal(journal_bytes(events))[0])[0]


@case("review1 full unknown-cost marker")
def _():
    events = list(OK_RUN)
    events.insert(-1, "step/error провайдер не сообщил расход: бюджет проверить нельзя")
    ok, rows = run(CRITERIA, events)
    assert not ok, rows
    assert any("unknown-cost" in detail for _, passed, detail in rows if not passed), rows


@case("review1 step before result is invalid")
def _():
    events = order_events(["tool/call read a", "step 1, потрачено 0", "tool/result ok a"])
    ok, rows = check_order(events)
    assert not ok, rows
    assert any("tool/call" in name and not passed for name, passed, _ in rows), rows


@case("review1 step before call is invalid")
def _():
    events = order_events(["step 1, потрачено 0", "tool/call read a", "tool/result ok a"])
    ok, rows = check_order(events)
    assert not ok, rows
    assert any("tool/call" in name and not passed for name, passed, _ in rows), rows


@case("review1 result needs completing step")
def _():
    events = order_events(["tool/call read a", "tool/result ok a"])
    ok, rows = check_order(events)
    assert not ok, rows


@case("review1 duplicate run end is invalid")
def _():
    events = ["run/start task: x", "step 0, потрачено 0", "run/end готово", "run/end снова"]
    ok, rows = check_order(events)
    assert not ok, rows
    assert any("run/end" in detail for _, passed, detail in rows if not passed), rows


@case("review1 work after early run end is invalid")
def _():
    events = [
        "run/start task: x", "tool/call read a", "tool/result ok a",
        "step 1, потрачено 0", "run/end готово",
        "run/start task: x", "tool/call read b", "tool/result ok b",
        "step 2, потрачено 0", "run/end снова",
    ]
    ok, rows = check_order(events)
    assert not ok, rows
    assert any("run/end" in detail for _, passed, detail in rows if not passed), rows


@case("review1 two complete call result step pairs")
def _():
    events = order_events([
        "tool/call read a", "tool/result ok a", "step 1, потрачено 0",
        "tool/call read b", "tool/result ok b", "step 2, потрачено 0",
    ])
    ok, rows = check_order(events)
    assert ok, rows


@case("review1 granted tool success remains accepted")
def _():
    events = order_events(["tool/call read a", "tool/result ok a", "step 1, потрачено 0"])
    criteria = {
        "task": "x", "require_status": "done-без-опоры", "tools": ["read"],
        "max_steps": 4, "max_allowance": 0.001, "require_commit": True,
    }
    ok, rows = run(criteria, events)
    assert ok, rows
    projected = journal_event.project(
        [("tool/call", "read a"), ("tool/result", "ok a")], SESSION,
    )
    assert projected[-1]["status"] == "ok", projected


@case("review1 fresh route is wired to disk proof")
def _():
    source = (ROOT / "core-rs/src/main.rs").read_text(encoding="utf-8")
    fresh = source.split('if mode_text == "loop-bridge" {', 1)[1].split(
        'if mode_text == "loop-bridge-resume" {', 1)[0]
    assert "loop_succeeded_with_journal(" in fresh, "fresh success игнорирует on-disk proof"
    assert "&outcome," in fresh
    assert "return if hs_core::loopmod::loop_succeeded(&outcome)" not in fresh


@case("review1 disk proof contract is fail-closed")
def _():
    source = (ROOT / "core-rs/src/loopmod.rs").read_text(encoding="utf-8")
    helper = source.split("pub fn loop_succeeded_with_journal", 1)
    assert len(helper) == 2, "нет единого fresh disk-proof contract"
    body = helper[1].split("\n}\n", 1)[0]
    assert "loop_succeeded(outcome)" in body
    assert "order_from_journal(journal_path)" in body
    assert "is_empty()" in body


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
    print(f"W03 review1 controls: {len(CASES) - failed}/{len(CASES)} ok; провалов: {failed}")
    return 1 if failed or len(CASES) != 16 else 0


if __name__ == "__main__":
    sys.exit(main())
