"""Тесты тормоза прогона: потолок останавливает шаг ДО выполнения.

Запуск: python tests/test_budget.py
"""

from __future__ import annotations

import json
import sys
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import budget  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []
TEMP_DIRS: list[Path] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


def make_run(steps: int, seconds: float = 0.0, artifact_bytes: int = 0) -> Path:
    tmp = Path(tempfile.mkdtemp())
    TEMP_DIRS.append(tmp)
    lines = []
    for i in range(steps):
        lines.append(json.dumps({"seq": i, "type": "tool/call", "ts": f"2026-10-29T10:00:{i:02d}+00:00",
                                 "payload": {"arguments": {"command": f"echo {i}"}}}))
    if steps == 0:
        lines.append(json.dumps({"seq": 0, "type": "run/start", "ts": "2026-10-29T10:00:00+00:00"}))
    (tmp / "events.jsonl").write_text("\n".join(lines), encoding="utf-8")
    if artifact_bytes:
        (tmp / "artifacts").mkdir()
        (tmp / "artifacts" / "a.txt").write_bytes(b"x" * artifact_bytes)
    return tmp


@case("пустой прогон не превышает ничего", False)
def _():
    run = make_run(0)
    ok, reason = budget.exceeded(run, max_steps=5, max_seconds=60, max_bytes=100)
    assert not ok, reason


@case("превышение шагов обнаруживается", False)
def _():
    run = make_run(5)
    ok, reason = budget.exceeded(run, max_steps=5)
    assert ok and "шагов 5" in reason, reason


@case("превышение объёма обнаруживается", False)
def _():
    run = make_run(1, artifact_bytes=2048)
    ok, reason = budget.exceeded(run, max_bytes=1024)
    assert ok and "байт 2048" in reason, reason


@case("потолок 0 значит «без потолка»", False)
def _():
    run = make_run(1000)
    ok, _reason = budget.exceeded(run, max_steps=0, max_seconds=0, max_bytes=0)
    assert not ok


@case("использование считается по журналу", False)
def _():
    run = make_run(3)
    current = budget.usage(run)
    assert current["steps"] == 3, current


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
    for leftover in TEMP_DIRS:
        shutil.rmtree(leftover, ignore_errors=True)
    print(f"\nбюджет: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
