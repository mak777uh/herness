"""W07B-REVIEW2: damaged tail не может дать PASS через прямой accept.check().

Запуск: python tests/test_host_journal_accept_integrity.py
Windows и POSIX: 6/6 без N/A. E-0054/E-0055 sealed corpus не изменяется.
"""

from __future__ import annotations

import io
import json
import re
import sys
import tempfile
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import accept, host_journal, hsj2, journal_event, judge_metrics, verify_answers  # noqa: E402

SESSION = "11111111-1111-4111-8111-111111111111"
RUN = "accept-integrity-review2"
LINES = [
    "run/start task: найти опору",
    "tool/call search /mnt CLAIMS",
    "tool/result ok /mnt/CLAIMS.md:4: опора",
    "step 1, потрачено 0.00010000",
    "claim/anchored /mnt/CLAIMS.md:4",
    "run/end Опора лежит в /mnt/CLAIMS.md:4",
]
HOST_CRITERIA = {"host_run": RUN, "host_session": SESSION, "host_match": True}
PLAIN_CRITERIA = {
    "task": "найти опору",
    "require_status": "done",
    "anchor_regex": r"CLAIMS\.md:\d+",
    "require_commit": True,
}
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


@contextmanager
def host_projection(lines: list[str]):
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp) / "journal"
        old_default = host_journal.DEFAULT_DIR
        host_journal.DEFAULT_DIR = directory
        try:
            for event in journal_event.project_payloads(lines, SESSION):
                payload = journal_event.canonical(event).decode("utf-8")
                host_journal.append(RUN, payload, directory)
            yield directory
        finally:
            host_journal.DEFAULT_DIR = old_default


def row(rows: list[tuple[str, bool, str]], name: str) -> tuple[str, bool, str]:
    matches = [item for item in rows if item[0] == name]
    assert len(matches) == 1, (name, rows)
    return matches[0]


def assert_damaged(data: bytes, host_lines: list[str]) -> None:
    with host_projection(host_lines):
        records, tail, problems = accept.parse_journal(data)
        ok, rows = accept.check(HOST_CRITERIA, records, show_hidden=True)
        assert tail > 0 and problems, (tail, problems)
        assert not ok, f"damaged journal принят: tail={tail}, problems={problems}, rows={rows}"
        assert not row(rows, "журнал комнаты совпадает с хостовым")[1], rows
        assert not row(rows, "журнал прочитан полностью")[1], rows


@case("trailing-invalid-utf8-data")
def _():
    first = hsj2.frame(1, hsj2.DATA, LINES[0].encode("utf-8"))
    invalid = hsj2.frame(2, hsj2.DATA, b"step 1\xff")
    assert_damaged(first + invalid, [LINES[0]])


@case("trailing-invalid-utf8-commit")
def _():
    assert_damaged(data_journal(LINES, commit=b"commit\xfe"), LINES)


@case("trailing-bad-crc")
def _():
    first = hsj2.frame(1, hsj2.DATA, LINES[0].encode("utf-8"))
    second = bytearray(hsj2.frame(2, hsj2.DATA, LINES[1].encode("utf-8")))
    second[12] ^= 0x01  # ровно один бит CRC; заголовок и payload остаются валидными
    assert_damaged(first + bytes(second), [LINES[0]])


@case("trailing-torn-frame")
def _():
    assert_damaged(data_journal(LINES) + b"\x10\x00\x00\x00", LINES)


@case("direct-callers")
def _():
    damaged = data_journal(LINES) + hsj2.frame(7, hsj2.DATA, b"step 2\xff")
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


@case("clean-positive")
def _():
    with host_projection(LINES):
        records, tail, problems = accept.parse_journal(data_journal(LINES))
        ok, rows = accept.check(HOST_CRITERIA, records, show_hidden=True)
        assert not tail and not problems, (tail, problems)
        assert ok, rows
        assert row(rows, "журнал комнаты совпадает с хостовым")[1], rows
        assert row(rows, "журнал прочитан полностью")[1], rows


def main() -> int:
    assert len(CASES) == 6, len(CASES)
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
    print(f"\nhost journal accept integrity: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    return 0 if failed == 0 and na == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
