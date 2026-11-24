"""W07B-REVIEW: семь correction controls после независимого authority review.

Запуск: python tests/test_host_journal_authority_review.py
Windows и POSIX: 7/7 без N/A. Исходный W07B 14-control corpus не изменяется.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from bin import accept, host_journal, hsj2, journal_event, rust_tests  # noqa: E402
import test_host_journal_authority as authority  # noqa: E402

SESSION = authority.SESSION
RUN = authority.RUN
EVENT_DOMAIN = journal_event.EVENT_DOMAIN
VECTOR_PATH = ROOT / "tests" / "vectors" / "host-journal-event-review-v1.json"
CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn

    return wrap


def vector() -> dict:
    return json.loads(VECTOR_PATH.read_text(encoding="utf-8"))


def canonical(value: dict) -> bytes:
    return journal_event.canonical(value)


def exact_payload(line: str, session: str = SESSION) -> dict:
    """Независимый эталон для correction-векторов: хешируем точную строку."""
    kind, _, detail = line.partition(" ")
    statuses = {
        "run/start": "started", "run/end": "ended", "run/blocked": "blocked",
        "run/no-work": "no-work", "step/error": "error", "model/reply": "replied",
    }
    refs: list[dict[str, str]] = []
    if kind == "claim/anchored" and "C-0345" in detail:
        refs = [{"id": "c-0345", "kind": "claim"}]
    return {
        "schema": "host-journal-event-v1", "session": session, "type": kind,
        "call_id": None, "status": statuses.get(kind, "recorded"), "refs": refs,
        "digests": {"event": hashlib.sha256(EVENT_DOMAIN + line.encode("utf-8")).hexdigest()},
    }


def run_rust(filter_name: str, expected_passed: int) -> None:
    core = rust_tests.wsl_path(ROOT / "core-rs")
    if os.name == "nt":
        script = (f"test -d '{core}' && cd '{core}' && {rust_tests.CLEAN} && "
                  f"CARGO_NET_OFFLINE=true rustup run stable cargo test --release --lib {filter_name} 2>&1")
        code, output = rust_tests.wsl(script, timeout=600)
    else:
        result = subprocess.run(
            ["cargo", "test", "--release", "--lib", filter_name],
            cwd=ROOT / "core-rs", capture_output=True, text=True,
            env={**os.environ, "CARGO_NET_OFFLINE": "true"}, timeout=600,
        )
        code, output = result.returncode, (result.stdout or "") + (result.stderr or "")
    marker = f"{expected_passed} passed; 0 failed"
    assert code == 0 and marker in output, output[-5000:]


@case("strict-local-utf8")
def _():
    lines = ["run/start task: \ufffd", "run/end done"]
    expected = [exact_payload(line) for line in lines]
    old_default = host_journal.DEFAULT_DIR
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp) / "journal"
        host_journal.DEFAULT_DIR = directory
        try:
            for payload in expected:
                host_journal.append(RUN, canonical(payload).decode("utf-8"), directory)
            for bad_byte in (0xFF, 0xFE):
                forged = hsj2.journal([
                    (hsj2.DATA, b"run/start task: " + bytes([bad_byte])),
                    (hsj2.DATA, b"run/end done"),
                ])
                records, tail, problems = accept.parse_journal(forged)
                criteria = {"host_run": RUN, "host_session": SESSION, "host_match": True}
                ok, rows = accept.check(criteria, records, show_hidden=True)
                assert not ok, f"invalid UTF-8 {bad_byte:#04x} принят: {rows}"
                assert tail == len(forged) - 8 and problems, (tail, problems, rows)
        finally:
            host_journal.DEFAULT_DIR = old_default


@case("exact-whitespace")
def _():
    data = vector()
    assert len(data["events"]) == 4
    lines = [row["local"] for row in data["events"]]
    expected = [row["expected"] for row in data["events"]]
    assert [exact_payload(line) for line in lines] == expected
    local = [tuple(line.split(" ", 1)) for line in lines]
    assert journal_event.project(local, SESSION) == expected

    old_default = host_journal.DEFAULT_DIR
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp) / "journal"
        host_journal.DEFAULT_DIR = directory
        try:
            for payload in expected:
                host_journal.append(RUN, canonical(payload).decode("utf-8"), directory)
            records, tail, problems = accept.parse_journal(hsj2.journal([(hsj2.DATA, line) for line in lines]))
            assert not tail and not problems, (tail, problems)
            ok, rows = accept.check(
                {"host_run": RUN, "host_session": SESSION, "host_match": True},
                records, show_hidden=True,
            )
            assert ok, rows
        finally:
            host_journal.DEFAULT_DIR = old_default

    run_rust("host_event_review_vector", 1)


@case("typed-mismatched-session")
def _():
    body = copy.deepcopy(vector()["events"][0]["expected"])
    body["session"] = "22222222-2222-4222-8222-222222222222"
    with tempfile.TemporaryDirectory() as tmp:
        with authority.server(Path(tmp), **authority.bound()) as (port, directory, _log):
            status, payload = authority.response(port, authority.typed(body))
            assert status == 400, (status, payload)
            assert authority.journal_events(directory) == []


@case("typed-expired-binding")
def _():
    body = vector()["events"][0]["expected"]
    with tempfile.TemporaryDirectory() as tmp:
        options = authority.bound(expires_at=time.monotonic() - 1)
        with authority.server(Path(tmp), **options) as (port, directory, _log):
            status, payload = authority.response(port, authority.typed(body))
            assert status == 403, (status, payload)
            assert authority.journal_events(directory) == []


@case("session-before-read")
def _():
    old_verify, old_events = host_journal.verify, host_journal.events

    def forbidden(*_args, **_kwargs):
        raise AssertionError("host chain прочитана до обязательной session")

    host_journal.verify = forbidden
    host_journal.events = forbidden
    try:
        ok, rows = accept.check(
            {"host_run": RUN, "host_match": True}, [], show_hidden=True,
        )
    finally:
        host_journal.verify, host_journal.events = old_verify, old_events
    assert not ok, rows
    assert any("session" in name.lower() for name, _passed, _detail in rows), rows


@case("claim-unverified-status")
def _():
    body = {
        "schema": "host-journal-event-v1", "session": SESSION,
        "type": "claim/unverified", "call_id": None, "status": "ok", "refs": [],
        "digests": {"event": hashlib.sha256(EVENT_DOMAIN + b"claim/unverified C-0345").hexdigest()},
    }
    with tempfile.TemporaryDirectory() as tmp:
        with authority.server(Path(tmp), **authority.bound()) as (port, directory, _log):
            status, payload = authority.response(port, authority.typed(body))
            assert status == 400, (status, payload)
            assert authority.journal_events(directory) == []


@case("rust-receipt-shape")
def _():
    run_rust("emit_journal_receipt_", 6)


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
    print(f"\nhost journal authority review: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    return 0 if failed == 0 and na == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
