"""Тесты сетевого слоя провайдера на локальном сервере. Интернет не нужен.

Проверяем: сборку ответа из SSE, коды ошибок, отсутствие ключа.
Запуск: python tests/test_http_provider.py
"""

from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
        provider = OpenAICompatProvider(f"http://127.0.0.1:{port}", "test-model", "TEST_KEY_ABSENT")
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
        provider = OpenAICompatProvider(f"http://127.0.0.1:{port}/fail", "test-model", "TEST_KEY_ABSENT")
        provider.complete([{"role": "user", "content": "hi"}], stream=True)
    finally:
        server.shutdown()


@case("без ключа провайдер сообщает об этом, а не молчит", False)
def _():
    provider = OpenAICompatProvider("http://127.0.0.1:1", "m", "DEFINITELY_ABSENT_KEY_ENV")
    assert provider.has_key() is False


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


