"""fake_upstream — заглушка провайдера для проверки моста без сети и без ключей.

Отвечает на любой POST фиксированным JSON в формате OpenAI-совместимого ответа. Нужна, чтобы
проверить цепочку «комната → мост → провайдер» целиком, не тратя денег и не трогая настоящий ключ.

    python bin/fake_upstream.py --port 8801 --content "DONE проверено"
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def make_handler(content: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            return

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            reply = {
                "id": "fake-1",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
                # Размер входа возвращаем, чтобы было видно, что тело дошло.
                "usage": {"prompt_tokens": len(body), "completion_tokens": len(content)},
            }
            payload = json.dumps(reply, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="заглушка провайдера для проверки моста")
    parser.add_argument("--port", type=int, default=8801)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--content", default="DONE проверено")
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.bind, args.port), make_handler(args.content))
    print(f"заглушка провайдера: http://{args.bind}:{args.port}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
