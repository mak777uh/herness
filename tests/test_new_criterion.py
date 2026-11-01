"""Тесты шаблона критерия: он обязан собирать то, что приёмка понимает и что не ломает чистый прогон."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import accept, new_criterion  # noqa: E402

CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


@case("шаблон собирает только известные приёмке ключи")
def _():
    criteria = new_criterion.build("t", r"C-\d{4}")
    unknown = set(criteria) - accept.KNOWN_KEYS
    assert not unknown, unknown


@case("шаблон ставит обязательные условия по умолчанию")
def _():
    criteria = new_criterion.build("t", r"C-\d{4}")
    assert criteria["require_status"] == "done"
    assert criteria["require_commit"] is True
    assert "claim/anchored" in criteria["require_events"]
    assert criteria["max_repeat_ratio"] == 0.35
    assert criteria["max_calls_without_claim"] == 10
    assert criteria["anchor_regex"] == r"C-\d{4}"


@case("выдача инструментов и запрет записи не противоречат друг другу")
def _():
    with_write = new_criterion.build("t", r"C-\d{4}", tools=["read", "write"])
    assert with_write["must_not_call"] == []
    without_write = new_criterion.build("t", r"C-\d{4}", tools=["read", "search"])
    assert without_write["must_not_call"] == ["write"]


@case("хостовый прогон включает сверку содержимого")
def _():
    criteria = new_criterion.build("t", r"C-\d{4}", host_run="run-1")
    assert criteria["host_run"] == "run-1" and criteria["host_match"] is True


@case("готовый критерий пропускает честный прогон")
def _():
    journal = ROOT / "runs" / "accept" / "journal-default-threshold.bin"
    if not journal.exists():
        return  # журнал — рабочий артефакт, в репозиторий не едет
    criteria = new_criterion.build(
        "найти statistics", r"C-\d{4}", tools=["search", "read", "list"], scope=["только CLAIMS.md"]
    )
    records, _tail, _problems = accept.parse_journal(journal.read_bytes())
    ok, rows = accept.check(criteria, records)
    assert ok, [row for row in rows if not row[1]]


@case("CLI пишет файл, который читается приёмкой")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "c.json"
        code = new_criterion.main(["--task", "t", "--anchor", r"C-\d{4}", "--out", str(out)])
        assert code == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert set(data) <= accept.KNOWN_KEYS


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
    print(f"\nшаблон критерия: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
