"""W17 review round: отдельные контролы пяти находок независимого аудита."""

from __future__ import annotations

import contextlib
import io
import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from bin import bridge as bridge_mod  # noqa: E402
from bin import host_journal  # noqa: E402
import test_bridge_http_subset as subset  # noqa: E402

TOKEN = subset.TOKEN
CANARY = subset.CANARY
RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, label: str) -> None:
    RESULTS.append((bool(flag), label))


def read_all(sock: socket.socket, timeout: float) -> bytes:
    sock.settimeout(timeout)
    chunks: list[bytes] = []
    while True:
        try:
            chunk = sock.recv(65536)
        except (socket.timeout, ConnectionAbortedError, ConnectionResetError):
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def require_timeout(raw: bytes, elapsed: float, lower: float, upper: float, label: str) -> None:
    status, _headers, payload = subset.response(raw)
    check(
        status == 408
        and payload.get("code") == "BRIDGE_HTTP_TIMEOUT"
        and lower <= elapsed <= upper,
        f"{label}: status={status}, code={payload.get('code')}, elapsed={elapsed:.3f}s",
    )


class TimeoutSocket:
    """Test double для write deadline: ждёт установленный timeout и затем падает."""

    def __init__(self) -> None:
        self.timeout: float | None = None

    def settimeout(self, value: float) -> None:
        self.timeout = value

    def sendall(self, _payload: bytes) -> None:
        assert self.timeout is not None
        time.sleep(self.timeout)
        raise socket.timeout("simulated write timeout")


def main() -> int:
    with (
        tempfile.TemporaryDirectory() as tmp,
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        tmp_path = Path(tmp)
        upstream = subset.start_server(subset.FakeUpstream)
        up_port = upstream.server_address[1]
        subset.FakeUpstream.received.clear()
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
        server = subset.start_server(bridge_mod.make_handler(bridge))
        port = server.server_address[1]

        try:
            # 1. Точный request header separator ': '.
            counters["chat"] = 0
            raw = subset.post_request(port, body=b"{}").replace(
                b"Content-Length: ", b"Content-Length:"
            )
            try:
                subset.require_rejected(
                    subset.exchange(port, raw), "BRIDGE_HTTP_MALFORMED", counters,
                    "header-separator",
                )
            except Exception as exc:  # noqa: BLE001
                check(False, f"header-separator: {exc}")
            else:
                check(True, "header-separator")

            # 2. Неверный token отвергается до чтения объявленного body.
            counters["chat"] = 0
            with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
                head = subset.post_request(port, body=b"x" * 100).split(b"\r\n\r\n", 1)[0]
                head = head.replace(TOKEN.encode(), b"wrong-token")
                started = time.monotonic()
                sock.sendall(head + b"\r\n\r\n")
                raw = read_all(sock, 1.0)
                elapsed = time.monotonic() - started
            status, _headers, payload = subset.response(raw)
            check(
                status == 401
                and payload.get("code") == "BRIDGE_HTTP_UNAUTHORIZED"
                and elapsed < 0.8
                and counters["chat"] == 0,
                f"auth-before-body: status={status}, elapsed={elapsed:.3f}s",
            )

            # 3. Второй request отдельным сегментом после задержки.
            counters["chat"] = 0
            with socket.create_connection(("127.0.0.1", port), timeout=2.0) as sock:
                first = subset.post_request(port, body=b"{}")
                second = subset.post_request(port, body=b"{}")
                sock.sendall(first)
                time.sleep(0.1)
                try:
                    sock.sendall(second)
                except OSError:
                    pass
                sock.shutdown(socket.SHUT_WR)
                raw = read_all(sock, 2.0)
            try:
                subset.require_rejected(
                    raw, "BRIDGE_HTTP_SMUGGLING", counters, "delayed-pipeline",
                )
            except Exception as exc:  # noqa: BLE001
                check(False, f"delayed-pipeline: {exc}")
            else:
                check(True, "delayed-pipeline")

            # 4. Connect/first-byte deadline на масштабированном значении.
            old_connect = bridge_mod.HTTP_CONNECT_TIMEOUT
            bridge_mod.HTTP_CONNECT_TIMEOUT = 0.2
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1.5) as sock:
                    started = time.monotonic()
                    raw = read_all(sock, 1.5)
                    elapsed = time.monotonic() - started
                require_timeout(raw, elapsed, 0.15, 1.2, "connect-timeout")
            finally:
                bridge_mod.HTTP_CONNECT_TIMEOUT = old_connect

            # 5. Настоящий header idle timeout 5.0 c.
            started = time.monotonic()
            raw = subset.slowloris(port)
            elapsed = time.monotonic() - started
            require_timeout(raw, elapsed, 4.5, 7.0, "header-idle-timeout")

            # 6. Scaled total timeout использует ту же production-ветку.
            started = time.monotonic()
            raw = subset.scaled_total_timeout(port)
            elapsed = time.monotonic() - started
            require_timeout(raw, elapsed, 0.15, 1.5, "total-timeout")

            # 7. Write deadline реально передаётся sendall и выдерживается.
            old_write = bridge_mod.HTTP_WRITE_TIMEOUT
            bridge_mod.HTTP_WRITE_TIMEOUT = 0.2
            try:
                handler_cls = bridge_mod.make_handler(bridge)
                handler = handler_cls.__new__(handler_cls)
                handler.request = TimeoutSocket()
                handler._path = "?"
                started = time.monotonic()
                handler._respond(200, b"{}")
                elapsed = time.monotonic() - started
                check(
                    handler.request.timeout == 0.2 and 0.15 <= elapsed <= 1.0,
                    f"write-timeout: timeout={handler.request.timeout}, elapsed={elapsed:.3f}s",
                )
            finally:
                bridge_mod.HTTP_WRITE_TIMEOUT = old_write

            # 8. Единая закрытая status policy.
            try:
                policy = bridge_mod.canonical_response_status
                observed = [policy(value) for value in (200, 400, 415, 418, 500, 599, 201, 302, 600)]
                check(
                    observed == [200, 400, 415, 418, 500, 599, 502, 502, 502],
                    f"status-policy: {observed}",
                )
            except Exception as exc:  # noqa: BLE001
                check(False, f"status-policy: {exc}")
        finally:
            server.shutdown()
            server.server_close()
            upstream.shutdown()
            upstream.server_close()
            bridge.forward = original_forward
            host_journal.append = original_append
            host_journal.DEFAULT_DIR = old_default_dir

    for flag, label in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {label}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"проверок: {len(RESULTS)}; провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
