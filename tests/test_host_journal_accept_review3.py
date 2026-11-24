"""W07B-REVIEW3: metadata-only PASS и exact UTF-8 direct-caller control.

Запуск: python tests/test_host_journal_accept_review3.py
Windows и POSIX: 7/7 без N/A. E-0054/E-0055/E-0056 sealed corpus не изменяется.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import accept, hsj2, judge_metrics, verify_answers  # noqa: E402

LINES = [
    "run/start task: найти опору",
    "tool/call search /mnt CLAIMS",
    "tool/result ok /mnt/CLAIMS.md:4: опора",
    "step 1, потрачено 0.00010000",
    "claim/anchored /mnt/CLAIMS.md:4",
    "run/end Опора лежит в /mnt/CLAIMS.md:4",
]
PLAIN_CRITERIA = {
    "task": "найти опору",
    "require_status": "done",
    "anchor_regex": r"CLAIMS\.md:\d+",
    "require_commit": True,
}
REAL_METRICS = ROOT / "research" / "outputs" / "acceptance-metrics.txt"
CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn

    return wrap


def data_journal(lines: list[str], *, commit: bytes = b"") -> bytes:
    records = [(hsj2.DATA, line) for line in lines]
    records.append((hsj2.COMMIT, commit))
    return hsj2.journal(records)


def row(rows: list[tuple[str, bool, str]], name: str) -> tuple[str, bool, str]:
    matches = [item for item in rows if item[0] == name]
    assert len(matches) == 1, (name, rows)
    return matches[0]


def empty_records():
    records, tail, problems = accept.parse_journal(hsj2.journal([]))
    assert not tail and not problems, (tail, problems)
    assert records.complete
    return records


def assert_metadata_only(criteria: dict) -> None:
    ok, rows = accept.check(criteria, empty_records())
    assert not ok, f"metadata-only criterion принят: {criteria}, rows={rows}"
    assert not row(rows, "есть содержательная проверка")[1], rows
    assert row(rows, "журнал прочитан полностью")[1], rows


@case("metadata-task-only")
def _():
    assert_metadata_only({"task": "x"})


@case("metadata-comment-only")
def _():
    assert_metadata_only({"comment": "x"})


@case("metadata-host-match-only")
def _():
    assert_metadata_only({"host_match": True})


@case("hidden-only-substantive")
def _():
    records, tail, problems = accept.parse_journal(data_journal(LINES))
    assert not tail and not problems, (tail, problems)
    ok, rows = accept.check({"hidden": {"max_steps": 1}}, records, show_hidden=True)
    assert ok, rows
    assert row(rows, "скрытая часть критерия")[1], rows
    assert row(rows, "журнал прочитан полностью")[1], rows


@case("exact-utf8-direct-callers")
def _():
    clean = data_journal(LINES)
    damaged = clean + hsj2.frame(8, hsj2.DATA, b"step 2\xff")
    records, tail, problems = accept.parse_journal(damaged)
    assert tail > 0 and problems, (tail, problems)
    assert any("invalid UTF-8" in problem for problem in problems), problems
    ok, rows = accept.check(PLAIN_CRITERIA, records)
    assert not ok, rows
    assert not row(rows, "журнал прочитан полностью")[1], rows

    before = hashlib.sha256(REAL_METRICS.read_bytes()).digest()
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        journal = directory / "p27-probe.bin"
        journal.write_bytes(damaged)
        criterion = directory / "probe.json"
        criterion.write_text(json.dumps(PLAIN_CRITERIA, ensure_ascii=False), encoding="utf-8")

        old = (judge_metrics.ROOT, judge_metrics.JOURNALS, judge_metrics.INDEX,
               judge_metrics.all_criteria, judge_metrics.musique_order)
        judge_metrics.ROOT = directory
        judge_metrics.JOURNALS = directory
        judge_metrics.INDEX = directory / "missing-index.json"
        judge_metrics.all_criteria = lambda: {"probe": PLAIN_CRITERIA}
        judge_metrics.musique_order = lambda: []
        output = io.StringIO()
        try:
            with redirect_stdout(output):
                code = judge_metrics.main()
        finally:
            (judge_metrics.ROOT, judge_metrics.JOURNALS, judge_metrics.INDEX,
             judge_metrics.all_criteria, judge_metrics.musique_order) = old
        assert code == 0, output.getvalue()
        assert re.search(r"probe\s+1\s+0\s+0\.00", output.getvalue()), output.getvalue()

        output = io.StringIO()
        with redirect_stdout(output):
            code = verify_answers.main([str(criterion), str(journal)])
        assert code == 0, output.getvalue()
        assert "принятых прогонов нет" in output.getvalue(), output.getvalue()
    after = hashlib.sha256(REAL_METRICS.read_bytes()).digest()
    assert after == before, "real acceptance-metrics.txt changed during direct-caller control"


@case("clean-positive")
def _():
    records, tail, problems = accept.parse_journal(data_journal(LINES))
    assert not tail and not problems, (tail, problems)
    ok, rows = accept.check(PLAIN_CRITERIA, records)
    assert ok, rows
    assert row(rows, "журнал прочитан полностью")[1], rows


@case("cli-no-content")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        journal = directory / "empty.bin"
        journal.write_bytes(hsj2.journal([]))
        criterion = directory / "criterion.json"
        criterion.write_text(json.dumps({"task": "x"}), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            code = accept.main([str(criterion), str(journal)])
        assert code == 1, (code, output.getvalue())
        assert "итог: FAIL" in output.getvalue(), output.getvalue()
        assert "итог: PASS" not in output.getvalue(), output.getvalue()


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
    print(f"\nhost journal accept review3: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    return 0 if failed == 0 and na == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
