"""Нагрузочная проверка моста: переживает ли он серию запросов подряд.

Зачем: в прогоне новых задач мост исчез посреди работы (health 000), и прогон
оборвался на 5 из 10. Нужно понять, падает ли он от нагрузки, или это был
внешний случай.

Проверяем: N запросов /v1/net подряд, после каждого — health.

    python work/stress_bridge.py [N]
"""

from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

TOKEN = pathlib.Path(r"C:\111\env\bridge-token.txt").read_text(encoding="utf-8").strip()


def health() -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8790/health", timeout=5) as r:
            return r.status
    except Exception:  # noqa: BLE001
        return 0


def net_call(line: str) -> tuple[int, str]:
    body = json.dumps({"request": line}).encode()
    request = urllib.request.Request(
        "http://127.0.0.1:8790/v1/net", data=body,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read()).get("error", "ok")
    except urllib.error.HTTPError as error:
        return error.code, f"HTTP {error.code}"
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
