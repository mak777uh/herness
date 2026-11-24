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
import hmac
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path
from socketserver import BaseRequestHandler

MAX_BODY = 8 * 1024 * 1024
# Канонический subset комнаты. Эти значения — контракт W17, а не настройки окружения.
HTTP_CONNECT_TIMEOUT = 5.0
HTTP_WRITE_TIMEOUT = 5.0
HTTP_HEADER_IDLE_TIMEOUT = 5.0
HTTP_TOTAL_TIMEOUT = 30.0
MAX_HEADER_LINE = 1024
MAX_HEADERS = 8
MAX_HEADER_BYTES = MAX_HEADER_LINE * (MAX_HEADERS + 1) + 2 * MAX_HEADERS
POST_ROUTES = frozenset({"/v1/chat/completions", "/v1/journal", "/v1/net"})
REQUEST_HEADERS = frozenset({
    "host", "authorization", "content-type", "content-length", "connection", "x-request-id",
})
# Корень репозитория: нужен, чтобы позвать bin/net.py по известному пути,
# а не по текущему каталогу процесса.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.http_boundary import (  # noqa: E402 — root added for `python bin/bridge.py`
    NoRedirectHandler,
    UpstreamError,
    build_no_redirect_opener,
    validate_upstream,
)

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")
ALLOWED_PREFIX = "/v1/"
REDIRECT_REFUSAL = b'{"error":"upstream redirect refused"}'

# Окружение внешнего помощника `net.py`: только то, без чего не запускается Python.
# Ключ провайдера живёт в окружении моста; если запускать дочерний процесс без env=,
# он наследует HS_BRIDGE_KEY и внешний слой (разбор чужого HTML) видит ключ первой
# комнаты. Поэтому здесь allowlist, а не копия os.environ: новое имя секрета не
# попадёт в ребёнка по умолчанию. PATH нужен для поиска программ, TEMP/TMP — для
# временных файлов; HOME, APPDATA, токены и прокси-переменные не передаются.
NET_CHILD_ENV = frozenset({
    "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
    "LANG", "LC_ALL", "PYTHONIOENCODING", "PYTHONUTF8",
})


def net_child_env(environ: dict[str, str] | None = None) -> dict[str, str]:
    """Окружение для /v1/net: allowlist, а не наследование секретов моста."""
    source = os.environ if environ is None else environ
    return {
        key: value
        for key, value in source.items()
        if key.upper() in NET_CHILD_ENV
    }


def token_fingerprint(token: str) -> str:
    """Отпечаток токена для журнала: по нему видно, кто звал, но не видно самого токена."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def read_token(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit(f"пустой файл токена: {path}")
    return text


def port_in_use(host: str, port: int) -> bool:
    """Занят ли порт: пробуем занять его сами и сразу отпускаем.

    Почему не «попробовать подключиться»: на Windows занятый порт может не
    отвечать на connect (процесс висит без обработки), и проверка соврала бы.
    Проба bind честнее: если занять не удалось — порт занят кем-то другим.

    SO_REUSEADDR здесь НЕ ставится намеренно: именно он позволял двум мостам
    слушать один порт, и второй висел вхолостую (F-BRIDGE-1).
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
        return False
    except OSError:
        return True
    finally:
        probe.close()


# Историческое имя сохранено для traceability прежнего redirect hotfix.
_NoRedirectHandler = NoRedirectHandler


def upstream_allowed(
    url: str,
    allow_loopback_http: bool = False,
    allowed_origins: tuple[str, ...] | None = None,
) -> tuple[bool, str]:
    """Проверить адрес провайдера до старта общей provider/bridge границей."""
    try:
        validate_upstream(
            url,
            allow_loopback_http=allow_loopback_http,
            allowed_origins=allowed_origins,
        )
    except UpstreamError as exc:
        return False, str(exc)
    return True, ""


class Bridge:
    def __init__(self, upstream: str, provider_key: str, local_token: str,
                 log_path: Path | None, session: str | None = None, *,
                 allow_loopback_http: bool = False,
                 allowed_origins: tuple[str, ...] | None = None):
        self.allow_loopback_http = allow_loopback_http
        self.allowed_origins = tuple(allowed_origins) if allowed_origins is not None else None
        allowed, why = upstream_allowed(
            upstream,
            allow_loopback_http=allow_loopback_http,
            allowed_origins=self.allowed_origins,
        )
        if not allowed:
            raise UpstreamError(why)
        self.upstream = upstream
        self.provider_key = provider_key
        self.local_token = local_token
        self.log_path = log_path
        # Сессия стабильна на весь процесс: при новом UUID на каждый запрос провайдер не отдаёт
        # prompt-cache (измерено: cache_read 512 против 0, allowance в 4,7 раза меньше).
        self.session = session or str(uuid.uuid4())
        self._unshare_ok: bool | None = None
        self._win_lowil_ok: bool | None = None

    def unshare_works(self, unshare: str) -> bool:
        """Рабочий ли unshare, а не только найденный в PATH.

        Наличие файла не значит, что user namespace разрешён: Ubuntu 24.04
        с apparmor_restrict_unprivileged_userns и CI-раннеры дают EPERM.
        Проба один раз; без рабочего namespace net.py не запускается (C-0329).
        """
        try:
            probe = subprocess.run(
                [unshare, "-U", "-p", "-f", "--mount-proc",
                 sys.executable, "-c", "pass"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=15, env=net_child_env(),
                close_fds=True,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return probe.returncode == 0

    def win_lowil_works(self, launcher: Path) -> bool:
        """Работает ли Windows-изоляция, а не только существует файл лаунчера.

        Проба запускает low-IL ребёнка и требует от него две вещи: собственный
        уровень целостности Low (S-1-16-4096) и запись в runs/net (иначе net.py
        упадёт на журнале). Наличие win_lowil.py без рабочего токена — отказ.
        """
        try:
            probe = subprocess.run(
                [sys.executable, str(launcher), "--probe"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60, env=net_child_env(),
                close_fds=True,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return probe.returncode == 0 and "LOWIL_PROBE=1" in (probe.stdout or "")

    def net_command(self, argv: list[str]) -> tuple[list[str], str]:
        """Команда /v1/net: Linux — PID-namespace, Windows — low IL, иначе отказ.

        Allowlist окружения закрывает наследование ключа, но не same-uid чтение
        окружения родителя. На Linux это делает PID-namespace (C-0328/C-0329),
        на Windows — low-integrity токен: medium-родителя нельзя открыть для
        чтения памяти через PEB (C-0330). Если механизма нет или он не работает,
        fail-closed без тихого запуска без изоляции. Это один канал, не K9.
        """
        command = [sys.executable, str(ROOT / "bin" / "net.py"), *argv]
        if sys.platform.startswith("linux"):
            unshare = shutil.which("unshare")
            if not unshare:
                return [], "unshare не найден: /v1/net выключен (fail-closed)"
            if self._unshare_ok is None:
                self._unshare_ok = self.unshare_works(unshare)
            if not self._unshare_ok:
                return [], "unshare не работает: /v1/net выключен (fail-closed)"
            return [unshare, "-U", "-p", "-f", "--mount-proc", *command], ""
        if not sys.platform.startswith("win"):
            return [], "нет механизма изоляции: /v1/net выключен (fail-closed)"
        launcher = ROOT / "bin" / "win_lowil.py"
        if not launcher.is_file():
            return [], "win_lowil не найден: /v1/net выключен (fail-closed)"
        if self._win_lowil_ok is None:
            self._win_lowil_ok = self.win_lowil_works(launcher)
        if not self._win_lowil_ok:
            return [], "win_lowil не работает: /v1/net выключен (fail-closed)"
        return [sys.executable, str(launcher), "--", *command], ""

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
            opener = build_no_redirect_opener(
                self.upstream,
                allow_loopback_http=self.allow_loopback_http,
                allowed_origins=self.allowed_origins,
            )
            with opener.open(request, timeout=180) as response:
                status = int(response.status)
                if 300 <= status < 400:
                    return 502, REDIRECT_REFUSAL, f"upstream redirect refused ({status})"
                return status, response.read(), ""
        except urllib.error.HTTPError as error:
            try:
                status = int(error.code)
                if 300 <= status < 400:
                    # Тело и Location источника не читаем и не отражаем: источник
                    # уже видел Authorization, но target не должен получить ничего.
                    return 502, REDIRECT_REFUSAL, f"upstream redirect refused ({status})"
                return status, error.read() or b"", f"upstream {status}"
            finally:
                error.close()
        except Exception as error:  # noqa: BLE001 — сеть, TLS, таймаут
            return 502, b"", f"upstream error: {type(error).__name__}"


class _BridgeHTTPError(Exception):
    """Типизированный отказ границы: код уходит клиенту, сырой запрос — никогда."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class _HTTPRequest:
    method: str
    path: str
    headers: dict[str, str]
    length: int
    token: str | None


_REQUEST_LINE = re.compile(r"([A-Za-z]+) ([!-~]+) (HTTP/[0-9]+(?:\.[0-9]+)?)\Z")
_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+\Z")
_HOST_VALUE = re.compile(
    r"(?:\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]+)(?::[0-9]{1,5})?\Z"
)
_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_LENGTH = re.compile(r"[1-9][0-9]*\Z")


def _has_bare_lf(data: bytes) -> bool:
    return any(byte == 0x0A and (index == 0 or data[index - 1] != 0x0D)
               for index, byte in enumerate(data))


def canonical_response_status(status: int) -> int:
    """Успех и ошибки сохраняются; остальные upstream statuses становятся 502."""
    return status if status == 200 or 400 <= status <= 599 else 502


class _SocketReader:
    """Чтение с общим wall deadline и без буферизации сверх объявленного body."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buffer = bytearray()
        self.started = time.monotonic()
        self.received_any = False

    def _receive(self, idle_timeout: float) -> None:
        remaining = HTTP_TOTAL_TIMEOUT - (time.monotonic() - self.started)
        if remaining <= 0:
            raise _BridgeHTTPError(408, "BRIDGE_HTTP_TIMEOUT", "total request timeout")
        self.sock.settimeout(min(idle_timeout, remaining))
        try:
            chunk = self.sock.recv(65536)
        except socket.timeout:
            raise _BridgeHTTPError(408, "BRIDGE_HTTP_TIMEOUT", "request read timeout") from None
        if not chunk:
            raise EOFError
        self.received_any = True
        self.buffer.extend(chunk)

    def read_head(self) -> bytes:
        while True:
            end = self.buffer.find(b"\r\n\r\n")
            if end >= 0:
                if end > MAX_HEADER_BYTES:
                    raise _BridgeHTTPError(400, "BRIDGE_HTTP_HEADER_LIMIT", "header block too large")
                head = bytes(self.buffer[:end])
                del self.buffer[:end + 4]
                return head
            if len(self.buffer) > MAX_HEADER_BYTES:
                raise _BridgeHTTPError(400, "BRIDGE_HTTP_HEADER_LIMIT", "header block too large")
            if _has_bare_lf(self.buffer):
                raise _BridgeHTTPError(400, "BRIDGE_HTTP_MALFORMED", "LF-only header grammar")
            idle = HTTP_HEADER_IDLE_TIMEOUT if self.received_any else HTTP_CONNECT_TIMEOUT
            self._receive(idle)

    def read_body(self, length: int) -> bytes:
        while len(self.buffer) < length:
            self._receive(HTTP_TOTAL_TIMEOUT)
        body = bytes(self.buffer[:length])
        del self.buffer[:length]
        return body

    def assert_no_trailing(self) -> None:
        if self.buffer:
            raise _BridgeHTTPError(400, "BRIDGE_HTTP_SMUGGLING", "bytes after request body")
        # Dispatch разрешён только после EOF. Иначе второй request может прийти
        # отдельным TCP-сегментом уже после zero-time проверки и до dispatch.
        while True:
            remaining = HTTP_TOTAL_TIMEOUT - (time.monotonic() - self.started)
            if remaining <= 0:
                raise _BridgeHTTPError(408, "BRIDGE_HTTP_TIMEOUT", "total request timeout")
            self.sock.settimeout(remaining)
            try:
                extra = self.sock.recv(65536)
            except socket.timeout:
                raise _BridgeHTTPError(
                    408, "BRIDGE_HTTP_TIMEOUT", "client did not half-close request",
                ) from None
            if not extra:
                return
            raise _BridgeHTTPError(400, "BRIDGE_HTTP_SMUGGLING", "bytes after request body")


def _parse_http_request(head: bytes) -> _HTTPRequest:
    lines = head.split(b"\r\n")
    if not lines or any(not line for line in lines):
        raise _BridgeHTTPError(400, "BRIDGE_HTTP_MALFORMED", "empty request line or header")
    if len(lines[0]) > MAX_HEADER_LINE or _has_bare_lf(head):
        raise _BridgeHTTPError(400, "BRIDGE_HTTP_MALFORMED", "bad request line grammar")
    try:
        request_line = lines[0].decode("ascii")
    except UnicodeDecodeError:
        raise _BridgeHTTPError(400, "BRIDGE_HTTP_MALFORMED", "non-ASCII request line") from None
    match = _REQUEST_LINE.fullmatch(request_line)
    if match is None:
        raise _BridgeHTTPError(400, "BRIDGE_HTTP_MALFORMED", "request line is not canonical")
    method, path, version = match.groups()
    if version != "HTTP/1.1":
        raise _BridgeHTTPError(400, "BRIDGE_HTTP_VERSION", "only HTTP/1.1 is accepted")
    if method not in {"GET", "POST"}:
        raise _BridgeHTTPError(405, "BRIDGE_HTTP_METHOD", "method is not accepted")
    if method == "GET" and path in POST_ROUTES:
        raise _BridgeHTTPError(405, "BRIDGE_HTTP_METHOD", "POST route requires POST")
    if method == "POST" and path == "/health":
        raise _BridgeHTTPError(405, "BRIDGE_HTTP_METHOD", "health route requires GET")
    if path not in POST_ROUTES | {"/health"}:
        raise _BridgeHTTPError(404, "BRIDGE_HTTP_PATH", "path is not in the canonical route set")
    if len(lines) - 1 > MAX_HEADERS:
        raise _BridgeHTTPError(400, "BRIDGE_HTTP_HEADER_LIMIT", "too many headers")

    headers: dict[str, str] = {}
    for line in lines[1:]:
        if len(line) > MAX_HEADER_LINE or line[:1] in (b" ", b"\t"):
            raise _BridgeHTTPError(400, "BRIDGE_HTTP_MALFORMED", "bad header line")
        if any(byte < 0x20 or byte > 0x7E for byte in line) or b":" not in line:
            raise _BridgeHTTPError(400, "BRIDGE_HTTP_MALFORMED", "bad header bytes")
        raw_name, raw_value = line.split(b":", 1)
        if _HEADER_NAME.fullmatch(raw_name.decode("ascii")) is None:
            raise _BridgeHTTPError(400, "BRIDGE_HTTP_MALFORMED", "bad header name")
        if not raw_value.startswith(b" "):
            raise _BridgeHTTPError(400, "BRIDGE_HTTP_MALFORMED", "header separator must be ': '")
        raw_value = raw_value[1:]
        name = raw_name.decode("ascii").lower()
        value = raw_value.decode("ascii")
        if name in headers:
            raise _BridgeHTTPError(400, "BRIDGE_HTTP_DUPLICATE_HEADER", "duplicate header")
        # Один ведущий пробел после двоеточия — разделитель, второй уже не каноничен.
        # Для Content-Length оставляем его лексическому парсеру: ожидаемый код BAD_LENGTH.
        if (value.startswith(" ") or value.endswith(" ")) and name != "content-length":
            raise _BridgeHTTPError(400, "BRIDGE_HTTP_MALFORMED", "non-canonical header value")
        headers[name] = value

    if "transfer-encoding" in headers:
        raise _BridgeHTTPError(400, "BRIDGE_HTTP_CHUNKED_FORBIDDEN", "transfer encoding is forbidden")
    if "expect" in headers:
        raise _BridgeHTTPError(400, "BRIDGE_HTTP_EXPECT_FORBIDDEN", "expect is forbidden")
    allowed = REQUEST_HEADERS if method == "POST" else frozenset({"host", "connection"})
    for name in headers:
        if name not in allowed:
            raise _BridgeHTTPError(400, "BRIDGE_HTTP_FORBIDDEN_HEADER", "header is not allowed")

    host = headers.get("host", "")
    if _HOST_VALUE.fullmatch(host) is None:
        raise _BridgeHTTPError(400, "BRIDGE_HTTP_BAD_HOST", "host is missing or malformed")
    if host.startswith("["):
        port_text = host[host.index("]") + 2:]
    elif ":" in host:
        port_text = host.rsplit(":", 1)[1]
    else:
        port_text = ""
    if port_text and not 1 <= int(port_text) <= 65535:
        raise _BridgeHTTPError(400, "BRIDGE_HTTP_BAD_HOST", "host port is out of range")
    if headers.get("connection", "").lower() != "close":
        raise _BridgeHTTPError(400, "BRIDGE_HTTP_CONNECTION", "connection must be close")
    if "x-request-id" in headers and _REQUEST_ID.fullmatch(headers["x-request-id"]) is None:
        raise _BridgeHTTPError(400, "BRIDGE_HTTP_MALFORMED", "bad request id")

    token: str | None = None
    length = 0
    if method == "POST":
        if headers.get("content-type", "").lower() != "application/json":
            raise _BridgeHTTPError(415, "BRIDGE_HTTP_CONTENT_TYPE", "content type must be application/json")
        authorization = headers.get("authorization", "")
        auth_match = re.fullmatch(r"(?i:Bearer) ([!-~]+)", authorization)
        if auth_match is None:
            raise _BridgeHTTPError(401, "BRIDGE_HTTP_UNAUTHORIZED", "local bearer token is required")
        token = authorization.split(" ", 1)[1]
        raw_length = headers.get("content-length", "")
        if _LENGTH.fullmatch(raw_length) is None:
            raise _BridgeHTTPError(400, "BRIDGE_HTTP_BAD_LENGTH", "content length is not canonical")
        length = int(raw_length)
        if length > MAX_BODY:
            raise _BridgeHTTPError(413, "BRIDGE_HTTP_LENGTH_CAP", "request body exceeds 8 MiB")
    return _HTTPRequest(method, path, headers, length, token)


def make_handler(bridge: Bridge):
    class Handler(BaseRequestHandler):
        def setup(self) -> None:
            # connect deadline принятого сокета и отдельный write deadline ответа.
            self.request.settimeout(HTTP_CONNECT_TIMEOUT)
            self._path = "?"

        def _respond(self, status: int, payload: bytes,
                     content_type: str = "application/json") -> None:
            status = canonical_response_status(status)
            reasons = {
                200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found",
                405: "Method Not Allowed", 408: "Request Timeout", 413: "Payload Too Large",
                415: "Unsupported Media Type", 429: "Too Many Requests", 500: "Internal Server Error",
                502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout",
            }
            reason = reasons.get(status, "Upstream Response")
            head = (
                f"HTTP/1.1 {status} {reason}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            self.request.settimeout(HTTP_WRITE_TIMEOUT)
            try:
                self.request.sendall(head + payload)
            except OSError:
                # Клиент уже ушёл; попытка ответа не должна печатать заголовки/тело в stderr.
                return

        def _reject(self, status: int, code: str, message: str) -> None:
            bridge.log({"ts": time.time(), "path": self._path, "status": status, "reason": code})
            payload = json.dumps(
                {"code": code, "message": message}, ensure_ascii=False, separators=(",", ":"),
            ).encode("utf-8")
            self._respond(status, payload)

        def _reject_problem(self, problem: _BridgeHTTPError) -> None:
            self._reject(problem.status, problem.code, problem.message)

        def handle(self) -> None:
            reader = _SocketReader(self.request)
            try:
                head = reader.read_head()
            except EOFError:
                return
            except _BridgeHTTPError as problem:
                self._reject_problem(problem)
                return
            except Exception:  # noqa: BLE001 — сырой запрос не попадает в traceback
                self._reject(500, "BRIDGE_HTTP_INTERNAL", "request parsing failed")
                return

            try:
                http_request = _parse_http_request(head)
                self._path = http_request.path
                if http_request.token is not None and not hmac.compare_digest(
                    http_request.token.encode("ascii"), bridge.local_token.encode("utf-8"),
                ):
                    raise _BridgeHTTPError(401, "BRIDGE_HTTP_UNAUTHORIZED", "invalid local token")
                body = reader.read_body(http_request.length) if http_request.method == "POST" else b""
                reader.assert_no_trailing()
            except EOFError:
                self._reject(400, "BRIDGE_HTTP_BAD_BODY", "request body ended early")
                return
            except _BridgeHTTPError as problem:
                self._reject_problem(problem)
                return
            except Exception:  # noqa: BLE001 — fail-closed без отражения входных данных
                self._reject(500, "BRIDGE_HTTP_INTERNAL", "request validation failed")
                return

            try:
                self._dispatch(http_request, body, reader.started)
            except _BridgeHTTPError as problem:
                self._reject_problem(problem)
            except Exception as error:  # noqa: BLE001 — в журнал только тип, не содержимое
                bridge.log({
                    "ts": time.time(), "path": self._path, "status": 500,
                    "reason": f"downstream: {type(error).__name__}",
                })
                self._reject(500, "BRIDGE_HTTP_INTERNAL", "downstream request failed")

        def _dispatch(self, http_request: _HTTPRequest, body: bytes, started: float) -> None:
            if http_request.method == "GET":
                self._respond(200, b'{"ok":true}')
                return

            # Приём событий журнала: авторитетную копию ведёт хост, комнате остаётся кэш.
            # Отдельный путь, чтобы «событие» нельзя было спутать с запросом к модели.
            if http_request.path == "/v1/journal":
                try:
                    from bin import host_journal  # запуск как модуль
                except Exception:  # noqa: BLE001 — запуск как `python bin/bridge.py`
                    try:
                        import host_journal  # type: ignore[no-redef]
                    except Exception as exc:  # noqa: BLE001
                        raise _BridgeHTTPError(
                            500, "BRIDGE_HTTP_JOURNAL_UNAVAILABLE",
                            f"журнал хоста недоступен: {type(exc).__name__}",
                        ) from None
                try:
                    request = json.loads(body.decode("utf-8"))
                    run = str(request["run"])
                    event = str(request["event"])
                except (ValueError, KeyError, TypeError) as exc:
                    bridge.log({"ts": time.time(), "path": self._path, "status": 400,
                                "reason": f"плохое событие: {type(exc).__name__}"})
                    raise _BridgeHTTPError(400, "BRIDGE_HTTP_BAD_JSON", "нужно {run, event}") from None
                try:
                    entry = host_journal.append(run, event)
                except OSError as exc:
                    bridge.log({"ts": time.time(), "path": self._path, "status": 500,
                                "reason": f"запись: {type(exc).__name__}"})
                    raise _BridgeHTTPError(500, "BRIDGE_HTTP_JOURNAL_WRITE", "не записать событие") from None
                bridge.log({"ts": time.time(), "path": self._path, "status": 200,
                            "run": run, "seq": entry["seq"]})
                answer = json.dumps(
                    {"seq": entry["seq"], "sha256": entry["sha256"]}, separators=(",", ":"),
                ).encode("utf-8")
                self._respond(200, answer)
                return

            # Выход в сеть для агента (ADR-0054): `search …`, `open 3`, `links`,
            # `follow 2`. Разбор — в bin/net.py, здесь только транспорт: мост не
            # ходит по адресам из запроса, он передаёт строку одному исполнителю.
            if http_request.path == "/v1/net":
                try:
                    request = json.loads(body.decode("utf-8"))
                    line = str(request["request"]).strip()
                except (ValueError, KeyError, TypeError):
                    raise _BridgeHTTPError(400, "BRIDGE_HTTP_BAD_JSON", "нужно {request}") from None
                if not line:
                    raise _BridgeHTTPError(400, "BRIDGE_HTTP_BAD_JSON", "пустой запрос")
                try:
                    # Разбор строки — как у оболочки, но без оболочки: shlex
                    # сохраняет кавычки («search "два слова"»), а split() их
                    # съедал, и запрос из трёх слов разваливался на три аргумента.
                    import shlex
                    try:
                        argv = shlex.split(line)
                    except ValueError:
                        argv = line.split()
                    command, why = bridge.net_command(argv)
                    if not command:
                        bridge.log({"ts": time.time(), "path": self._path, "status": 503,
                                    "reason": why})
                        raise _BridgeHTTPError(503, "BRIDGE_HTTP_NET_UNAVAILABLE", why)
                    result = subprocess.run(
                        command,
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", cwd=str(ROOT), timeout=120,
                        env=net_child_env(), close_fds=True,
                    )
                except subprocess.TimeoutExpired:
                    bridge.log({"ts": time.time(), "path": self._path, "status": 504,
                                "reason": "таймаут net"})
                    raise _BridgeHTTPError(504, "BRIDGE_HTTP_NET_TIMEOUT", "сеть не ответила за 120 с") from None
                output = (result.stdout or "").strip()
                error = (result.stderr or "").strip()
                # Лаунчер не смог поднять изоляцию уже после успешной пробы:
                # это отказ механизма, а не ошибка net.py; вызывающий видит 503.
                if result.returncode != 0 and "LOWIL_REFUSED=1" in error:
                    bridge.log({"ts": time.time(), "path": self._path, "status": 503,
                                "reason": "win_lowil отказал"})
                    raise _BridgeHTTPError(
                        503, "BRIDGE_HTTP_NET_ISOLATION", "win_lowil не смог запустить изоляцию (fail-closed)",
                    )
                bridge.log({"ts": time.time(), "path": self._path, "status": 200,
                            "cmd": line.split()[0], "code": result.returncode,
                            "bytes": len(output)})
                # Отказ возвращается как есть, с кодом: пустой список выглядел бы
                # как «ничего не нашлось» и соврал бы.
                answer = json.dumps(
                    {"output": output} if result.returncode == 0
                    else {"error": error.split(":")[0] or "net", "message": error or output},
                    ensure_ascii=False, separators=(",", ":"),
                ).encode("utf-8")
                self._respond(200, answer)
                return

            status, payload, reason = bridge.forward(
                body, http_request.path,
                {"content-type": http_request.headers.get("content-type", "")},
            )
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
                "path": self._path,
                "status": status,
                "bytes_in": len(body),
                "bytes_out": len(payload),
                "ms": round((time.monotonic() - started) * 1000),
                "token": token_fingerprint(http_request.token or ""),
                "reason": reason or None,
                "usage": usage or None,
                "session": token_fingerprint(bridge.session),
                # тела и заголовки не пишем: в них запрос пользователя и ключ провайдера
            })
            self._respond(status, payload)

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="мост выхода: HTTP внутри, HTTPS и ключ снаружи")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--allow-remote", action="store_true",
                        help="разрешить bind не на loopback (по умолчанию запрещено)")
    parser.add_argument("--allow-loopback-http", action="store_true",
                        help="test-only: разрешить http:// upstream на loopback")
    parser.add_argument("--upstream", required=True, help="полный URL провайдера")
    parser.add_argument("--token-file", required=True, help="файл с локальным токеном клиента")
    parser.add_argument("--log", default=None, help="файл журнала (по умолчанию stderr)")
    args = parser.parse_args(argv)

    if not args.allow_remote and args.bind not in ("127.0.0.1", "::1", "localhost"):
        print("мост слушает только loopback; для внешнего bind нужен --allow-remote", file=sys.stderr)
        return 2
    allowed, why = upstream_allowed(
        args.upstream,
        allow_loopback_http=args.allow_loopback_http,
        allowed_origins=(args.upstream,),
    )
    if not allowed:
        print(f"upstream отклонён: {why}", file=sys.stderr)
        return 2

    provider_key = os.environ.get("HS_BRIDGE_KEY", "").strip()
    if not provider_key:
        print("нет HS_BRIDGE_KEY: мост без ключа провайдера бесполезен", file=sys.stderr)
        return 2

    local_token = read_token(Path(args.token_file))
    log_path = Path(args.log) if args.log else None
    bridge = Bridge(
        args.upstream,
        provider_key,
        local_token,
        log_path,
        allow_loopback_http=args.allow_loopback_http,
        allowed_origins=(args.upstream,),
    )

    # F-BRIDGE-1 (09.11.2026). Раньше мост на занятом порту НЕ падал: у
    # ThreadingHTTPServer по умолчанию allow_reuse_address=1, и на Windows это
    # позволяет двум процессам слушать один порт. Второй висел вхолостую, не
    # получая ни одного запроса, и копился — в замере их набралось 29.
    # Теперь порт проверяется до запуска, и занятый даёт внятный отказ с кодом,
    # а не тихое зависание.
    if port_in_use(args.bind, args.port):
        print(f"порт {args.bind}:{args.port} уже занят — второй мост не нужен "
              f"и не запускается (иначе процессы копятся)", file=sys.stderr)
        return 3

    server = ThreadingHTTPServer((args.bind, args.port), make_handler(bridge))
    print(f"мост: http://{args.bind}:{args.port} -> {args.upstream}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        # Сокет закрывается явно: без этого порт остаётся занятым до выхода
        # процесса, и следующий запуск упирается в ту же ловушку.
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

