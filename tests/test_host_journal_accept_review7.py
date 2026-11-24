"""W07B-REVIEW7: Unicode-safe criterion и строгий duplicate oracle.

Запуск: python tests/test_host_journal_accept_review7.py
Windows и POSIX: 9/9 без N/A. E-0054–E-0061 sealed corpus не изменяется.
"""

from __future__ import annotations

import io
import sys
import tempfile
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from bin import accept, host_journal, hsj2  # noqa: E402
import test_host_journal_authority as authority  # noqa: E402

RUN = "w07b-review7-combined"
SESSION = authority.SESSION
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


def assert_json_rejected(raw: str, diagnostic: str) -> tuple[str, str]:
    """Loader refusal, а не обычный semantic FAIL по принятому критерию."""
    code, stdout, stderr = cli(raw)
    output = stdout + stderr
    assert code == 2, (code, output)
    assert diagnostic in stderr, (diagnostic, output)
    assert "итог: PASS" not in output, output
    assert "Traceback" not in output, output
    return stdout, stderr


def first_key_wins(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        result.setdefault(key, value)
    return result


def last_key_wins(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        result[key] = value
    return result


def assert_oracle_catches(raw: str, resolver) -> None:
    with patch.object(accept, "_criterion_pairs", resolver):
        try:
            assert_json_rejected(raw, "повторяющийся JSON ключ")
        except AssertionError:
            return
    raise AssertionError("oracle приняла semantic FAIL вместо loader refusal")


@case("visible-task-surrogate")
def _():
    stdout, stderr = assert_json_rejected(
        r'{"require_status":"done","task":"VISIBLE-\ud800"}',
        "недопустимую Unicode",
    )
    assert "VISIBLE-" not in stdout + stderr


@case("visible-status-surrogate")
def _():
    stdout, stderr = assert_json_rejected(
        r'{"require_status":"done\ud800"}',
        "недопустимую Unicode",
    )
    assert "done" not in stdout + stderr


@case("hidden-task-surrogate-no-leak")
def _():
    stdout, stderr = assert_json_rejected(
        r'{"require_status":"done","hidden":{"task":"HIDDEN-\ud800"}}',
        "недопустимую Unicode",
    )
    output = stdout + stderr
    assert "HIDDEN-" not in output
    assert r"\ud800" not in output


@case("surrogate-key-no-traceback")
def _():
    stdout, stderr = assert_json_rejected(
        r'{"require_status":"done","\ud800":1}',
        "недопустимую Unicode",
    )
    assert r"\ud800" not in stdout + stderr


@case("duplicate-visible-threshold-reverse")
def _():
    assert_json_rejected(
        '{"require_status":"done","max_steps":4,"max_steps":0}',
        "повторяющийся JSON ключ",
    )


@case("duplicate-oracle-first-key-wins")
def _():
    assert_oracle_catches(
        '{"require_status":"done","max_steps":0,"max_steps":4}',
        first_key_wins,
    )


@case("duplicate-oracle-last-key-wins")
def _():
    assert_oracle_catches(
        '{"require_status":"done","max_steps":4,"max_steps":0}',
        last_key_wins,
    )


@case("full-combined-positive")
def _():
    old_default = host_journal.DEFAULT_DIR
    with tempfile.TemporaryDirectory() as tmp:
        host_journal.DEFAULT_DIR = Path(tmp) / "journal"
        try:
            events = [tuple(line.split(" ", 1)) for line in LINES]
            for event in authority.project(events):
                host_journal.append(RUN, authority.canonical(event).decode("utf-8"))
            criteria = {
                "task": "найти опору",
                "comment": "полный combined review7",
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
                "host_run": RUN,
                "host_session": SESSION,
                "host_match": True,
                "hidden": {"max_steps": 1},
            }
            assert len(criteria) == 19, criteria.keys()
            ok, rows = accept.check(criteria, clean_records(), show_hidden=True)
            assert ok, rows
            assert row(rows, "скрытая часть критерия")[1]
            assert any(name.startswith("хост подтвердил прогон") and passed
                       for name, passed, _detail in rows), rows
            assert any("совпадает с хостовым" in name and passed
                       for name, passed, _detail in rows), rows
        finally:
            host_journal.DEFAULT_DIR = old_default


@case("valid-unicode-positive")
def _():
    code, stdout, stderr = cli(
        '{"require_status":"done","task":"найти опору \\ud83d\\ude00",'
        '"comment":"корректный Unicode"}'
    )
    output = stdout + stderr
    assert code == 0, output
    assert "итог: PASS" in stdout, output
    assert "Traceback" not in output, output


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
    print(f"\nhost journal accept review7: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    return 0 if failed == 0 and na == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
