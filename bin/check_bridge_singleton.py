"""Проверка F-BRIDGE-1: второй мост на занятом порту не запускается.

Дефект: ThreadingHTTPServer с allow_reuse_address=1 на Windows позволял двум
процессам слушать один порт. Второй висел вхолостую и копился — в замере
09.11.2026 их набралось 29.

Проверка поднимает настоящий мост на свободном порту и пробует второй.
Отрицательный контроль: до правки второй оставался жив.

    python bin/check_bridge_singleton.py
"""

from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PORT = 8794
KEY_FILE = pathlib.Path(r"C:\111\env\secrets\opencode_go_key.txt")
TOKEN_FILE = pathlib.Path(r"C:\111\env\bridge-token.txt")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start(port: int) -> subprocess.Popen:
    env = {**os.environ}
    if KEY_FILE.exists():
        env["HS_BRIDGE_KEY"] = KEY_FILE.read_text(encoding="utf-8").strip()
    return subprocess.Popen(
        [sys.executable, str(ROOT / "bin" / "bridge.py"), "--port", str(port),
         "--upstream", "https://opencode.ai/inference/go/openai/v1/chat/completions",
         "--token-file", str(TOKEN_FILE)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", env=env,
    )


def health(port: int) -> int:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
            return r.status
    except Exception:  # noqa: BLE001
        return 0


def main() -> int:
    if not TOKEN_FILE.exists() or not KEY_FILE.exists():
        print("нет токена или ключа моста — это UNKNOWN, не PASS")
        return 2

    port = free_port()
    first = start(port)
    try:
        for _ in range(60):
            if health(port) == 200:
                break
            time.sleep(0.2)
        checks = [("первый мост поднялся", health(port) == 200)]

        second = start(port)
        try:
            # Даём второму время либо упасть, либо повиснуть.
            for _ in range(50):
                if second.poll() is not None:
                    break
                time.sleep(0.2)
            code = second.poll()
            checks.append(("второй мост завершился, а не повис", code is not None))
            checks.append(("код отказа — 3 (порт занят)", code == 3))
            err = ""
            if code is not None and second.stderr is not None:
                err = second.stderr.read() or ""
            checks.append(("в отказе сказано про занятый порт", "занят" in err))
        finally:
            if second.poll() is None:
                second.kill()
                second.wait(timeout=10)
    finally:
        first.kill()
        first.wait(timeout=10)

    bad = 0
    for title, ok in checks:
        if not ok:
            bad += 1
        print(f"{'ok  ' if ok else 'FAIL'} {title}")
    print()
    if bad:
        print(f"[FAIL] провалено: {bad} из {len(checks)}")
        return 1
    print(f"[ok] пройдено: {len(checks)} из {len(checks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
