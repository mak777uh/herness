"""net_policy — что мост вправе открыть от имени агента (F-0081, SSRF).

Зачем отдельный модуль, а не проверка внутри `net.py`. Проверка нужна в двух местах —
на стартовом адресе и на **каждом** redirect, — и оба обязаны спрашивать одно и то же
правило. Две копии правила разойдутся, и это ровно тот класс, что чинится весь ноябрь.

Граница честности. Модуль отвечает на вопрос «можно ли открыть этот адрес», а не «безопасен
ли ответ». Он не защищает от вредного содержимого страницы, от утечки через DNS-запрос
(имя уходит резолверу до проверки) и от подмены DNS между проверкой и соединением —
последнее закрывается сверкой фактического адреса сокета, и это делает вызывающая сторона.

    python bin/net_policy.py check https://example.com
    python bin/net_policy.py check http://127.0.0.1:8080/admin
"""

from __future__ import annotations

import ipaddress
import socket
import sys
import urllib.parse

# Порты, к которым мост ходит. Список короткий намеренно: 80 и 443 — это веб, всё остальное
# требует отдельного решения и отдельной строки здесь.
ALLOWED_PORTS = {80, 443}

# Схемы. `file:`, `ftp:`, `gopher:`, `data:` и прочее не открываются никогда: мост — не
# универсальный загрузчик, а окно в веб.
ALLOWED_SCHEMES = {"http", "https"}

# Имена, которые резолвятся в локальную машину по соглашению, а не по DNS.
LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


class Refused(Exception):
    """Адрес отклонён. `code` — машиночитаемая причина, `why` — для человека."""

    def __init__(self, code: str, why: str) -> None:
        super().__init__(f"{code}: {why}")
        self.code = code
        self.why = why


def _refuse(code: str, why: str) -> None:
    raise Refused(code, why)


def check_scheme(scheme: str) -> None:
    if scheme.lower() not in ALLOWED_SCHEMES:
        _refuse("bad-scheme", f"схема {scheme!r} не открывается: только http и https")


def check_credentials(url: str) -> None:
    """`http://user:pass@host/` — логин в адресе. Мост не передаёт чужие учётные данные."""
    parts = urllib.parse.urlsplit(url)
    if parts.username or parts.password:
        _refuse("credentials", "логин или пароль в адресе запрещён")


def check_host_name(host: str) -> None:
    if not host:
        _refuse("no-host", "в адресе нет хоста")
    lowered = host.lower().rstrip(".")
    if lowered in LOCAL_NAMES or lowered.endswith(".localhost"):
        _refuse("loopback-name", f"имя {host!r} указывает на эту машину")


def check_port(port: int | None, scheme: str) -> None:
    effective = port if port is not None else (443 if scheme.lower() == "https" else 80)
    if effective not in ALLOWED_PORTS:
        _refuse("bad-port", f"порт {effective} не разрешён: только 80 и 443")


def check_ip(address: str) -> None:
    """Запрещённые диапазоны. Проверка по объекту `ipaddress`, а не по строке.

    Строковая проверка (`startswith("10.")`) пропускает `010.0.0.1` и `10.0.0.1.nip.io`,
    поэтому адрес сначала разбирается, а потом проверяется по классу.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        _refuse("bad-ip", f"{address!r} не разбирается как IP")
    if ip.is_loopback:
        _refuse("loopback", f"{address} — loopback")
    # 198.18.0.0/15 — диапазон benchmarking (RFC 2544). На машине с перехватом DNS он
    # отдаётся для ЛЮБОГО домена (F-0082: example.com, github.com, tokio.rs -> 198.19.0.x),
    # поэтому судить по нему, куда пойдёт соединение, нельзя: это адрес перехватчика, а не
    # цели. Такой адрес не отклоняем и не считаем доказательством внешности — решает имя.
    if ip in ipaddress.ip_network("198.18.0.0/15"):
        return
    # `0.0.0.0` в Python 3.13 помечен и как private, и как unspecified. Порядок важен:
    # unspecified проверяется раньше, иначе отказ называет не ту причину.
    if ip.is_unspecified:
        _refuse("unspecified", f"{address} — 0.0.0.0 или ::")
    if ip.is_private:
        _refuse("private", f"{address} — частный диапазон")
    if ip.is_link_local:
        _refuse("link-local", f"{address} — link-local (в том числе metadata 169.254.169.254)")
    if ip.is_multicast:
        _refuse("multicast", f"{address} — multicast")
    if ip.is_reserved:
        _refuse("reserved", f"{address} — зарезервированный диапазон")
    if ip.is_unspecified:
        _refuse("unspecified", f"{address} — 0.0.0.0 или ::")
    # IPv4, отображённый в IPv6 (`::ffff:127.0.0.1`), разбирается как IPv6 и проходит
    # проверки выше только если `is_private` его ловит. Проверяем явно.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        check_ip(str(ip.ipv4_mapped))


def resolve(host: str, port: int | None) -> list[str]:
    """Все адреса, в которые резолвится имя. Пустой список — отказ."""
    try:
        infos = socket.getaddrinfo(host, port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror as error:
        _refuse("dns", f"{host} не резолвится: {error}")
    addresses = []
    for info in infos:
        address = info[4][0]
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        _refuse("dns", f"{host} не дал ни одного адреса")
    return addresses


def check_url(url: str, *, resolve_dns: bool = True) -> list[str]:
    """Проверить адрес целиком. Возвращает список IP, в которые он резолвится.

    `resolve_dns=False` — для тестов без сети: проверяются схема, логин, имя и порт.
    """
    parts = urllib.parse.urlsplit(url)
    check_scheme(parts.scheme)
    check_credentials(url)
    if parts.fragment:
        # Фрагмент не уходит на сервер, но и смысла в нём нет: адрес пришёл от агента.
        pass
    host = parts.hostname or ""
    check_host_name(host)
    check_port(parts.port, parts.scheme)
    # Хост может быть литеральным IP — тогда DNS не нужен.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        check_ip(str(literal))
        return [str(literal)]
    if not resolve_dns:
        return []
    addresses = resolve(host, parts.port)
    for address in addresses:
        check_ip(address)
    return addresses


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "check" or len(argv) < 2:
        print("нужно: net_policy.py check <url>", file=sys.stderr)
        return 2
    try:
        addresses = check_url(argv[1])
    except Refused as refusal:
        print(f"ОТКАЗ {refusal.code}: {refusal.why}")
        return 1
    print(f"РАЗРЕШЁН {argv[1]} -> {', '.join(addresses) or '(без DNS)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
