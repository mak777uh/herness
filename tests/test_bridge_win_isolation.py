"""Проверка: /v1/net на Windows не видит окружение моста через PEB.

До изменения Windows-ветка запускала net.py как обычного ребёнка: same-uid
процесс открывал моста через OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ),
читал PEB → RTL_USER_PROCESS_PARAMETERS → Environment и видел HS_BRIDGE_KEY.
Плечо A воспроизводит это напрямую (medium-ребёнок, FOUND=1, FOUND_ANY=1).

После изменения мост запускает net.py через bin/win_lowil.py с токеном низкой
целостности (S-1-16-4096): low-ребёнок не может открыть medium-родителя для
чтения памяти. Плечо B идёт через мост и требует NET_PROBE=1, IL_RID=4096,
FOUND=0, FOUND_ANY=0 и «OpenProcess err=5» — отказ, а не пропуск проверки.

Плечи C/D — fail-closed: без лаунчера и с нерабочим лаунчером мост отвечает 503,
а net.py не исполняется (маркер отсутствует).

Тест заодно проверяет файловую границу того же low-IL: medium-ребёнок A пишет
room/protected.txt (PROTECTED_WRITE=1), low-ребёнок B не пишет (PROTECTED_WRITE=0,
errno 13), но пишет downstream runs/net (STATE_WRITE=1). Это та же граница, что
Linux-барьер NET-FS-WRITE-BARRIER-R1, другим механизмом.

Тест только для Windows: на другой платформе печатает N/A и возвращает 2.
Канарейка и токен синтетические; настоящие ключи и токены не читаются.

    python tests/test_bridge_win_isolation.py
"""

from __future__ import annotations

import ctypes
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
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANARY = "hs-winlow-" + secrets.token_hex(12)
TOKEN = "local-" + secrets.token_hex(8)

FAKE_NET = r'''\
import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

MARKER = Path(r"__MARKER__")
PIDFILE = Path(r"__PIDFILE__")
PROTECTED = Path(r"__PROTECTED__")
STATE = Path(r"__STATE__")
NEEDLE = "HS_BRIDGE_KEY=__CANARY__"

try:
    MARKER.write_text("executed", encoding="utf-8")
except OSError:
    pass

# Файловая граница: medium-файл комнаты/репозитория писать нельзя, downstream
# runs/net (метка Low) — можно. Это проверяет тот же low-IL барьер, что и env.
try:
    PROTECTED.write_text("PWNED", encoding="utf-8")
    print("PROTECTED_WRITE=1")
except OSError as error:
    print("PROTECTED_WRITE=0")
    print("PROTECTED_ERRNO=" + str(error.errno))
try:
    STATE.write_text("state", encoding="utf-8")
    print("STATE_WRITE=1")
except OSError as error:
    print("STATE_WRITE=0")
    print("STATE_ERRNO=" + str(error.errno))

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")


class PROCESS_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Reserved1", ctypes.c_void_p),
        ("PebBaseAddress", ctypes.c_void_p),
        ("Reserved2", ctypes.c_void_p * 2),
        ("UniqueProcessId", ctypes.c_void_p),
        ("InheritedFromUniqueProcessId", ctypes.c_void_p),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
    ]


k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.OpenProcess.restype = wintypes.HANDLE
k32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t)]
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.CloseHandle.restype = wintypes.BOOL
ntdll.NtQueryInformationProcess.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    ctypes.c_void_p]
ntdll.NtQueryInformationProcess.restype = ctypes.c_long
k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32FirstW.restype = wintypes.BOOL
k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.restype = wintypes.BOOL

advapi = ctypes.WinDLL("advapi32", use_last_error=True)
advapi.OpenProcessToken.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
advapi.OpenProcessToken.restype = wintypes.BOOL
advapi.GetTokenInformation.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD)]
advapi.GetTokenInformation.restype = wintypes.BOOL
advapi.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
advapi.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
advapi.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
advapi.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
k32.GetCurrentProcess.restype = wintypes.HANDLE


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", SID_AND_ATTRIBUTES)]


def own_rid():
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(
            k32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        return None
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 25, None, 0, ctypes.byref(size))
        if not size.value:
            return None
        buf = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(
                token, 25, buf, size, ctypes.byref(size)):
            return None
        label = ctypes.cast(buf, ctypes.POINTER(TOKEN_MANDATORY_LABEL)).contents
        count = advapi.GetSidSubAuthorityCount(label.Label.Sid)[0]
        if not count:
            return None
        return int(advapi.GetSidSubAuthority(label.Label.Sid, count - 1)[0])
    finally:
        k32.CloseHandle(token)


def read_mem(handle, address, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    ok = k32.ReadProcessMemory(
        handle, ctypes.c_void_p(address), buf, size, ctypes.byref(got))
    return buf.raw[:got.value] if ok else b""


def read_ptr(handle, address):
    data = read_mem(handle, address, 8)
    return int.from_bytes(data, "little") if len(data) == 8 else 0


def environment(pid):
    handle = k32.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        return None, "OpenProcess err=" + str(ctypes.get_last_error())
    try:
        info = PROCESS_BASIC_INFORMATION()
        status = ntdll.NtQueryInformationProcess(
            handle, 0, ctypes.byref(info), ctypes.sizeof(info), None)
        if status != 0:
            return None, "NtQuery status=" + str(status)
        peb = info.PebBaseAddress or 0
        params = read_ptr(handle, peb + 0x20)
        pointer = read_ptr(handle, params + 0x80)
        if not pointer:
            return None, "env pointer 0"
        chunks = []
        address = pointer
        for _ in range(64):
            data = read_mem(handle, address, 4096)
            if not data:
                break
            chunks.append(data)
            address += len(data)
            if data.endswith(b"\x00\x00"):
                break
        return b"".join(chunks).decode("utf-16-le", "ignore"), ""
    finally:
        k32.CloseHandle(handle)


def all_pids():
    snapshot = k32.CreateToolhelp32Snapshot(2, 0)
    if not snapshot:
        return []
    pids = []
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        if k32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                pids.append(int(entry.th32ProcessID))
                if not k32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
    finally:
        k32.CloseHandle(snapshot)
    return pids


print("NET_PROBE=1")
print("IL_RID=" + str(own_rid() or 0))
target = int(PIDFILE.read_text(encoding="utf-8").strip())
direct, error = environment(target)
print("FOUND=" + ("1" if direct is not None and NEEDLE in direct else "0"))
if error:
    print("ERR=" + error)
found_any = False
for pid in all_pids():
    if pid == os.getpid():
        continue
    text, _ = environment(pid)
    if text is not None and NEEDLE in text:
        found_any = True
        break
print("FOUND_ANY=" + ("1" if found_any else "0"))
'''

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def fingerprint(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def fake_net(tmp: Path) -> Path:
    marker = tmp / "runs" / "net" / "net-executed.txt"
    pidfile = tmp / "runs" / "net" / "bridge-pid.txt"
    protected = tmp / "room" / "protected.txt"
    state = tmp / "runs" / "net" / "write-probe.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    protected.parent.mkdir(parents=True, exist_ok=True)
    protected.write_text("original\n", encoding="utf-8")
    fake = (FAKE_NET
            .replace("__MARKER__", str(marker).replace("\\", "/"))
            .replace("__PIDFILE__", str(pidfile).replace("\\", "/"))
            .replace("__PROTECTED__", str(protected).replace("\\", "/"))
            .replace("__STATE__", str(state).replace("\\", "/"))
            .replace("__CANARY__", CANARY))
    (tmp / "bin" / "net.py").write_text(fake, encoding="utf-8")
    return marker


def start_bridge(tmp: Path, port: int, launcher: str):
    bin_dir = tmp / "bin"
    bin_dir.mkdir(parents=True)
    shutil.copy2(ROOT / "bin" / "bridge.py", bin_dir / "bridge.py")
    if launcher == "ok":
        shutil.copy2(ROOT / "bin" / "win_lowil.py", bin_dir / "win_lowil.py")
    elif launcher == "broken":
        (bin_dir / "win_lowil.py").write_text(
            "import sys\nsys.exit(1)\n", encoding="utf-8")
    marker = fake_net(tmp)
    token_path = tmp / "token.txt"
    token_path.write_text(TOKEN, encoding="utf-8")
    proc_log = open(tmp / "proc.log", "wb")
    env = {**os.environ, "HS_BRIDGE_KEY": CANARY}
    command = [
        sys.executable, str(bin_dir / "bridge.py"),
        "--port", str(port),
        "--upstream", "http://127.0.0.1:9/v1/chat/completions",
        "--token-file", str(token_path),
        "--log", str(tmp / "bridge.log"),
    ]
    proc = subprocess.Popen(
        command, cwd=str(tmp), stdout=proc_log, stderr=subprocess.STDOUT, env=env)
    return proc, proc_log, marker


def wait_health(port: int, proc: subprocess.Popen, proc_log, tmp: Path) -> bool:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=1) as reply:
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
        with urllib.request.urlopen(request, timeout=30) as reply:
            return int(reply.status), reply.read().decode("utf-8", errors="replace")
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


def run_ab() -> None:
    """A: medium-ребёнок видит env моста; B: через мост low-ребёнок не видит."""
    tmp = Path(tempfile.mkdtemp(prefix="herness-winlow-ab-"))
    port = free_port()
    proc = None
    proc_log = None
    try:
        proc, proc_log, marker = start_bridge(tmp, port, "ok")
        if not wait_health(port, proc, proc_log, tmp):
            check(False, "A/B: мост поднялся")
            return
        (tmp / "runs" / "net" / "bridge-pid.txt").write_text(
            str(proc.pid), encoding="utf-8")

        # A: тот же net.py без изоляции, medium. Это положительный контроль канала:
        # если он не видит env, то и B ничего не доказывает.
        direct = subprocess.run(
            [sys.executable, str(tmp / "bin" / "net.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, cwd=str(tmp),
        )
        text_a = (direct.stdout or "") + (direct.stderr or "")
        check("NET_PROBE=1" in text_a, "A: подставной net.py выполнился напрямую")
        check("FOUND=1" in text_a, "A: medium-ребёнок видит HS_BRIDGE_KEY в PEB моста")
        check("FOUND_ANY=1" in text_a, "A: канарейка видна при поиске по процессам")
        check("PROTECTED_WRITE=1" in text_a,
              "A: medium-ребёнок пишет в комнату (канал записи воспроизведён)")
        marker.unlink(missing_ok=True)
        (tmp / "room" / "protected.txt").write_text("original\n", encoding="utf-8")
        (tmp / "runs" / "net" / "write-probe.txt").unlink(missing_ok=True)

        # B: тот же запрос через мост, Windows-ветка обязана применить low IL.
        status, body = post_net(port)
        parsed = json.loads(body) if body.startswith("{") else {}
        output = str(parsed.get("output", ""))
        error = str(parsed.get("error", ""))
        check(status == 200, f"B: ответ /v1/net 200 (получено {status})")
        check("NET_PROBE=1" in output, "B: подставной net.py выполнился (положительный контроль)")
        check("IL_RID=4096" in output, "B: ребёнок действительно в low IL (S-1-16-4096)")
        check("FOUND=0" in output, "B: ребёнок не видит HS_BRIDGE_KEY напрямую")
        check("ERR=OpenProcess err=5" in output,
              "B: отказ именно OpenProcess (access denied), а не пропуск")
        check("FOUND_ANY=0" in output, "B: канарейка не видна при поиске по процессам")
        check("PROTECTED_WRITE=0" in output,
              "B: low-IL ребёнок не пишет в комнату/репозиторий")
        check("STATE_WRITE=1" in output,
              "B: low-IL ребёнок пишет downstream runs/net (метка Low)")
        check((tmp / "room" / "protected.txt").read_text(encoding="utf-8") == "original\n",
              "B: защищённый файл комнаты не изменён")
        check(marker.exists(), "B: маркер исполнения net.py создан")
        check(CANARY not in body, "B: канарейка не попала в ответ /v1/net")
        check(CANARY not in output, "B: канарейка не попала в output")
        check(CANARY not in error, "B: канарейка не попала в error")
        log_path = tmp / "bridge.log"
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        check(CANARY not in log_text, "B: канарейка не попала в bridge.log")
        proc_log.flush()
        proc_text = (tmp / "proc.log").read_text(encoding="utf-8", errors="replace")
        check(CANARY not in proc_text, "B: канарейка не попала в stdout/stderr моста")

        probe = subprocess.run(
            [sys.executable, str(tmp / "bin" / "win_lowil.py"), "--probe"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, cwd=str(tmp),
        )
        check(probe.returncode == 0 and "LOWIL_PROBE=1" in (probe.stdout or ""),
              "E: проба лаунчера подтверждает low IL и запись состояния")
    finally:
        if proc is not None:
            stop(proc, proc_log)
        shutil.rmtree(tmp, ignore_errors=True)


def run_arm(name: str, launcher: str, expected: str) -> None:
    tmp = Path(tempfile.mkdtemp(prefix=f"herness-winlow-{name}-"))
    port = free_port()
    proc = None
    proc_log = None
    try:
        proc, proc_log, marker = start_bridge(tmp, port, launcher)
        if not wait_health(port, proc, proc_log, tmp):
            check(False, f"{name}: мост поднялся")
            return
        (tmp / "runs" / "net" / "bridge-pid.txt").write_text(
            str(proc.pid), encoding="utf-8")
        status, body = post_net(port)
        check(status == 503, f"{name}: ответ 503 (получено {status})")
        check(expected in body, f"{name}: причина отказа названа")
        check(not marker.exists(), f"{name}: net.py не исполнен (fail-closed)")
        check(CANARY not in body, f"{name}: канарейка не попала в отказ")
    finally:
        if proc is not None:
            stop(proc, proc_log)
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    if not sys.platform.startswith("win"):
        print("N/A: тест измеряет Windows-механизм; запускать на Windows")
        return 2
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        print("N/A: PEB-смещения проверены только для 64-битного Python")
        return 2
    print(f"канарейка: {fingerprint(CANARY)} (значение не печатается)")
    run_ab()
    run_arm("C", "missing", "не найден")
    run_arm("D", "broken", "не работает")

    failed = 0
    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
        failed += 0 if flag else 1
    print(f"провалов: {failed}")
    if failed:
        print("ВЕРДИКТ: FAIL — Windows-изоляция /v1/net не сработала или не различает отказ")
    else:
        print("ВЕРДИКТ: PASS — low-IL ребёнок не видит env моста и не пишет в комнату; без рабочего лаунчера 503")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
