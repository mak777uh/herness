"""Тесты сетевого инструмента: локальный сервер, никакой сети.

Проверяется то, что легко сломать: классификация (ok/blocked/not_found), лимит байтов,
кодировка и отказ для не-http схем.
"""

from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.webfetch import fetch  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_GET(self):
        if self.path == "/ok":
            body = "<html><body>привет</body></html>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/big":
            body = b"x" * 5000
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/captcha":
            body = b"<html><title>Just a moment...</title></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/forbidden":
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()


SERVER = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{SERVER.server_address[1]}"


@case("обычная страница читается", False)
def _():
    result = fetch(BASE + "/ok")
    assert result.ok and "привет" in result.text, result.to_dict()


@case("404 отличается от отказа", False)
def _():
    assert fetch(BASE + "/missing").kind == "not_found"


@case("403 — это blocked, а не not_found", False)
def _():
    assert fetch(BASE + "/forbidden").kind == "blocked"


@case("капча в теле при статусе 200 — blocked", False)
def _():
    assert fetch(BASE + "/captcha").kind == "blocked"


@case("лимит байтов соблюдается и отмечается", False)
def _():
    result = fetch(BASE + "/big", max_bytes=100)
    assert result.truncated and result.bytes_read == 100, result.to_dict()


@case("схема кроме http/https — отказ", False)
def _():
    assert fetch("file:///etc/passwd").kind == "error"


def main() -> int:
    failed = 0
    for name, should_raise, fn in CASES:
        try:
            fn()
            raised = False
        except AssertionError:
            raised = True
        ok = raised == should_raise
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {name}")
    SERVER.shutdown()
    print(f"\nсеть: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
