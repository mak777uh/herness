"""W07B-REVIEW6: strict criterion JSON/schema fail-closed.

Запуск: python tests/test_host_journal_accept_review6.py
Windows и POSIX: 16/16 без N/A. E-0054–E-0060 sealed corpus не изменяется.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import traceback
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
JOURNAL = hsj2.journal([
    *[(hsj2.DATA, line) for line in LINES],
    (hsj2.COMMIT, b""),
])
CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def clean_records():
    parsed, tail, problems = accept.parse_journal(JOURNAL)
    assert not tail and not problems, (tail, problems)
    return parsed


def row(rows: list[tuple[str, bool, str]], name: str) -> tuple[str, bool, str]:
    matches = [item for item in rows if item[0] == name]
    assert len(matches) == 1, (name, rows)
    return matches[0]


def cli(raw: str) -> tuple[int | None, str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        criterion = directory / "criterion.json"
        journal = directory / "journal.bin"
        criterion.write_text(raw, encoding="utf-8")
        journal.write_bytes(JOURNAL)
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = None
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = accept.main([str(criterion), str(journal)])
            except Exception:  # noqa: BLE001
                stderr.write(traceback.format_exc())
        return code, stdout.getvalue(), stderr.getvalue()


def assert_cli_rejected(raw: str) -> tuple[str, str]:
    code, stdout, stderr = cli(raw)
    assert code != 0, (code, stdout, stderr)
    assert "итог: PASS" not in stdout, stdout
    return stdout, stderr


def assert_hidden_no_leak(raw: str, sentinel: str) -> None:
    stdout, stderr = assert_cli_rejected(raw)
    output = stdout + stderr
    assert sentinel not in output, output
    assert "Traceback" not in output, output


@case("nested-hidden-string")
def _():
    ok, rows = accept.check(
        {"hidden": {"max_steps": 1, "hidden": "SENTINEL-NESTED"}},
        clean_records(),
        show_hidden=True,
    )
    assert not ok, rows
    assert not row(rows, "скрытая часть критерия")[1], rows


@case("nested-hidden-object")
def _():
    ok, rows = accept.check(
        {"hidden": {"max_steps": 1, "hidden": {"max_steps": 1}}},
        clean_records(),
        show_hidden=True,
    )
    assert not ok, rows
    assert not row(rows, "скрытая часть критерия")[1], rows


@case("duplicate-hidden-malformed-first")
def _():
    assert_cli_rejected(
        '{"require_status":"done","hidden":"SENTINEL-DUP","hidden":{}}'
    )


@case("duplicate-hidden-malformed-last")
def _():
    assert_cli_rejected(
        '{"require_status":"done","hidden":{},"hidden":"SENTINEL-DUP"}'
    )


@case("duplicate-visible-threshold")
def _():
    assert_cli_rejected(
        '{"require_status":"done","max_steps":0,"max_steps":4}'
    )


@case("hidden-max-steps-infinity")
def _():
    assert_cli_rejected(
        '{"require_status":"done","hidden":{"max_steps":Infinity}}'
    )


@case("hidden-max-steps-overflow")
def _():
    assert_cli_rejected(
        '{"require_status":"done","hidden":{"max_steps":1e309}}'
    )


@case("hidden-max-repeat-nan")
def _():
    assert_cli_rejected(
        '{"require_status":"done","hidden":{"max_repeat_ratio":NaN}}'
    )


@case("hidden-min-objects-no-leak")
def _():
    sentinel = "HIDDEN-SENTINEL-CONDITION"
    raw = json.dumps({"require_status": "done", "hidden": {"min_objects": sentinel}})
    assert_hidden_no_leak(raw, sentinel)


@case("hidden-max-repeat-no-leak")
def _():
    sentinel = "HIDDEN-SENTINEL-RATIO"
    raw = json.dumps({"require_status": "done", "hidden": {"max_repeat_ratio": sentinel}})
    assert_hidden_no_leak(raw, sentinel)


@case("hidden-invalid-regex-no-leak")
def _():
    sentinel = "HIDDEN-SENTINEL-REGEX["
    raw = json.dumps({"require_status": "done", "hidden": {"anchor_regex": sentinel}})
    assert_hidden_no_leak(raw, sentinel)


@case("hidden-max-steps-bool")
def _():
    ok, rows = accept.check(
        {"require_status": "done", "hidden": {"max_steps": True}},
        clean_records(),
    )
    assert not ok, rows
    assert not row(rows, "скрытая часть критерия")[1], rows


@case("visible-max-steps-string")
def _():
    ok, rows = accept.check(
        {"require_status": "done", "max_steps": "SENTINEL-VISIBLE"},
        clean_records(),
    )
    assert not ok, rows


@case("valid-hidden-positive")
def _():
    ok, rows = accept.check(
        {"require_status": "done", "hidden": {"max_steps": 1}},
        clean_records(),
        show_hidden=True,
    )
    assert ok, rows
    assert row(rows, "скрытая часть критерия")[1], rows


@case("valid-combined-positive")
def _():
    criteria = {
        "task": "найти опору",
        "comment": "валидный combined control",
        "scope": ["искать в /mnt"],
        "require_status": "done",
        "must_call": ["search"],
        "must_not_call": ["write"],
        "anchor_regex": r"CLAIMS\.md:\d+",
        "max_steps": 4,
        "max_allowance": 0.001,
        "require_commit": True,
        "require_events": ["claim/anchored"],
        "min_objects": 1,
        "tools": ["search"],
        "max_repeat_ratio": 0.35,
        "max_calls_without_claim": 3,
        "hidden": {"max_steps": 1},
    }
    ok, rows = accept.check(criteria, clean_records(), show_hidden=True)
    assert ok, rows
    assert row(rows, "скрытая часть критерия")[1], rows


@case("empty-hidden-positive")
def _():
    ok, rows = accept.check(
        {"require_status": "done", "hidden": {}},
        clean_records(),
    )
    assert ok, rows
    assert all(name != "скрытая часть критерия" for name, _passed, _detail in rows), rows


def main() -> int:
    assert len(CASES) == 16, len(CASES)
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
    print(f"\nhost journal accept review6: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    return 0 if failed == 0 and na == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
