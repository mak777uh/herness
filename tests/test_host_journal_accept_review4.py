"""W07B-REVIEW4: host_match binding и hidden unknown-key fail-closed.

Запуск: python tests/test_host_journal_accept_review4.py
Windows и POSIX: 7/7 без N/A. E-0054–E-0057 sealed corpus не изменяется.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import accept, hsj2  # noqa: E402

LINES = [
    "run/start task: найти опору",
    "tool/call search /mnt CLAIMS",
    "tool/result ok /mnt/CLAIMS.md:4: опора",
    "step 1, потрачено 0.00010000",
    "claim/anchored /mnt/CLAIMS.md:4",
    "run/end Опора лежит в /mnt/CLAIMS.md:4",
]
CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn

    return wrap


def clean_records():
    records = [(hsj2.DATA, line) for line in LINES]
    records.append((hsj2.COMMIT, b""))
    parsed, tail, problems = accept.parse_journal(hsj2.journal(records))
    assert not tail and not problems, (tail, problems)
    return parsed


def row(rows: list[tuple[str, bool, str]], name: str) -> tuple[str, bool, str]:
    matches = [item for item in rows if item[0] == name]
    assert len(matches) == 1, (name, rows)
    return matches[0]


@case("host-match-missing-run-visible")
def _():
    ok, rows = accept.check({"require_status": "done", "host_match": True}, clean_records())
    assert not ok, rows
    assert not row(rows, "host_match привязан к host_run")[1], rows


@case("host-match-missing-run-hidden")
def _():
    criteria = {"hidden": {"max_steps": 1}, "host_match": True}
    ok, rows = accept.check(criteria, clean_records(), show_hidden=True)
    assert not ok, rows
    assert not row(rows, "host_match привязан к host_run")[1], rows
    assert row(rows, "скрытая часть критерия")[1], rows


@case("host-match-false-no-run")
def _():
    ok, rows = accept.check({"require_status": "done", "host_match": False}, clean_records())
    assert ok, rows
    assert all(name != "host_match привязан к host_run" for name, _passed, _detail in rows), rows


@case("hidden-unknown-only")
def _():
    ok, rows = accept.check({"hidden": {"typo": True}}, clean_records(), show_hidden=True)
    assert not ok, rows
    assert not row(rows, "скрытая часть критерия")[1], rows


@case("hidden-unknown-with-positive")
def _():
    criteria = {"hidden": {"max_steps": 1, "typo": True}}
    ok, rows = accept.check(criteria, clean_records(), show_hidden=True)
    assert not ok, rows
    hidden = row(rows, "скрытая часть критерия")
    assert not hidden[1], rows
    assert "неизвестное условие typo" in hidden[2], rows


@case("hidden-real-positive")
def _():
    ok, rows = accept.check({"hidden": {"max_steps": 1}}, clean_records(), show_hidden=True)
    assert ok, rows
    assert row(rows, "скрытая часть критерия")[1], rows


@case("hidden-unknown-no-leak")
def _():
    criteria = {"hidden": {"max_steps": 1, "typo": True}}
    ok, rows = accept.check(criteria, clean_records(), show_hidden=False)
    assert not ok, rows
    assert not row(rows, "скрытая часть критерия")[1], rows
    assert all("typo" not in name and "typo" not in detail for name, _passed, detail in rows), rows


def main() -> int:
    assert len(CASES) == 7, len(CASES)
    passed = failed = na = 0
    for name, fn in CASES:
        try:
            result = fn()
            if result == "N/A":
                na += 1
                print(f"[N/A] {name}")
            else:
                passed += 1
                print(f"[ok] {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[FAIL] {name} — {type(exc).__name__}: {exc}")
    print(f"\nhost journal accept review4: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    return 0 if failed == 0 and na == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
