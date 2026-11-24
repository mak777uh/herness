"""W17: строгий HTTP-subset комнаты на raw TCP, а не через снижающий ошибки client.

Корпус исполняет настоящий bridge. Каждый invalid обязан получить BRIDGE_HTTP_* код
и не вызвать downstream; канонические health/chat/journal/net обязаны пройти.
"""

from __future__ import annotations

import contextlib
import io
import json
import socket
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import bridge as bridge_mod  # noqa: E402
from bin import host_journal  # noqa: E402

TOKEN = "local-" + "token-canary-w17"  # синтетический canary, не секрет
CANARY = "PROVIDER-KEY-CANARY-W17"
MAX_BODY = 8 * 1024 * 1024


class FakeUpstream(BaseHTTPRequestHandler):
    received: list[bytes] = []

    def log_message(self, *args):  # noqa: D401
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        type(self).received.append(b"chat")
        payload = b'{"choices":[{"message":{"content":"ok"}}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def start_server(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def post_request(
    port: int,
    *,
    path: str = "/v1/chat/completions",
    body: bytes = b'{"model":"m"}',
    method: str = "POST",
    version: str = "HTTP/1.1",
    omit: tuple[str, ...] = (),
    replace: dict[str, str] | None = None,
    extra: tuple[tuple[str, str], ...] = (),
) -> bytes:
    headers = [
        ("Host", f"127.0.0.1:{port}"),
        ("Authorization", f"Bearer {TOKEN}"),
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(body))),
        ("Connection", "close"),
    ]
    replace = {name.lower(): value for name, value in (replace or {}).items()}
    omitted = {name.lower() for name in omit}
    lines = [f"{method} {path} {version}".encode("ascii")]
    for name, value in headers:
        if name.lower() in omitted:
            continue
        lines.append(f"{name}: {replace.get(name.lower(), value)}".encode("ascii"))
    for name, value in extra:
        lines.append(f"{name}: {value}".encode("ascii"))
    return b"\r\n".join(lines) + b"\r\n\r\n" + body


def health_request(port: int) -> bytes:
    return (
        f"GET /health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")


def named_mutants(port: int) -> list[tuple[str, str, bytes]]:
    five = b"12345"
    canonical = post_request(port, body=five)
    chunked = (
        f"POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        f"Authorization: Bearer {TOKEN}\r\nContent-Type: application/json\r\n"
        "Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
        "5\r\n12345\r\n0\r\n\r\n"
    ).encode("ascii")
    return [
        ("duplicate-content-length", "BRIDGE_HTTP_DUPLICATE_HEADER",
         post_request(port, extra=(("content-length", "5"),))),
        ("duplicate-host", "BRIDGE_HTTP_DUPLICATE_HEADER",
         post_request(port, extra=(("host", f"127.0.0.1:{port}"),))),
        ("transfer-plus-length", "BRIDGE_HTTP_CHUNKED_FORBIDDEN",
         post_request(port, extra=(("Transfer-Encoding", "chunked"),))),
        ("chunked-body", "BRIDGE_HTTP_CHUNKED_FORBIDDEN", chunked),
        ("obs-fold", "BRIDGE_HTTP_MALFORMED",
         post_request(port, extra=(("X-Request-Id", "abc\r\n continued"),))),
        ("lf-only", "BRIDGE_HTTP_MALFORMED", canonical.replace(b"\r\n", b"\n")),
        ("obs-text", "BRIDGE_HTTP_MALFORMED",
         canonical.replace(b"Connection: close", b"X-Request-Id: caf\xe9")),
        ("missing-length", "BRIDGE_HTTP_BAD_LENGTH",
         post_request(port, body=five, omit=("Content-Length",))),
        ("plus-length", "BRIDGE_HTTP_BAD_LENGTH",
         post_request(port, body=five, replace={"Content-Length": "+5"})),
        ("leading-zero-length", "BRIDGE_HTTP_BAD_LENGTH",
         post_request(port, body=five, replace={"Content-Length": "05"})),
        ("space-length", "BRIDGE_HTTP_BAD_LENGTH",
         post_request(port, body=five, replace={"Content-Length": " 5"})),
        ("underscore-length", "BRIDGE_HTTP_BAD_LENGTH",
         post_request(port, body=five, replace={"Content-Length": "5_0"})),
        ("get-post-route", "BRIDGE_HTTP_METHOD",
         post_request(port, method="GET", body=b"", omit=("Content-Length",))),
        ("absolute-form", "BRIDGE_HTTP_PATH",
         post_request(port, path=f"http://127.0.0.1:{port}/v1/chat/completions")),
        ("unknown-header", "BRIDGE_HTTP_FORBIDDEN_HEADER",
         post_request(port, extra=(("X-Evil", "1"),))),
        ("path-traversal", "BRIDGE_HTTP_PATH",
         post_request(port, path="/v1/net/../chat")),
        ("http-10", "BRIDGE_HTTP_VERSION", post_request(port, version="HTTP/1.0")),
        ("trailing-byte", "BRIDGE_HTTP_SMUGGLING",
         post_request(port, body=b"{}") + b"X"),
        ("pipelined-request", "BRIDGE_HTTP_SMUGGLING",
         post_request(port, body=b"{}") + post_request(port, body=b"{}")),
        ("expect-continue", "BRIDGE_HTTP_EXPECT_FORBIDDEN",
         post_request(port, extra=(("Expect", "100-continue"),))),
        ("length-cap", "BRIDGE_HTTP_LENGTH_CAP",
         post_request(port, body=b"", replace={"Content-Length": str(MAX_BODY + 1)})),
        ("negative-length", "BRIDGE_HTTP_BAD_LENGTH",
         post_request(port, body=b"", replace={"Content-Length": "-2"})),
    ]


def malformed_corpus(port: int) -> list[tuple[str, bytes]]:
    """Ровно 50 дополнительных not-canonical запросов сверх 22 именованных."""
    cases: list[tuple[str, bytes]] = []

    def add(name: str, payload: bytes) -> None:
        cases.append((name, payload))

    for index, path in enumerate([
        "/v1/chat/completions/", "/v1/chat/completions?x=1", "/v1/chat/completions#x",
        "/v1//chat/completions", "/v1/%63hat/completions", "/v1/chat/completions ",
    ]):
        add(f"path-{index}", post_request(port, path=path))
    for index, method in enumerate(["post", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"]):
        add(f"method-{index}", post_request(port, method=method, body=b"", omit=("Content-Length",)))
    for index, version in enumerate(["HTTP/2.0", "HTTP/1", "HTTP/1.1 ", "http/1.1", "HTTP/1.2"]):
        add(f"version-{index}", post_request(port, version=version))
    for index, value in enumerate(["0", "00", "+2", "2 ", "2_0", "-1", "999999999999999999999"]):
        add(f"length-{index}", post_request(port, body=b"{}", replace={"Content-Length": value}))
    for index, (name, value) in enumerate([
        ("Connection", "keep-alive"), ("Content-Type", "text/plain"),
        ("Authorization", "Basic abc"), ("Authorization", "Bearer"),
        ("Host", ""), ("Host", "bad host"),
    ]):
        add(f"header-value-{index}", post_request(port, replace={name: value}))
    add("header-value-6", post_request(port, extra=(("X-Request-Id", "abc\tdef"),)))
    for index, name in enumerate(["X-One", "X-Two", "X-Three", "X-Four", "X-Five", "X-Six"]):
        add(f"header-count-{index}", post_request(port, extra=tuple((f"X-{n}", "1") for n in range(index + 1))))
    add("missing-host", post_request(port, omit=("Host",)))
    add("missing-auth", post_request(port, omit=("Authorization",)))
    add("missing-content-type", post_request(port, omit=("Content-Type",)))
    add("missing-connection", post_request(port, omit=("Connection",)))
    add("duplicate-auth", post_request(port, extra=(("Authorization", f"Bearer {TOKEN}"),)))
    add("duplicate-content-type", post_request(port, extra=(("Content-Type", "application/json"),)))
    add("duplicate-connection", post_request(port, extra=(("Connection", "close"),)))
    add("space-before-colon", post_request(port).replace(b"Host:", b"Host :"))
    add("tab-indent", post_request(port).replace(b"Host:", b"\tHost:"))
    add("bare-lf-header", post_request(port).replace(b"Host: 127.0.0.1:", b"Host: 127.0.0.1:\n"))
    add("long-header", post_request(port, extra=(("X-Long", "a" * 1100),)))
    add("empty-header-name", post_request(port).replace(b"Host:", b": value\r\nHost:"))
    add("double-space-request-line", post_request(port).replace(b"POST /v1/", b"POST  /v1/"))
    assert len(cases) == 50, len(cases)
    return cases


def exchange(port: int, payload: bytes, timeout: float = 4.0) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(payload)
        sock.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)


def response(raw: bytes) -> tuple[int | None, dict[str, str], dict]:
    if b"\r\n\r\n" not in raw:
        return None, {}, {}
    head, body = raw.split(b"\r\n\r\n", 1)
    lines = head.split(b"\r\n")
    parts = lines[0].split(b" ", 2)
    try:
        status = int(parts[1])
    except (IndexError, ValueError):
        status = None
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if b":" in line:
            name, value = line.split(b":", 1)
            headers[name.decode("latin-1").lower()] = value.strip().decode("latin-1")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        payload = {}
    return status, headers, payload


def require_rejected(raw: bytes, expected_code: str, counters: dict[str, int], label: str) -> None:
    status, _headers, payload = response(raw)
    if status is None or not 400 <= status <= 599:
        raise AssertionError(f"{label}: ожидался 4xx/5xx, получено {status}")
    if payload.get("code") != expected_code:
        raise AssertionError(f"{label}: ожидался {expected_code}, получено код {payload.get('code')!r}")
    if sum(counters.values()) != 0:
        raise AssertionError(f"{label}: invalid вызвал downstream {counters}")


def require_malformed(raw: bytes, counters: dict[str, int], label: str) -> None:
    status, _headers, payload = response(raw)
    if status is None or not 400 <= status <= 599:
        raise AssertionError(f"{label}: ожидался 4xx/5xx, получено {status}")
    if not str(payload.get("code", "")).startswith("BRIDGE_HTTP_"):
        raise AssertionError(f"{label}: ожидался BRIDGE_HTTP_* код, получено код {payload.get('code')!r}")
    if sum(counters.values()) != 0:
        raise AssertionError(f"{label}: malformed вызвал downstream {counters}")


def require_accepted(raw: bytes, counters: dict[str, int], label: str, downstream: str | None) -> None:
    status, headers, payload = response(raw)
    if status != 200 or not isinstance(payload, dict):
        raise AssertionError(f"{label}: ожидался JSON 200, получено status={status}, json={isinstance(payload, dict)}")
    if headers.get("connection", "").lower() != "close":
        raise AssertionError(f"{label}: нет Connection: close")
    length = headers.get("content-length")
    body = raw.split(b"\r\n\r\n", 1)[1]
    if length != str(len(body)):
        raise AssertionError(f"{label}: Content-Length {length!r} != {len(body)}")
    expected = 0 if downstream is None else 1
    if sum(counters.values()) != expected:
        raise AssertionError(f"{label}: неверный positive control {counters}")


def slowloris(port: int) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=7.0) as sock:
        sock.settimeout(7.0)
        sock.sendall(f"POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n".encode())
        chunks: list[bytes] = []
        while True:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)


def scaled_total_timeout(port: int) -> bytes:
    old = bridge_mod.HTTP_TOTAL_TIMEOUT
    bridge_mod.HTTP_TOTAL_TIMEOUT = 0.2
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as sock:
            sock.settimeout(2.0)
            sock.sendall(post_request(port, body=b"1234567890")[:-9])
            chunks: list[bytes] = []
            while True:
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
    finally:
        bridge_mod.HTTP_TOTAL_TIMEOUT = old


def main() -> int:
    failures: list[str] = []
    passed: list[str] = []
    checks = 0
    responses: list[bytes] = []
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        tempfile.TemporaryDirectory() as tmp,
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        tmp_path = Path(tmp)
        upstream = start_server(FakeUpstream)
        up_port = upstream.server_address[1]
        log_path = tmp_path / "bridge.jsonl"
        token_path = tmp_path / "token.txt"
        token_path.write_text(TOKEN + "\n", encoding="utf-8")
        bridge = bridge_mod.Bridge(
            f"http://127.0.0.1:{up_port}/v1/chat/completions",
            CANARY,
            TOKEN,
            log_path,
            allow_loopback_http=True,
        )
        counters = {"chat": 0, "journal": 0, "net": 0}
        original_forward = bridge.forward

        def counted_forward(*args, **kwargs):
            counters["chat"] += 1
            return original_forward(*args, **kwargs)

        bridge.forward = counted_forward
        original_append = host_journal.append
        old_default_dir = host_journal.DEFAULT_DIR
        host_journal.DEFAULT_DIR = tmp_path / "journal"

        def counted_append(*args, **kwargs):
            counters["journal"] += 1
            return original_append(*args, **kwargs)

        host_journal.append = counted_append

        def net_command(argv):
            if argv and argv[0] == "search":
                counters["net"] += 1
                return [sys.executable, "-c", "print('net-ok')"], ""
            return None, "unknown"

        bridge.net_command = net_command
        server = start_server(bridge_mod.make_handler(bridge))
        port = server.server_address[1]

        def observed_exchange(payload: bytes) -> bytes:
            raw = exchange(port, payload)
            responses.append(raw)
            return raw

        try:
            for label, code, payload in named_mutants(port):
                checks += 1
                counters.update(chat=0, journal=0, net=0)
                try:
                    require_rejected(observed_exchange(payload), code, counters, label)
                except Exception as exc:  # noqa: BLE001 — корпус печатает все провалы
                    failures.append(str(exc))
                else:
                    passed.append(label)

            for label, payload in malformed_corpus(port):
                checks += 1
                counters.update(chat=0, journal=0, net=0)
                try:
                    require_malformed(observed_exchange(payload), counters, label)
                except Exception as exc:  # noqa: BLE001
                    failures.append(str(exc))
                else:
                    passed.append(label)

            positives = [
                ("health", health_request(port), None),
                ("chat", post_request(port, body=b'{"model":"m"}'), "chat"),
                ("journal", post_request(port, path="/v1/journal", body=b'{"run":"w17","event":"run/start"}'), "journal"),
                ("net", post_request(port, path="/v1/net", body=b'{"request":"search test"}'), "net"),
            ]
            for label, payload, downstream in positives:
                checks += 1
                counters.update(chat=0, journal=0, net=0)
                try:
                    require_accepted(observed_exchange(payload), counters, label, downstream)
                except Exception as exc:  # noqa: BLE001
                    failures.append(str(exc))
                else:
                    passed.append(label)

            checks += 1
            try:
                if bridge_mod.HTTP_HEADER_IDLE_TIMEOUT != 5.0 or bridge_mod.HTTP_TOTAL_TIMEOUT != 30.0:
                    raise AssertionError("production timeout constants != 5.0/30.0")
                counters.update(chat=0, journal=0, net=0)
                raw = slowloris(port)
                responses.append(raw)
                require_rejected(raw, "BRIDGE_HTTP_TIMEOUT", counters, "slowloris")
            except Exception as exc:  # noqa: BLE001
                failures.append(str(exc))
            else:
                passed.append("slowloris")

            checks += 1
            try:
                counters.update(chat=0, journal=0, net=0)
                raw = scaled_total_timeout(port)
                responses.append(raw)
                require_rejected(raw, "BRIDGE_HTTP_TIMEOUT", counters, "total-timeout")
            except Exception as exc:  # noqa: BLE001
                failures.append(str(exc))
            else:
                passed.append("total-timeout")

            checks += 1
            try:
                def detects_secret(text: str) -> bool:
                    return CANARY in text or TOKEN in text

                if not detects_secret("prefix:" + CANARY) or not detects_secret("prefix:" + TOKEN):
                    raise AssertionError("отрицательный контроль детектора секретов не сработал")
                observed = "\n".join([
                    log_path.read_text(encoding="utf-8") if log_path.exists() else "",
                    stdout.getvalue(),
                    stderr.getvalue(),
                    b"".join(responses).decode("utf-8", "replace"),
                ])
                if detects_secret(observed):
                    raise AssertionError("canary или token попали в наблюдаемые каналы")
            except Exception as exc:  # noqa: BLE001
                failures.append(str(exc))
            else:
                passed.append("no-secret")
        finally:
            server.shutdown()
            server.server_close()
            upstream.shutdown()
            upstream.server_close()
            host_journal.append = original_append
            host_journal.DEFAULT_DIR = old_default_dir

    for label in passed:
        print(f"[ok] {label}")
    for failure in failures:
        print(f"[FAIL] {failure}")
    print(f"проверок: {checks}; провалов: {len(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
