"""W07B: host-issued authority и refs-only события, 14 зарегистрированных controls.

Запуск: python tests/test_host_journal_authority.py
Windows и POSIX: 14/14 без N/A. Сырые canary-строки существуют только в тесте и local journal.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from bin import accept, bridge as bridge_mod, host_journal, hsj2, rust_tests  # noqa: E402
import test_bridge_http_subset as subset  # noqa: E402

RUN = "w07b-authority-run"
SESSION = "11111111-1111-4111-8111-111111111111"
CANARY = "CANARY-W07B-RAW-SECRET"
VECTOR_PATH = ROOT / "tests" / "vectors" / "host-journal-event-v1.json"
EVENT_DOMAIN = b"HOST-JOURNAL-EVENT-V1\0"
CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn

    return wrap


def canonical(value: dict) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def event_digest(line: str) -> str:
    return hashlib.sha256(EVENT_DOMAIN + line.encode("utf-8")).hexdigest()


def project(events: list[tuple[str, str]], session: str = SESSION) -> list[dict]:
    """Независимая эталонная проекция; production обязан совпасть с ней побайтно."""
    out: list[dict] = []
    call_seq = 0
    pending: str | None = None
    for kind, detail in events:
        line = f"{kind} {detail}".strip()
        call_id = None
        refs: list[dict[str, str]] = []
        if kind == "tool/call":
            call_seq += 1
            call_id = f"call-{call_seq:06d}"
            pending = call_id
            tool = detail.split(" ", 1)[0]
            if re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", tool):
                refs.append({"id": tool, "kind": "tool"})
        elif kind == "tool/result":
            call_id = pending
            if pending:
                refs.append({"id": pending, "kind": "call"})
            pending = None
        elif kind == "claim/anchored":
            match = re.search(r"(?<![A-Za-z0-9_])C-[0-9]{4}(?![A-Za-z0-9_])", detail)
            if match:
                refs.append({"id": match.group(0).lower(), "kind": "claim"})
        if kind == "run/start":
            status = "started"
        elif kind == "run/end":
            status = "ended"
        elif kind == "run/blocked":
            status = "blocked"
        elif kind == "step/error":
            status = "error"
        elif kind == "model/reply":
            status = "replied"
        elif kind == "tool/result":
            head = detail.split(" ", 1)[0].lower()
            if head == "ok":
                status = "ok"
            elif detail.startswith("не выдан"):
                status = "denied"
            elif head in {"err", "error", "ошибка", "failed"}:
                status = "error"
            else:
                status = "recorded"
        else:
            status = "recorded"
        out.append({
            "schema": "host-journal-event-v1",
            "session": session,
            "type": kind,
            "call_id": call_id,
            "status": status,
            "refs": refs,
            "digests": {"event": event_digest(line)},
        })
    return out


def vector() -> dict:
    return json.loads(VECTOR_PATH.read_text(encoding="utf-8"))


def typed(value: dict) -> bytes:
    return canonical(value)


def legacy(run: str = RUN, event: str = "run/start", **extra) -> bytes:
    return canonical({"run": run, "event": event, **extra})


def request(port: int, body: bytes, *, declared: int | None = None) -> bytes:
    return subset.post_request(
        port, path="/v1/journal", body=body,
        replace={"Content-Length": str(len(body) if declared is None else declared)},
    )


def response(port: int, body: bytes, *, declared: int | None = None) -> tuple[int, dict]:
    status, _headers, payload = subset.response(subset.exchange(port, request(port, body, declared=declared)))
    assert status is not None, "bridge не вернул HTTP status"
    return status, payload


def journal_events(directory: Path) -> list[str]:
    return host_journal.events(RUN, directory)


@contextlib.contextmanager
def server(tmp: Path, **options):
    """Настоящий bridge; каждый case получает отдельный journal и log."""
    old_default = host_journal.DEFAULT_DIR
    directory = tmp / "journal"
    host_journal.DEFAULT_DIR = directory
    log_path = tmp / "bridge.jsonl"
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        instance = bridge_mod.Bridge(
            "http://127.0.0.1:1/v1/chat/completions", subset.CANARY, subset.TOKEN,
            log_path, session=SESSION, allow_loopback_http=True, **options,
        )
        http = subset.start_server(bridge_mod.make_handler(instance))
    try:
        yield http.server_address[1], directory, log_path
    finally:
        http.shutdown()
        http.server_close()
        host_journal.DEFAULT_DIR = old_default


def bound(**changes) -> dict:
    options = {
        "host_run": RUN,
        "host_session": SESSION,
        "expires_at": time.monotonic() + 300,
    }
    options.update(changes)
    return options


def reject(status: int, payload: dict) -> None:
    assert 400 <= status <= 499, (status, payload)


@case("bound-positive")
def _():
    expected = vector()["events"][0]["expected"]
    with tempfile.TemporaryDirectory() as tmp:
        with server(Path(tmp), **bound()) as (port, directory, _log):
            status, receipt = response(port, typed(expected))
            assert status == 200 and receipt.get("seq") == 1, (status, receipt)
            events = journal_events(directory)
            assert len(events) == 1 and json.loads(events[0]) == expected, events


@case("missing-binding")
def _():
    body = vector()["events"][0]["expected"]
    with tempfile.TemporaryDirectory() as tmp:
        with server(Path(tmp)) as (port, directory, _log):
            status, payload = response(port, typed(body))
            assert status == 503, (status, payload)
            assert journal_events(directory) == []


@case("partial-binding")
def _():
    # Все неполные связки обязаны отказать ещё в конструкторе. Это успешный negative control,
    # а не ошибка прибора: RED-версия не перехватывала ожидаемый ValueError. Inputs и число
    # controls не меняются; отсутствие expiry проверяется вместе с отсутствующим полем binding.
    for options in (
        {"host_run": RUN},
        {"host_session": SESSION},
        {"host_run": RUN, "host_session": SESSION},
    ):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                with server(Path(tmp), **options):
                    raise AssertionError("частичная связка запустила мост")
            except ValueError as exc:
                assert "host_run, host_session и expires_at" in str(exc), exc
            assert not (Path(tmp) / "journal").exists()


@case("forged-run")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        with server(Path(tmp), **bound()) as (port, directory, _log):
            status, payload = response(port, legacy(run="forged-run"))
            reject(status, payload)
            assert journal_events(directory) == []
            assert not (directory / "forged-run.jsonl").exists()


@case("mismatched-session")
def _():
    body = vector()["events"][0]["expected"]
    body["session"] = "22222222-2222-4222-8222-222222222222"
    with tempfile.TemporaryDirectory() as tmp:
        with server(Path(tmp), **bound()) as (port, directory, _log):
            status, payload = response(port, legacy(session=body["session"]))
            reject(status, payload)
            assert journal_events(directory) == []


@case("expired-binding")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        with server(Path(tmp), **bound(expires_at=time.monotonic() - 1)) as (port, directory, _log):
            status, payload = response(port, legacy())
            reject(status, payload)
            assert journal_events(directory) == []


@case("raw-canary")
def _():
    raw = f"run/start task: {CANARY}"
    with tempfile.TemporaryDirectory() as tmp:
        with server(Path(tmp), **bound()) as (port, directory, log_path):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status, payload = response(port, legacy(event=raw))
            reject(status, payload)
            assert journal_events(directory) == []
            sinks = b"\n".join(path.read_bytes() for path in (log_path,) if path.exists())
            sinks += b"\n".join(path.read_bytes() for path in directory.glob("*") if path.is_file())
            sinks += stdout.getvalue().encode("utf-8") + stderr.getvalue().encode("utf-8")
            assert CANARY.encode() not in sinks
            assert CANARY.encode() not in canonical(payload)


@case("oversized-body")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        with server(Path(tmp), **bound()) as (port, directory, _log):
            started = time.monotonic()
            status, payload = response(port, b"", declared=16385)
            elapsed = time.monotonic() - started
            assert status == 413 and elapsed < 1.0, (status, payload, elapsed)
            assert journal_events(directory) == []


@case("strict-schema")
def _():
    good = vector()["events"][0]["expected"]
    variants: list[bytes] = [
        legacy(extra=True),
        b'{"run":"' + RUN.encode() + b'","event":"run/start","event":"evil"}',
    ]
    changes = [
        {"schema": "host-journal-event-v2"},
        {"type": "unknown/type"},
        {"status": "accepted"},
        {"refs": [{"id": "../raw", "kind": "file"}]},
        {"digests": {"event": "0" * 64}},
        {"extra": CANARY},
    ]
    for change in changes:
        value = copy.deepcopy(good)
        value.update(change)
        variants.append(typed(value))
    missing = copy.deepcopy(good)
    del missing["digests"]
    variants.append(typed(missing))
    with tempfile.TemporaryDirectory() as tmp:
        with server(Path(tmp), **bound()) as (port, directory, _log):
            for body in variants:
                status, payload = response(port, body)
                reject(status, payload)
            assert journal_events(directory) == []


@case("host-match-positive")
def _():
    local = [("run/start", f"task: {CANARY}"), ("claim/anchored", "C-0345")]
    expected = project(local)
    old_default = host_journal.DEFAULT_DIR
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp) / "journal"
        host_journal.DEFAULT_DIR = directory
        try:
            for event in expected:
                host_journal.append(RUN, canonical(event).decode("utf-8"), directory)
            data = hsj2.journal([(1, f"{kind} {detail}".strip()) for kind, detail in local])
            records, tail, problems = accept.parse_journal(data)
            assert not tail and not problems, (tail, problems)
            criteria = {"host_run": RUN, "host_session": SESSION, "host_match": True}
            ok, rows = accept.check(criteria, records, show_hidden=True)
            assert ok, rows
        finally:
            host_journal.DEFAULT_DIR = old_default


@case("forged-local")
def _():
    original = [("run/start", f"task: {CANARY}"), ("claim/anchored", "C-0345")]
    forged = [("run/start", f"task: {CANARY}"), ("claim/anchored", "C-9999")]
    old_default = host_journal.DEFAULT_DIR
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp) / "journal"
        host_journal.DEFAULT_DIR = directory
        try:
            for event in project(original):
                host_journal.append(RUN, canonical(event).decode("utf-8"), directory)
            data = hsj2.journal([(1, f"{kind} {detail}".strip()) for kind, detail in forged])
            records, tail, problems = accept.parse_journal(data)
            assert not tail and not problems, "forged local journal должен иметь корректный CRC"
            criteria = {"host_run": RUN, "host_session": SESSION, "host_match": True}
            ok, rows = accept.check(criteria, records, show_hidden=True)
            assert not ok, rows
            assert any("совпадает" in name and not passed for name, passed, _detail in rows), rows
        finally:
            host_journal.DEFAULT_DIR = old_default


@case("required-session")
def _():
    local = [("run/start", "task: baseline")]
    old_default = host_journal.DEFAULT_DIR
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp) / "journal"
        host_journal.DEFAULT_DIR = directory
        try:
            for line in (f"{kind} {detail}" for kind, detail in local):
                host_journal.append(RUN, line, directory)
            records = [(1, f"{kind} {detail}") for kind, detail in local]
            ok, rows = accept.check({"host_run": RUN, "host_match": True}, records, show_hidden=True)
            assert not ok, "host_match без ожидаемой session принят"
            assert any("session" in name.lower() for name, _passed, _detail in rows), rows
        finally:
            host_journal.DEFAULT_DIR = old_default


@case("rust-python-vector")
def _():
    data = vector()
    assert len(data["events"]) == 5
    local = [(row["expected"]["type"], row["local"].split(" ", 1)[1]) for row in data["events"]]
    assert project(local) == [row["expected"] for row in data["events"]]
    core = rust_tests.wsl_path(ROOT / "core-rs")
    if os.name == "nt":
        script = (f"test -d '{core}' && cd '{core}' && {rust_tests.CLEAN} && "
                  "CARGO_NET_OFFLINE=true rustup run stable cargo test --release --lib host_event_vector 2>&1")
        code, output = rust_tests.wsl(script, timeout=600)
    else:
        result = subprocess.run(
            ["cargo", "test", "--release", "--lib", "host_event_vector"],
            cwd=ROOT / "core-rs", capture_output=True, text=True,
            env={**os.environ, "CARGO_NET_OFFLINE": "true"}, timeout=600,
        )
        code, output = result.returncode, (result.stdout or "") + (result.stderr or "")
    assert code == 0 and "1 passed; 0 failed" in output, output[-4000:]


@case("receipt-semantics")
def _():
    expected = vector()["events"][0]["expected"]
    with tempfile.TemporaryDirectory() as tmp:
        with server(Path(tmp), **bound()) as (port, _directory, _log):
            status, receipt = response(port, typed(expected))
            assert status == 200, (status, receipt)
            assert set(receipt) == {"seq", "sha256"}, receipt
            assert receipt["seq"] == 1 and re.fullmatch(r"[0-9a-f]{64}", receipt["sha256"])


def main() -> int:
    assert len(CASES) == 14, len(CASES)
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
    print(f"\nhost journal authority: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    return 0 if failed == 0 and na == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
