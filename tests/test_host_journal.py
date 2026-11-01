"""Тесты хостового журнала: цепочка должна ловить подделку, а не быть украшением."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import host_journal  # noqa: E402

CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


@case("цепочка растёт и проверяется")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for index in range(3):
            host_journal.append("run-1", f"событие {index}", directory)
        good, problems = host_journal.verify("run-1", directory)
        assert good == 3, (good, problems)
        assert problems == [], problems


@case("подмена события ломает проверку")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("run-2", "run/start task: честная", directory)
        host_journal.append("run-2", "tool/call read a.md", directory)
        path = directory / "run-2.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[0])
        entry["event"] = "run/start task: подделанная"
        lines[0] = json.dumps(entry, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        good, problems = host_journal.verify("run-2", directory)
        assert good == 0 and problems, (good, problems)
        assert "изменена" in problems[0], problems


@case("выкинутая запись ломает цепочку prev")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for index in range(3):
            host_journal.append("run-3", f"событие {index}", directory)
        path = directory / "run-3.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
        good, problems = host_journal.verify("run-3", directory)
        assert good == 1 and problems, (good, problems)
        assert "prev" in problems[0], problems


@case("дописывание идёт за последней записью, а не поверх")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        first = host_journal.append("run-4", "a", directory)
        second = host_journal.append("run-4", "b", directory)
        assert first["seq"] == 1 and second["seq"] == 2
        assert second["prev"] == first["sha256"]
        good, problems = host_journal.verify("run-4", directory)
        assert good == 2 and problems == []


@case("чужого журнала нет — это проблема, а не пустой успех")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        good, problems = host_journal.verify("нет-такого", Path(tmp))
        assert good == 0 and problems, (good, problems)


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            ok_case = True
        except AssertionError:
            ok_case = False
        failed += 0 if ok_case else 1
        print(f"[{'ok' if ok_case else 'FAIL'}] {name}")
    print(f"\nжурнал хоста: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
