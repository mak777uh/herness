"""Общая граница HTTP-провайдера: точный origin и запрет redirect.

Мост и прямой OpenAI-совместимый клиент обязаны использовать один контракт:
адрес задаётся конфигурацией, credentials в URL запрещены, HTTP допускается
только для явно test-only loopback, а 3xx никогда не становится новым destino
с Authorization. Значение ключа здесь не обрабатывается и не журналируется.
"""

from __future__ import annotations

import ipaddress
import urllib.parse
import urllib.request
from collections.abc import Iterable


class UpstreamError(ValueError):
    """Конфигурация upstream не проходит security boundary."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Отказать любому 3xx до чтения тела и Location."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _parse(url: str) -> tuple[urllib.parse.SplitResult, str, int | None]:
    if not isinstance(url, str) or not url:
        raise UpstreamError("upstream пуст")
    if any(ord(char) <= 0x20 or ord(char) == 0x7F for char in url):
        raise UpstreamError("upstream содержит управляющий символ или пробел")
    if "\\" in url:
        raise UpstreamError("upstream содержит обратный слеш")
    try:
        parts = urllib.parse.urlsplit(url)
        hostname = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise UpstreamError("upstream имеет неоднозначный host/port") from exc
    if parts.scheme not in {"http", "https"}:
        raise UpstreamError("upstream должен использовать http или https")
    if not parts.netloc or not hostname:
        raise UpstreamError("upstream без host")
    if parts.username is not None or parts.password is not None:
        raise UpstreamError("credentials в URL запрещены")
    if "%" in parts.netloc:
        raise UpstreamError("percent-encoding в host/port запрещён")
    if parts.netloc.endswith(":"):
        raise UpstreamError("upstream содержит пустой port")
    host = hostname.rstrip(".").lower()
    if not host:
        raise UpstreamError("upstream без host")
    if port is not None and not 1 <= port <= 65535:
        raise UpstreamError("upstream port вне 1..65535")
    return parts, host, port


def origin_of(url: str) -> str:
    """Канонический origin для точного hostname/port allowlist."""
    parts, host, port = _parse(url)
    default_port = 443 if parts.scheme == "https" else 80
    rendered_host = f"[{host}]" if ":" in host else host
    return f"{parts.scheme}://{rendered_host}:{port or default_port}"


def is_loopback_url(url: str) -> bool:
    _, host, _ = _parse(url)
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_upstream(
    url: str,
    *,
    allow_loopback_http: bool = False,
    allowed_origins: Iterable[str] | None = None,
) -> str:
    """Проверить точный configured destination до создания запроса.

    `allowed_origins` — явный список origin без path/query. Если он задан,
    сравнение выполняется по каноническим scheme/hostname/port, а не по строке.
    """
    parts, host, _ = _parse(url)
    if parts.scheme == "http" and not (allow_loopback_http and is_loopback_url(url)):
        raise UpstreamError("http:// допустим только для явного test-only loopback")
    if allowed_origins is not None:
        allowed = {origin_of(item) for item in allowed_origins}
        if not allowed:
            raise UpstreamError("upstream origin allowlist пуст")
        if origin_of(url) not in allowed:
            raise UpstreamError("upstream origin не входит в точный allowlist")
    return url


def validate_base_url(
    url: str,
    *,
    allow_loopback_http: bool = False,
    allowed_origins: Iterable[str] | None = None,
) -> str:
    """Base URL провайдера: без query/fragment, к нему добавляется endpoint."""
    validate_upstream(
        url,
        allow_loopback_http=allow_loopback_http,
        allowed_origins=allowed_origins,
    )
    parts, _, _ = _parse(url)
    if parts.query or parts.fragment:
        raise UpstreamError("base URL провайдера не должен содержать query/fragment")
    return url


def build_no_redirect_opener(
    url: str,
    *,
    allow_loopback_http: bool = False,
    allowed_origins: Iterable[str] | None = None,
) -> urllib.request.OpenerDirector:
    """Opener для provider/bridge: redirect off, loopback минует системный proxy."""
    validate_upstream(
        url,
        allow_loopback_http=allow_loopback_http,
        allowed_origins=allowed_origins,
    )
    handlers: list[urllib.request.BaseHandler] = [NoRedirectHandler()]
    if is_loopback_url(url):
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)
