"""Тесты сетевого слоя провайдера на локальном сервере. Интернет не нужен.

Проверяем: сборку ответа из SSE, коды ошибок, отсутствие ключа.
Запуск: python tests/test_http_provider.py
"""

from __future__ import annotations

import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.http_boundary import UpstreamError  # noqa: E402
from core.http_provider import OpenAICompatProvider  # noqa: E402
from core.provider import StreamError  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


SSE_OK = (
    'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
    'data: {"usage":{"prompt_tokens":3,"completion_tokens":1},"choices":[]}\n\n'
    'data: [DONE]\n\n'
)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # тишина в выводе тестов
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if "/fail" in self.path:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":"boom"}')
            return
        body = SSE_OK.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True


def _serve():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


@case("ответ собирается из SSE по сети", False)
def _():
    server, port = _serve()
    try:
        provider = OpenAICompatProvider(
            f"http://127.0.0.1:{port}",
            "test-model",
            "TEST_KEY_ABSENT",
            allow_loopback_http=True,
        )
        result = provider.complete([{"role": "user", "content": "hi"}], stream=True)
        assert result.status == 200, result.status
        assert result.reply.text == "ok", result.reply.text
        assert result.reply.usage["prompt_tokens"] == 3, result.reply.usage
        assert result.raw_chunks == 2, result.raw_chunks
    finally:
        server.shutdown()


@case("HTTP 500 превращается в отказ, а не в пустой ответ", True)
def _():
    server, port = _serve()
    try:
        provider = OpenAICompatProvider(
            f"http://127.0.0.1:{port}/fail",
            "test-model",
            "TEST_KEY_ABSENT",
            allow_loopback_http=True,
        )
        provider.complete([{"role": "user", "content": "hi"}], stream=True)
    finally:
        server.shutdown()


@case("без ключа провайдер сообщает об этом, а не молчит", False)
def _():
    provider = OpenAICompatProvider(
        "http://127.0.0.1:1",
        "m",
        "DEFINITELY_ABSENT_KEY_ENV",
        allow_loopback_http=True,
    )
    assert provider.has_key() is False


@case("provider redirect не переносит Authorization на target", False)
def _():
    canary = "hs-provider-" + secrets.token_hex(12)
    env_name = "HERNESS_TEST_PROVIDER_KEY"
    source_auth: list[str] = []
    target_auth: list[str] = []
    state = {"status": 302, "location": ""}

    class Source(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            source_auth.append(self.headers.get("Authorization", ""))
            self.send_response(state["status"])
            if state["location"]:
                self.send_header("Location", state["location"])
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

    class Target(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def _record(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            target_auth.append(self.headers.get("Authorization", ""))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

        do_GET = _record  # noqa: N802
        do_POST = _record  # noqa: N802

    source = ThreadingHTTPServer(("127.0.0.1", 0), Source)
    target = ThreadingHTTPServer(("127.0.0.1", 0), Target)
    threads = [
        threading.Thread(target=source.serve_forever, daemon=True),
        threading.Thread(target=target.serve_forever, daemon=True),
    ]
    for thread in threads:
        thread.start()
    old = os.environ.get(env_name)
    try:
        os.environ[env_name] = canary
        provider = OpenAICompatProvider(
            f"http://127.0.0.1:{source.server_port}",
            "test-model",
            env_name,
            allow_loopback_http=True,
        )
        for status in (301, 302, 303, 307, 308):
            state["status"] = status
            state["location"] = f"http://127.0.0.1:{target.server_port}/landing/{status}"
            try:
                provider.complete([{"role": "user", "content": "probe"}], stream=True)
            except StreamError as exc:
                assert str(exc) == "upstream redirect refused", str(exc)
            else:
                raise AssertionError(f"redirect {status} принят")
        assert source_auth == [f"Bearer {canary}"] * 5, "source должен получить ключ ровно пять раз"
        assert target_auth == [], "redirect target не должен получить ни одного запроса"
    finally:
        if old is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = old
        source.shutdown()
        target.shutdown()
        source.server_close()
        target.server_close()
        for thread in threads:
            thread.join(timeout=5)


@case("provider отвергает небезопасный base URL и несовпадение origin allowlist", False)
def _():
    cases = (
        ("https://user:pass@example.test/v1", {}),
        ("https://example.test:bad/v1", {}),
        ("http://example.test/v1", {}),
        ("https://example.test/v1?query=1", {}),
        ("https://example.test:444/v1", {"allowed_origins": ("https://example.test:443/v1",)}),
    )
    for url, kwargs in cases:
        try:
            OpenAICompatProvider(url, "m", "DEFINITELY_ABSENT_KEY_ENV", **kwargs)
        except UpstreamError:
            continue
        raise AssertionError(f"небезопасный base URL принят: {url}")


def main() -> int:
    failed = 0
    for name, should_raise, fn in CASES:
        try:
            fn()
            raised = False
        except (AssertionError, StreamError):
            raised = True
        ok = raised == should_raise
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {name}")
    print(f"\nсеть провайдера: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


