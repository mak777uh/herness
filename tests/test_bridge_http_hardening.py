"""W17 R2: изолированные проверки общих и построчных HTTP header limits.

Этот раунд не меняет 79 W17 markers и 8 review markers. Каждый control проверяет
одну границу парой «ровно предел / на единицу больше».
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import bridge as bridge_mod  # noqa: E402


class ChunkSocket:
    """Минимальный socket double: read_head видит только recv/settimeout."""

    def __init__(self, payload: bytes):
        self.payload = payload

    def settimeout(self, _value: float) -> None:
        pass

    def recv(self, _size: int) -> bytes:
        if not self.payload:
            return b""
        chunk, self.payload = self.payload, b""
        return chunk


def error_code(call) -> str | None:
    try:
        call()
    except bridge_mod._BridgeHTTPError as error:
        return error.code
    return None


def synthetic_head(header_count: int, line_size: int | None = None) -> bytes:
    lines = [b"POST /v1/chat/completions HTTP/1.1"]
    for index in range(header_count):
        name = f"X-{index}".encode("ascii")
        line = name + b": 1"
        if line_size is not None:
            line = name + b": " + b"a" * (line_size - len(name) - 2)
        lines.append(line)
    return b"\r\n".join(lines)


def header_total_boundary() -> None:
    expected = (
        bridge_mod.MAX_HEADER_LINE * (bridge_mod.MAX_HEADERS + 1)
        + 2 * bridge_mod.MAX_HEADERS
    )
    head = b"\r\n".join([b"x" * bridge_mod.MAX_HEADER_LINE] * (bridge_mod.MAX_HEADERS + 1))
    assert len(head) == expected == 9232, len(head)
    reader = bridge_mod._SocketReader(ChunkSocket(head + b"\r\n\r\n"))
    assert reader.read_head() == head

    oversized = head + b"x"
    reader = bridge_mod._SocketReader(ChunkSocket(oversized + b"\r\n\r\n"))
    assert error_code(reader.read_head) == "BRIDGE_HTTP_HEADER_LIMIT"


def header_count_boundary() -> None:
    at_limit = synthetic_head(bridge_mod.MAX_HEADERS)
    assert error_code(lambda: bridge_mod._parse_http_request(at_limit)) == "BRIDGE_HTTP_FORBIDDEN_HEADER"

    above_limit = synthetic_head(bridge_mod.MAX_HEADERS + 1)
    assert error_code(lambda: bridge_mod._parse_http_request(above_limit)) == "BRIDGE_HTTP_HEADER_LIMIT"


def header_line_boundary() -> None:
    at_limit = synthetic_head(1, bridge_mod.MAX_HEADER_LINE)
    assert error_code(lambda: bridge_mod._parse_http_request(at_limit)) == "BRIDGE_HTTP_FORBIDDEN_HEADER"

    above_limit = synthetic_head(1, bridge_mod.MAX_HEADER_LINE + 1)
    assert error_code(lambda: bridge_mod._parse_http_request(above_limit)) == "BRIDGE_HTTP_MALFORMED"


def main() -> int:
    checks = [
        ("header-total-boundary", header_total_boundary),
        ("header-count-boundary", header_count_boundary),
        ("header-line-boundary", header_line_boundary),
    ]
    failures = 0
    for label, check in checks:
        try:
            check()
        except Exception as exc:  # noqa: BLE001 — корпус печатает все провалы
            failures += 1
            print(f"[FAIL] {label}: {exc}")
        else:
            print(f"[ok] {label}")
    print(f"проверок: {len(checks)}; провалов: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
