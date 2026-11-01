"""bridge — мост выхода: комната говорит по HTTP, ключ провайдера живёт на хосте.

Зачем свой, если есть готовые шлюзы. Проверено по первичным источникам 31.10.2026:

* LiteLLM — компрометация цепочки поставки: вендор сам подтверждает, что 21.10.2026 в Docker и
  PyPI уехал `v1.107.0` со скомпилированным вредоносным кодом, который крадёт учётные данные, и
  жил ~2 часа; подпись cosign после этого перевыпускали. Это ровно тот компонент, который держит
  ключ, — то есть цена готового решения попадает ровно в нашу границу доверия.
* Agent Router (бывш. Envoy AI Gateway) — существует, Apache-2.0, OpenAI-совместимый; но нативный
  Windows-рантайм и аутентификация локального клиента не подтверждены.
* one-api / new-api / Portkey / Helicone — старые, AGPL-RC, заброшенные или хранят ключи открытым
  текстом; у каждого свой повод не брать.

Поэтому мост — свой и минимальный: один провайдер, один клиент, ключ не покидает хост. Никакой
криптографии своего кода: TLS делает стандартная библиотека Python.

Что он делает:
  комната → POST /v1/chat/completions  (Authorization: Bearer <локальный токен>)
  мост    → HTTPS к провайдеру          (Authorization: Bearer <настоящий ключ>)
  журнал  → одна строка JSON на запрос: время, путь, код, байты, длительность, отпечаток токена.

Чего он не делает и не должен:
  * не логирует тела запросов и ответов, заголовки, ключи и токены (по образцу аудита Codex:
    решение и адрес — да, содержимое — нет);
  * не ходит по адресам из запроса (upstream задан при запуске; иначе это SSRF-дверь);
  * не слушает не-loopback без явного `--allow-remote`.

Запуск:
  HS_BRIDGE_KEY=... python bin/bridge.py --token-file C:/111/env/secrets/bridge-token.txt \\
      --upstream https://api.deepseek.com/v1/chat/completions
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY = 8 * 1024 * 1024
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")
ALLOWED_PREFIX = "/v1/"


def token_fingerprint(token: str) -> str:
    """Отпечаток токена для журнала: по нему видно, кто звал, но не видно самого токена."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def read_token(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit(f"пустой файл токена: {path}")
    return text


def upstream_allowed(url: str) -> tuple[bool, str]:
    """Проверить адрес провайдера до старта.

    https обязателен всегда, кроме одного случая: локальная заглушка на loopback для тестов.
    Открытый текст наружу — это ключ в открытом виде, а не «удобство разработки».
    """
    lowered = url.lower()
    if lowered.startswith("https://"):
        return True, ""
    if lowered.startswith("http://"):
        host = lowered[7:].split("/")[0].split(":")[0]
        if host in ("127.0.0.1", "localhost", "::1"):
            return True, ""
        return False, "http:// допустим только для loopback-заглушки"
    return False, "upstream должен начинаться с https://"


class Bridge:
    def __init__(self, upstream: str, provider_key: str, local_token: str,
                 log_path: Path | None, session: str | None = None):
        self.upstream = upstream
        self.provider_key = provider_key
        self.local_token = local_token
        self.log_path = log_path
        # Сессия стабильна на весь процесс: при новом UUID на каждый запрос провайдер не отдаёт
        # prompt-cache (измерено: cache_read 512 против 0, allowance в 4,7 раза меньше).
        self.session = session or str(uuid.uuid4())

    def log(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False)
        if self.log_path is None:
            print(line, file=sys.stderr, flush=True)
        else:
            with open(self.log_path, "a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")

    def forward(self, body: bytes, path: str, headers: dict) -> tuple[int, bytes, str]:
        """Переслать запрос провайдеру. Ошибки — типизированные, не «что-то пошло не так»."""
        request = urllib.request.Request(self.upstream, data=body, method="POST")
        # Ключ ставим здесь и только здесь: комната его не видит и не может увидеть.
        request.add_header("Authorization", f"Bearer {self.provider_key}")
        # Провайдер требует браузерный UA и идентификатор сессии; иначе 403/400 до модели.
        request.add_header("User-Agent", BROWSER_UA)
        request.add_header("x-opencode-session", self.session)
        request.add_header("Content-Type", headers.get("content-type", "application/json"))
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return int(response.status), response.read(), ""
        except urllib.error.HTTPError as error:
            return int(error.code), error.read() or b"", f"upstream {error.code}"
        except Exception as error:  # noqa: BLE001 — сеть, TLS, таймаут
            return 502, b"", f"upstream error: {type(error).__name__}"


def make_handler(bridge: Bridge):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # noqa: D401 — глушим стандартный лог: он пишет URL
            return

        def _reject(self, code: int, reason: str) -> None:
            payload = json.dumps({"error": reason}, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802 — имя требует http.server
            started = time.monotonic()
            if not self.path.startswith(ALLOWED_PREFIX):
                bridge.log({"ts": time.time(), "path": "?", "status": 404, "reason": "путь вне /v1"})
                self._reject(404, "только /v1/*")
                return

            auth = self.headers.get("Authorization", "")
            token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            if not token or token != bridge.local_token:
                bridge.log({
                    "ts": time.time(), "path": self.path, "status": 401,
                    "reason": "неверный локальный токен",
                })
                self._reject(401, "нужен локальный токен моста")
                return

            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                bridge.log({"ts": time.time(), "path": self.path, "status": 413,
                            "reason": f"длина {length}"})
                self._reject(413, "тело пустое или слишком большое")
                return

            body = self.rfile.read(length)
            # Приём событий журнала: авторитетную копию ведёт хост, комнате остаётся кэш.
            # Отдельный путь, чтобы «событие» нельзя было спутать с запросом к модели.
            if self.path.rstrip("/") == "/v1/journal":
                try:
                    from bin import host_journal  # запуск как модуль
                except Exception:  # noqa: BLE001 — запуск как `python bin/bridge.py`
                    try:
                        import host_journal  # type: ignore[no-redef]
                    except Exception as exc:  # noqa: BLE001
                        self._reject(500, f"журнал хоста недоступен: {type(exc).__name__}")
                        return
                try:
                    request = json.loads(body.decode("utf-8"))
                    run = str(request["run"])
                    event = str(request["event"])
                except (ValueError, KeyError, TypeError) as exc:
                    bridge.log({"ts": time.time(), "path": self.path, "status": 400,
                                "reason": f"плохое событие: {type(exc).__name__}"})
                    self._reject(400, "нужно {run, event}")
                    return
                try:
                    entry = host_journal.append(run, event)
                except OSError as exc:
                    bridge.log({"ts": time.time(), "path": self.path, "status": 500,
                                "reason": f"запись: {type(exc).__name__}"})
                    self._reject(500, "не записать событие")
                    return
                bridge.log({"ts": time.time(), "path": self.path, "status": 200,
                            "run": run, "seq": entry["seq"]})
                answer = json.dumps({"seq": entry["seq"], "sha256": entry["sha256"]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(answer)))
                self.end_headers()
                self.wfile.write(answer)
                return
            status, payload, reason = bridge.forward(
                body, self.path, {"content-type": self.headers.get("Content-Type", "")})
            usage = {}
            try:
                parsed = json.loads(payload.decode("utf-8"))
                oc = ((parsed.get("usage") or {}).get("opencode") or {})
                usage = {
                    "allowance": oc.get("allowance"),
                    "cache_read": (oc.get("tokens") or {}).get("cache_read"),
                }
            except Exception:  # noqa: BLE001 — тело может быть не JSON
                usage = {}
            bridge.log({
                "ts": time.time(),
                "path": self.path,
                "status": status,
                "bytes_in": len(body),
                "bytes_out": len(payload),
                "ms": round((time.monotonic() - started) * 1000),
                "token": token_fingerprint(token),
                "reason": reason or None,
                "usage": usage or None,
                "session": token_fingerprint(bridge.session),
                # тела и заголовки не пишем: в них запрос пользователя и ключ провайдера
            })
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                payload = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self._reject(404, "только POST /v1/*")

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="мост выхода: HTTP внутри, HTTPS и ключ снаружи")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--allow-remote", action="store_true",
                        help="разрешить bind не на loopback (по умолчанию запрещено)")
    parser.add_argument("--upstream", required=True, help="полный URL провайдера")
    parser.add_argument("--token-file", required=True, help="файл с локальным токеном клиента")
    parser.add_argument("--log", default=None, help="файл журнала (по умолчанию stderr)")
    args = parser.parse_args(argv)

    if not args.allow_remote and args.bind not in ("127.0.0.1", "::1", "localhost"):
        print("мост слушает только loopback; для внешнего bind нужен --allow-remote", file=sys.stderr)
        return 2
    allowed, why = upstream_allowed(args.upstream)
    if not allowed:
        print(f"upstream отклонён: {why}", file=sys.stderr)
        return 2

    provider_key = os.environ.get("HS_BRIDGE_KEY", "").strip()
    if not provider_key:
        print("нет HS_BRIDGE_KEY: мост без ключа провайдера бесполезен", file=sys.stderr)
        return 2

    local_token = read_token(Path(args.token_file))
    log_path = Path(args.log) if args.log else None
    bridge = Bridge(args.upstream, provider_key, local_token, log_path)
    server = ThreadingHTTPServer((args.bind, args.port), make_handler(bridge))
    print(f"мост: http://{args.bind}:{args.port} -> {args.upstream}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

