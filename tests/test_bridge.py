"""Тесты моста: ключ не утекает, токен проверяется, журнал без тел и заголовков."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import bridge as bridge_mod  # noqa: E402

CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


class FakeUpstream(BaseHTTPRequestHandler):
    received: list[dict] = []

    def log_message(self, *args):
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        FakeUpstream.received.append({
            "auth": self.headers.get("Authorization", ""),
            "body": body.decode("utf-8", "replace"),
        })
        payload = b'{"choices":[{"message":{"content":"ok"}}]}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def start(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def with_bridge(upstream_url: str, log_path: Path):
    token = "local-" + "tk-123"
    b = bridge_mod.Bridge(upstream_url, "PROVIDER-KEY-SECRET", token, log_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), bridge_mod.make_handler(b))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1], token


def post(port: int, path: str, token: str | None, body: bytes) -> tuple[int, bytes]:
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as error:
        return int(error.code), error.read()


@case("без локального токена — 401, провайдер не тронут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        upstream, up_port = start(FakeUpstream)
        port, _token = with_bridge(f"http://127.0.0.1:{up_port}/v1/x", Path(tmp) / "log.jsonl")
        FakeUpstream.received = []
        status, _ = post(port, "/v1/chat/completions", None, b'{"model":"m"}')
        assert status == 401, status
        assert FakeUpstream.received == []
        upstream.shutdown()


@case("с токеном — 200, провайдер получает настоящий ключ, а не локальный")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        upstream, up_port = start(FakeUpstream)
        port, token = with_bridge(f"http://127.0.0.1:{up_port}/v1/x", Path(tmp) / "log.jsonl")
        FakeUpstream.received = []
        status, body = post(port, "/v1/chat/completions", token, '{"model":"m"}'.encode())
        assert status == 200, status
        assert b"ok" in body
        sent = FakeUpstream.received[0]
        assert sent["auth"] == "Bearer PROVIDER-KEY-SECRET", sent["auth"]
        assert token not in sent["auth"]
        upstream.shutdown()


@case("путь вне /v1 — 404 и никакой пересылки")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        upstream, up_port = start(FakeUpstream)
        port, token = with_bridge(f"http://127.0.0.1:{up_port}/v1/x", Path(tmp) / "log.jsonl")
        FakeUpstream.received = []
        status, _ = post(port, "/admin/secret", token, b"{}")
        assert status == 404, status
        assert FakeUpstream.received == []
        upstream.shutdown()


@case("журнал не содержит ни тела, ни ключа, ни токена")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "log.jsonl"
        upstream, up_port = start(FakeUpstream)
        port, token = with_bridge(f"http://127.0.0.1:{up_port}/v1/x", log_path)
        post(port, "/v1/chat/completions", token, '{"model":"m","secret":"ТЕЛО"}'.encode())
        time.sleep(0.2)
        text = log_path.read_text(encoding="utf-8")
        entry = json.loads(text.strip().splitlines()[-1])
        assert "ТЕЛО" not in text
        assert "PROVIDER-KEY-SECRET" not in text
        assert token not in text
        assert entry["status"] == 200 and entry["bytes_in"] > 0 and entry["bytes_out"] > 0
        upstream.shutdown()


@case("отпечаток токена в журнале есть, но не сам токен")
def _():
    assert bridge_mod.token_fingerprint("abc") == bridge_mod.token_fingerprint("abc")
    assert bridge_mod.token_fingerprint("abc") != bridge_mod.token_fingerprint("abd")
    assert "abc" not in bridge_mod.token_fingerprint("abc")


@case("без ключа провайдера мост не стартует")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        token_file = Path(tmp) / "token.txt"
        token_file.write_text("t\n", encoding="utf-8")
        old = bridge_mod.os.environ.pop("HS_BRIDGE_KEY", None)
        try:
            code = bridge_mod.main([
                "--upstream", "https://example.test/v1/x", "--token-file", str(token_file)])
        finally:
            if old is not None:
                bridge_mod.os.environ["HS_BRIDGE_KEY"] = old
        assert code == 2, code


@case("не-https upstream отвергается")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        token_file = Path(tmp) / "token.txt"
        token_file.write_text("t\n", encoding="utf-8")
        code = bridge_mod.main([
            "--upstream", "http://example.test/v1/x", "--token-file", str(token_file)])
        assert code == 2, code


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            ok = True
        except AssertionError:
            ok = False
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {name}")
    print(f"\nмост: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
