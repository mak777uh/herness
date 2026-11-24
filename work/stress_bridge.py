"""Нагрузочная проверка моста: переживает ли он серию запросов подряд.

Зачем: в прогоне новых задач мост исчез посреди работы (health 000), и прогон
оборвался на 5 из 10. Нужно понять, падает ли он от нагрузки, или это был
внешний случай.

Проверяем: N запросов /v1/net подряд, после каждого — health.

    python work/stress_bridge.py [N]
"""

from __future__ import annotations

import http.client
import json
import pathlib
import socket
import sys
import time

TOKEN = pathlib.Path(r"C:\111\env\bridge-token.txt").read_text(encoding="utf-8").strip()


def exchange(method: str, path: str, headers: list[tuple[str, str]],
             body: bytes = b"", timeout: float = 120) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", 8790, timeout=timeout)
    try:
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for name, value in headers:
            connection.putheader(name, value)
        connection.endheaders(body)
        connection.sock.shutdown(socket.SHUT_WR)
        response = connection.getresponse()
        return int(response.status), response.read()
    finally:
        connection.close()


def health() -> int:
    try:
        status, _ = exchange(
            "GET", "/health", [("Host", "127.0.0.1:8790"), ("Connection", "close")],
            timeout=5,
        )
        return status
    except Exception:  # noqa: BLE001
        return 0


def net_call(line: str) -> tuple[int, str]:
    body = json.dumps({"request": line}).encode()
    try:
        status, payload = exchange(
            "POST", "/v1/net",
            [
                ("Host", "127.0.0.1:8790"),
                ("Authorization", f"Bearer {TOKEN}"),
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body))),
                ("Connection", "close"),
            ],
            body,
        )
        if status != 200:
            return status, f"HTTP {status}"
        return status, json.loads(payload).get("error", "ok")
    except Exception as error:  # noqa: BLE001
        return 0, f"{type(error).__name__}: {error}"


def main(argv: list[str]) -> int:
    count = int(argv[0]) if argv else 5
    print(f"мост до нагрузки: health {health()}")
    for index in range(1, count + 1):
        status, note = net_call("links")
        alive = health()
        print(f"  {index}: /v1/net -> {status} ({note}), health {alive}")
        if alive != 200:
            print(f"  МОСТ УПАЛ после {index} запросов")
            return 1
        time.sleep(0.5)
    print(f"мост выжил после {count} запросов")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
