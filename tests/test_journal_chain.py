"""Тесты цепочки журнала: подмена и удаление событий обязаны быть видны."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin.verify_journal import verify_run  # noqa: E402
from core.journal import Journal  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


def make_run(directory: Path) -> Path:
    journal = Journal(directory)
    journal.run_start("тест", model="mock")
    journal.event("tool/call", {"name": "shell", "arguments": {"command": "echo 1"}})
    journal.event("tool/result", {"ok": True})
    journal.run_end("done")
    journal.close()
    return directory


@case("чистая цепочка проходит", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = make_run(Path(tmp) / "run")
        report = verify_run(directory)
        assert report.ok and not report.legacy, report


@case("правка события ломает цепочку", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = make_run(Path(tmp) / "run")
        path = directory / "events.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        event = json.loads(lines[1])
        event["payload"]["command"] = "echo 2"
        lines[1] = json.dumps(event, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = verify_run(directory)
        assert not report.ok and "хеш" in report.reason, report


@case("удаление события ломает цепочку", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = make_run(Path(tmp) / "run")
        path = directory / "events.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        del lines[2]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = verify_run(directory)
        assert not report.ok, report


@case("старый журнал без цепочки считается legacy, а не ошибкой", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp) / "run"
        directory.mkdir()
        (directory / "events.jsonl").write_text(
            json.dumps({"seq": 1, "type": "run/start", "payload": {}}, ensure_ascii=False) + "\n",
            encoding="utf-8")
        report = verify_run(directory)
        assert report.ok and report.legacy, report


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
    print(f"\nжурнал: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
