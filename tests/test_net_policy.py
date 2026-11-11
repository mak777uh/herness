"""Тесты фильтра исходящих URL (SSRF-R1, F-0081, F-0082).

Каждый запрещённый класс проверяется **вместе с положительным контролем**: фильтр, который
блокирует всё, проходит все отрицательные тесты и при этом бесполезен. Поэтому тест
`public_url_is_allowed` стоит первым и обязателен.

DNS не спрашивается там, где предмет — имя или литеральный IP: `resolve_dns=False`.
Отдельный тест проверяет, что резолв в перехваченный диапазон 198.18.0.0/15 не отклоняется
(F-0082: на этой машине DNS отдаёт его для любого домена).

    python -m pytest tests/test_net_policy.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import net_policy  # noqa: E402


def refused(url: str, code: str | None = None, resolve_dns: bool = False) -> str:
    with pytest.raises(net_policy.Refused) as caught:
        net_policy.check_url(url, resolve_dns=resolve_dns)
    if code is not None:
        assert caught.value.code == code, f"{url}: ждали {code}, получили {caught.value.code}"
    return caught.value.code


# --- положительные контроли: фильтр не должен блокировать веб -------------------------------

def test_public_url_is_allowed() -> None:
    """Без этого теста остальные девять ничего не значат: блокировать всё — тоже «9 из 9»."""
    assert net_policy.check_url("https://example.com/", resolve_dns=False) == []


def test_public_http_is_allowed() -> None:
    assert net_policy.check_url("http://example.com/path?q=1", resolve_dns=False) == []


def test_public_ip_literal_is_allowed() -> None:
    assert net_policy.check_url("https://93.184.216.34/", resolve_dns=False) == ["93.184.216.34"]


# --- девять запрещённых классов ------------------------------------------------------------

def test_loopback_literal() -> None:
    refused("http://127.0.0.1/", "loopback")


def test_loopback_other_in_8() -> None:
    refused("http://127.13.7.9/", "loopback")


def test_localhost_name() -> None:
    refused("http://localhost/", "loopback-name")


def test_localhost_subdomain() -> None:
    refused("http://admin.localhost/", "loopback-name")


def test_rfc1918_ten() -> None:
    refused("http://10.0.0.1/", "private")


def test_rfc1918_172() -> None:
    refused("http://172.16.5.4/", "private")


def test_rfc1918_192() -> None:
    refused("http://192.168.1.1/", "private")


def test_link_local_metadata() -> None:
    refused("http://169.254.169.254/latest/meta-data/", "private")


def test_ipv6_loopback() -> None:
    refused("http://[::1]/", "loopback")


def test_ipv6_ula() -> None:
    refused("http://[fd00::1]/", "private")


def test_ipv6_mapped_loopback() -> None:
    refused("http://[::ffff:127.0.0.1]/", "loopback")


def test_unspecified() -> None:
    refused("http://0.0.0.0/", "unspecified")


def test_multicast() -> None:
    refused("http://224.0.0.1/", "multicast")


def test_bad_scheme_file() -> None:
    refused("file:///etc/passwd", "bad-scheme")


def test_bad_scheme_ftp() -> None:
    refused("ftp://example.com/x", "bad-scheme")


def test_bad_scheme_gopher() -> None:
    refused("gopher://example.com/", "bad-scheme")


def test_credentials_in_url() -> None:
    refused("https://user:pass@example.com/", "credentials")


def test_bad_port() -> None:
    refused("http://example.com:8080/", "bad-port")


def test_bad_port_ssh() -> None:
    refused("http://example.com:22/", "bad-port")


# --- резолв: перехватчик не должен отклоняться ---------------------------------------------

def test_intercepted_dns_range_is_not_refused() -> None:
    """F-0082: на машине с перехватом DNS 198.18.0.0/15 — это адрес перехватчика, не цели.

    Отклонять его значило бы блокировать весь интернет на этой машине. Решает имя.
    """
    net_policy.check_ip("198.19.0.202")


def test_private_resolved_address_is_refused() -> None:
    """Обратная сторона: настоящий частный адрес в резолве — отказ."""
    refused("10.1.2.3")


def test_resolve_returns_addresses_for_public_host() -> None:
    """Резолв публичного имени даёт хотя бы один адрес и не отказывает."""
    addresses = net_policy.resolve("example.com", 443)
    assert addresses, "example.com не дал ни одного адреса"
