"""W07B-REVIEW5: present-but-malformed hidden fail-closed.

Запуск: python tests/test_host_journal_accept_review5.py
Windows и POSIX: 9/9 без N/A. E-0054–E-0059 sealed corpus не изменяется.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
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


def assert_malformed_rejected(hidden, *, show_hidden: bool = False):
    ok, rows = accept.check(
        {"require_status": "done", "hidden": hidden},
        clean_records(),
        show_hidden=show_hidden,
    )
    assert not ok, rows
    assert not row(rows, "скрытая часть критерия")[1], rows
    return rows


@case("hidden-string-visible-positive")
def _():
    rows = assert_malformed_rejected("typo", show_hidden=True)
    assert "hidden" in row(rows, "скрытая часть критерия")[2], rows


@case("hidden-list-visible-positive")
def _():
    assert_malformed_rejected(["max_steps", 1])


@case("hidden-int-visible-positive")
def _():
    assert_malformed_rejected(0)


@case("hidden-bool-visible-positive")
def _():
    assert_malformed_rejected(False)


@case("hidden-null-visible-positive")
def _():
    assert_malformed_rejected(None)


@case("malformed-hidden-no-leak")
def _():
    sentinel = "HIDDEN-SENTINEL-7f13c92e"
    rows = assert_malformed_rejected(sentinel)
    assert all(
        sentinel not in name and sentinel not in detail
        for name, _passed, detail in rows
    ), rows


@case("malformed-hidden-cli-fail")
def _():
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        criterion = directory / "criterion.json"
        journal = directory / "journal.bin"
        criterion.write_text(
            json.dumps({"require_status": "done", "hidden": []}),
            encoding="utf-8",
        )
        journal.write_bytes(hsj2.journal([
            *[(hsj2.DATA, line) for line in LINES],
            (hsj2.COMMIT, b""),
        ]))
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = accept.main([str(criterion), str(journal)])
        assert code != 0, (code, stdout.getvalue(), stderr.getvalue())
        assert "итог: PASS" not in stdout.getvalue(), stdout.getvalue()


@case("empty-hidden-visible-positive")
def _():
    ok, rows = accept.check(
        {"require_status": "done", "hidden": {}},
        clean_records(),
    )
    assert ok, rows
    assert all(name != "скрытая часть критерия" for name, _passed, _detail in rows), rows


@case("valid-hidden-visible-positive")
def _():
    ok, rows = accept.check(
        {"require_status": "done", "hidden": {"max_steps": 1}},
        clean_records(),
        show_hidden=True,
    )
    assert ok, rows
    assert row(rows, "скрытая часть критерия")[1], rows


def main() -> int:
    assert len(CASES) == 9, len(CASES)
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
    print(f"\nhost journal accept review5: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    return 0 if failed == 0 and na == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
