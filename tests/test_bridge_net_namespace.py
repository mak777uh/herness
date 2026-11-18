"""Проверка: /v1/net на Linux запускает помощника в PID-namespace и не откатывается молча.

Плечо B: мост запущен обычным PATH; подставной net.py ищет `HS_BRIDGE_KEY=<канарейка>`
по всему `/proc`. До изменения он видит ключ (FOUND_ANY=1), после — нет (FOUND_ANY=0),
при этом NET_PROBE=1 подтверждает, что помощник действительно выполнился.

Плечо C: PATH без unshare; мост обязан ответить 503 и не исполнять net.py (fail-closed),
а не запускать его без изоляции. Маркер исполнения — файл, который пишет net.py.

Плечо D: unshare есть, но не работает (подставной бинарник с exit 1); мост обязан
ответить 503 и не исполнять net.py — наличие файла не считается рабочей изоляцией.

Канарейка и токен синтетические; настоящие ключи не читаются.

    python tests/test_bridge_net_namespace.py   # Windows: делегирует в WSL Ubuntu
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
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANARY = "hs-netns-" + secrets.token_hex(12)
TOKEN = "local-" + secrets.token_hex(8)

FAKE_NET = '''\
import os
from pathlib import Path

MARKER = Path(r"__MARKER__")
MARKER.write_text("executed", encoding="utf-8")
needle = b"HS_BRIDGE_KEY=__CANARY__"
found = False
for entry in Path("/proc").iterdir():
    if not entry.name.isdigit():
        continue
    try:
        if needle in (entry / "environ").read_bytes():
            found = True
            break
    except OSError:
        continue
print("NET_PROBE=1")
print("FOUND_ANY=" + ("1" if found else "0"))
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


def start_bridge(tmp: Path, port: int, path_env: str | None = None):
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    shutil.copy2(ROOT / "bin" / "bridge.py", bin_dir / "bridge.py")
    marker = tmp / "net-executed.txt"
    fake = FAKE_NET.replace("__MARKER__", str(marker)).replace("__CANARY__", CANARY)
    (bin_dir / "net.py").write_text(fake, encoding="utf-8")
    token_path = tmp / "token.txt"
    token_path.write_text(TOKEN, encoding="utf-8")
    proc_log = open(tmp / "proc.log", "wb")
    env = {**os.environ, "HS_BRIDGE_KEY": CANARY}
    if path_env is not None:
        env["PATH"] = path_env
    command = [
        sys.executable,
        str(bin_dir / "bridge.py"),
        "--port", str(port),
        "--upstream", "http://127.0.0.1:9/v1/chat/completions",
        "--token-file", str(token_path),
        "--log", str(tmp / "bridge.log"),
    ]
    proc = subprocess.Popen(
        command, cwd=str(tmp), stdout=proc_log, stderr=subprocess.STDOUT, env=env,
    )
    return proc, proc_log, marker


def wait_health(port: int, proc: subprocess.Popen, proc_log, tmp: Path) -> bool:
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


def post_net(port: int) -> tuple[int, str]:
    payload = json.dumps({"request": "probe"}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/net",
        data=payload,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as reply:
            return int(reply.status), reply.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return int(error.code), (error.read() or b"").decode("utf-8", errors="replace")


def stop(proc: subprocess.Popen, proc_log) -> None:
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


def run_arm_b() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="herness-netns-b-"))
    port = free_port()
    proc = None
    proc_log = None
    try:
        proc, proc_log, marker = start_bridge(tmp, port)
        if not wait_health(port, proc, proc_log, tmp):
            check(False, "B: мост поднялся")
            return
        status, body = post_net(port)
        check(status == 200, f"B: ответ /v1/net 200 (получено {status})")
        try:
            output = str(json.loads(body).get("output", ""))
        except ValueError:
            output = ""
        print("B: вывод подставного net.py:")
        print(output.strip() or "(пусто)")
        check("NET_PROBE=1" in output, "B: подставной net.py выполнился (положительный контроль)")
        check("FOUND_ANY=0" in output,
              "B: ребёнок не видит HS_BRIDGE_KEY в /proc (PID-namespace)")
        check("FOUND_ANY=1" not in output,
              "B: в выводе нет свидетельства утечки через /proc")
        check(marker.exists(), "B: маркер исполнения net.py создан")
        check(CANARY not in body, "B: канарейка не попала в ответ /v1/net")
        log_path = tmp / "bridge.log"
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        check(CANARY not in log_text, "B: канарейка не попала в bridge.log")
        proc_log.flush()
        proc_text = (tmp / "proc.log").read_text(encoding="utf-8", errors="replace")
        check(CANARY not in proc_text, "B: канарейка не попала в stdout/stderr моста")
    finally:
        if proc is not None:
            stop(proc, proc_log)
        shutil.rmtree(tmp, ignore_errors=True)


def run_arm_c() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="herness-netns-c-"))
    port = free_port()
    empty_path = tmp / "empty-path"
    empty_path.mkdir()
    proc = None
    proc_log = None
    try:
        proc, proc_log, marker = start_bridge(tmp, port, path_env=str(empty_path))
        if not wait_health(port, proc, proc_log, tmp):
            check(False, "C: мост поднялся без unshare")
            return
        status, body = post_net(port)
        check(status == 503, f"C: без unshare мост отказывает 503 (получено {status})")
        check("не найден" in body, "C: причина отказа — unshare не найден, а не другое")
        check(not marker.exists(), "C: net.py не исполнен без unshare (fail-closed)")
        check(CANARY not in body, "C: канарейка не попала в отказ")
    finally:
        if proc is not None:
            stop(proc, proc_log)
        shutil.rmtree(tmp, ignore_errors=True)


def run_arm_d() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="herness-netns-d-"))
    port = free_port()
    fake_bin = tmp / "fake-bin"
    fake_bin.mkdir()
    broken = fake_bin / "unshare"
    broken.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    broken.chmod(0o755)
    proc = None
    proc_log = None
    try:
        proc, proc_log, marker = start_bridge(tmp, port, path_env=str(fake_bin))
        if not wait_health(port, proc, proc_log, tmp):
            check(False, "D: мост поднялся с нерабочим unshare")
            return
        status, body = post_net(port)
        check(status == 503, f"D: нерабочий unshare отвергнут 503 (получено {status})")
        check("не работает" in body, "D: причина отказа — unshare не работает, а не не найден")
        check(not marker.exists(), "D: net.py не исполнен при нерабочем unshare")
        check(CANARY not in body, "D: канарейка не попала в отказ")
    finally:
        if proc is not None:
            stop(proc, proc_log)
        shutil.rmtree(tmp, ignore_errors=True)


def run_tests() -> int:
    print(f"канарейка: {fingerprint(CANARY)} (значение не печатается)")
    run_arm_b()
    run_arm_c()
    run_arm_d()

    failed = 0
    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
        failed += 0 if flag else 1
    print(f"провалов: {failed}")
    if failed:
        print("ВЕРДИКТ: FAIL — /v1/net не изолирован или fail-closed не сработал")
        return 1
    print("ВЕРДИКТ: PASS — /v1/net не видит ключ через /proc; без рабочего unshare отказ")
    return 0


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = str(resolved).replace("\\", "/")[len(resolved.drive):]
    return f"/mnt/{drive}{rest}"


def delegate_wsl() -> int:
    if shutil.which("wsl") is None:
        print("N/A: WSL не найден, срез не выполнен")
        return 2
    script = wsl_path(Path(__file__).resolve())
    result = subprocess.run(
        ["wsl", "-d", "Ubuntu", "--exec", "python3", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240,
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


def main() -> int:
    if not sys.platform.startswith("linux"):
        return delegate_wsl()
    return run_tests()


if __name__ == "__main__":
    raise SystemExit(main())
