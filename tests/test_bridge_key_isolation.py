"""Проверка: внешний помощник /v1/net не получает ключ провайдера из окружения моста.

Мост — adjacent bridge: ключ провайдера живёт на хосте, комната получает только
операцию. Но /v1/net запускает bin/net.py как дочерний процесс. Если запускать его
без явного env=, он наследует os.environ, включая HS_BRIDGE_KEY. Тогда внешний
слой (код, разбирающий чужой HTML) видит ключ первой комнаты.

Тест подкладывает в копию дерева подставной net.py, который печатает значение
HS_BRIDGE_KEY. Канарейка синтетическая; настоящие ключи и токены не читаются.

На Linux мост запускает net.py только под рабочим unshare (C-0328/C-0329).
Здесь предмет — наследование окружения, а не namespace, поэтому на Linux в PATH
подставляется shim `unshare`, который лишь исполняет команду: иначе на раннере
с запрещёнными user namespace тест мерил бы не тот канал. Namespace проверяет
tests/test_bridge_net_namespace.py.

    python tests/test_bridge_key_isolation.py
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANARY = "hs-canary-" + secrets.token_hex(12)
TOKEN = "local-" + secrets.token_hex(8)

FAKE_NET = '''\
import os
import sys

print("NET_PROBE")
print("HS_BRIDGE_KEY=" + os.environ.get("HS_BRIDGE_KEY", "ABSENT"))
print("ARGV=" + " ".join(sys.argv[1:]))
'''

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((flag, message))


def fingerprint(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def unshare_shim(tmp: Path) -> Path:
    """Заглушка launcher'а: исполняет команду без namespace (только для env-теста)."""
    shim_dir = tmp / "shim-bin"
    shim_dir.mkdir()
    shim = shim_dir / "unshare"
    shim.write_text('#!/bin/sh\nshift 4\nexec "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    return shim_dir


def start_bridge(tmp: Path, port: int) -> tuple[subprocess.Popen, object]:
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    shutil.copy2(ROOT / "bin" / "bridge.py", bin_dir / "bridge.py")
    (bin_dir / "net.py").write_text(FAKE_NET, encoding="utf-8")
    token_path = tmp / "token.txt"
    token_path.write_text(TOKEN, encoding="utf-8")
    proc_log = open(tmp / "proc.log", "wb")
    env = {**os.environ, "HS_BRIDGE_KEY": CANARY}
    if sys.platform.startswith("linux"):
        env["PATH"] = str(unshare_shim(tmp)) + os.pathsep + env.get("PATH", "")
    command = [
        sys.executable,
        str(bin_dir / "bridge.py"),
        "--port", str(port),
        "--upstream", "http://127.0.0.1:9/v1/chat/completions",
        "--token-file", str(token_path),
        "--log", str(tmp / "bridge.log"),
    ]
    proc = subprocess.Popen(
        command,
        cwd=str(tmp),
        stdout=proc_log,
        stderr=subprocess.STDOUT,
        env=env,
    )
    return proc, proc_log


def wait_health(port: int, proc: subprocess.Popen, proc_log: object, tmp: Path) -> bool:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as reply:
                if reply.status == 200:
                    return True
        except Exception:  # noqa: BLE001 — мост ещё не поднялся
            time.sleep(0.1)
    proc_log.flush()
    text = (tmp / "proc.log").read_text(encoding="utf-8", errors="replace")
    print("мост не поднялся; stdout/stderr:")
    print(text[-2000:])
    return False


def post_net(port: int) -> str:
    payload = json.dumps({"request": "probe"}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/net",
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as reply:
        return reply.read().decode("utf-8")


def stop(proc: subprocess.Popen, proc_log: object) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    try:
        proc_log.close()
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    print(f"канарейка: {fingerprint(CANARY)} (значение не печатается)")
    tmp = Path(tempfile.mkdtemp(prefix="herness-bridge-iso-"))
    port = free_port()
    proc = None
    proc_log = None
    try:
        proc, proc_log = start_bridge(tmp, port)
        if not wait_health(port, proc, proc_log, tmp):
            return 2

        body = post_net(port)
        parsed = json.loads(body)
        output = str(parsed.get("output", ""))
        error = str(parsed.get("error", ""))
        check("NET_PROBE" in output, "подставной net.py выполнился (положительный контроль)")
        check(CANARY not in body, "канарейка не попала в ответ /v1/net")
        check(CANARY not in output, "канарейка не попала в output дочернего процесса")
        check(CANARY not in error, "канарейка не попала в error ответа")
        check("HS_BRIDGE_KEY=ABSENT" in output,
              "дочерний процесс видит HS_BRIDGE_KEY как отсутствующий")

        log_path = tmp / "bridge.log"
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        check(CANARY not in log_text, "канарейка не попала в bridge.log")

        proc_log.flush()
        proc_text = (tmp / "proc.log").read_text(encoding="utf-8", errors="replace")
        check(CANARY not in proc_text, "канарейка не попала в stdout/stderr моста")

        # Диагностика без значения: сколько раз и в каком канале.
        channels = {
            "response": body.count(CANARY),
            "output": output.count(CANARY),
            "bridge.log": log_text.count(CANARY),
            "proc.log": proc_text.count(CANARY),
        }
        print(f"вхождения канарейки: {channels}")
    finally:
        if proc is not None:
            stop(proc, proc_log)
        shutil.rmtree(tmp, ignore_errors=True)

    failed = 0
    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
        failed += 0 if flag else 1
    print(f"провалов: {failed}")
    if failed:
        print("ВЕРДИКТ: FAIL — внешний помощник видит ключ моста")
    else:
        print("ВЕРДИКТ: PASS — дочерний процесс /v1/net не получает ключ из окружения")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
