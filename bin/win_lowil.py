"""win_lowil — запуск `/v1/net` в токене низкой целостности на Windows.

Зачем. PID-namespace закрыл чтение `/proc/<ppid>/environ` на Linux (C-0328/C-0329),
но у Windows нет `/proc`. Тот же uid читает стартовое окружение родителя через PEB:
`OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ)`, `NtQueryInformationProcess`,
`RTL_USER_PROCESS_PARAMETERS.Environment`, `ReadProcessMemory`. Мандатный контроль
целостности не даёт low-процессу открыть medium-родителя для чтения памяти, поэтому
`/v1/net` запускается с токеном low IL. Это один канал (окружение/память процесса),
а не «мост безопасен».

Режимы (внутренние, вызывает мост и тест):
    python bin/win_lowil.py --probe
    python bin/win_lowil.py -- <команда...>

`--probe` проверяет три вещи до первого запроса: токен создаётся, ребёнок действительно
получает low IL (S-1-16-4096), и `runs/net` доступен ему на запись (иначе net.py упадёт
на журнале). Если хоть одна не выполняется — отказ, а не тихий запуск без изоляции.

Метка `runs/net` опускается до Low: net.py пишет туда session.json и журнал; low-процесс
не может писать в medium-файлы. Это downstream-состояние, не секреты и не первая комната.
Файловая система, сеть, token-файл, командная строка процесса и K9 этим не закрываются.
"""

from __future__ import annotations

import argparse
import ctypes
import msvcrt
import os
import shutil
import subprocess
import sys
import threading
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runs" / "net"
LOW_IL_SID = "S-1-16-4096"
LOW_IL_RID = 4096

TOKEN_ASSIGN_PRIMARY = 0x0001
TOKEN_DUPLICATE = 0x0002
TOKEN_QUERY = 0x0008
TOKEN_ADJUST_DEFAULT = 0x0080
DISABLE_MAX_PRIVILEGE = 0x0001
SE_GROUP_INTEGRITY = 0x00000020
TOKEN_INTEGRITY_LEVEL = 25
CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
STARTF_USESTDHANDLES = 0x00000100
HANDLE_FLAG_INHERIT = 0x00000001
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
TH32CS_SNAPPROCESS = 0x00000002
INFINITE = 0xFFFFFFFF

if sys.platform.startswith("win"):
    _advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:  # позволяет импортировать модуль на Linux без падения
    _advapi = None
    _k32 = None


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", SID_AND_ATTRIBUTES)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD),
    ]


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


class LARGE_INTEGER(ctypes.Structure):
    _fields_ = [("QuadPart", ctypes.c_longlong)]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", LARGE_INTEGER),
        ("PerJobUserTimeLimit", LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
    ]


def _bind() -> None:
    """Прототипы WinAPI: без них ctypes на x64 обрезает HANDLE до 32 бит."""
    if _advapi is None or _k32 is None:
        return
    _advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    _advapi.OpenProcessToken.restype = wintypes.BOOL
    _advapi.CreateRestrictedToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
        ctypes.POINTER(wintypes.HANDLE)]
    _advapi.CreateRestrictedToken.restype = wintypes.BOOL
    _advapi.SetTokenInformation.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    _advapi.SetTokenInformation.restype = wintypes.BOOL
    _advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD)]
    _advapi.GetTokenInformation.restype = wintypes.BOOL
    _advapi.ConvertStringSidToSidW.argtypes = [
        wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    _advapi.ConvertStringSidToSidW.restype = wintypes.BOOL
    _advapi.GetLengthSid.argtypes = [ctypes.c_void_p]
    _advapi.GetLengthSid.restype = wintypes.DWORD
    _advapi.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
    _advapi.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    _advapi.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    _advapi.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
    _advapi.CreateProcessAsUserW.argtypes = [
        wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p,
        wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOW),
        ctypes.POINTER(PROCESS_INFORMATION)]
    _advapi.CreateProcessAsUserW.restype = wintypes.BOOL
    _k32.GetCurrentProcess.restype = wintypes.HANDLE
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL
    _k32.CreatePipe.argtypes = [
        ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(SECURITY_ATTRIBUTES), wintypes.DWORD]
    _k32.CreatePipe.restype = wintypes.BOOL
    _k32.SetHandleInformation.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
    _k32.SetHandleInformation.restype = wintypes.BOOL
    _k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(SECURITY_ATTRIBUTES), wintypes.DWORD, wintypes.DWORD,
        wintypes.HANDLE]
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.ResumeThread.argtypes = [wintypes.HANDLE]
    _k32.ResumeThread.restype = wintypes.DWORD
    _k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.WaitForSingleObject.restype = wintypes.DWORD
    _k32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _k32.GetExitCodeProcess.restype = wintypes.BOOL
    _k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.TerminateProcess.restype = wintypes.BOOL
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _k32.Process32FirstW.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _k32.Process32FirstW.restype = wintypes.BOOL
    _k32.Process32NextW.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _k32.Process32NextW.restype = wintypes.BOOL
    _k32.LocalFree.argtypes = [ctypes.c_void_p]
    _k32.LocalFree.restype = ctypes.c_void_p


_bind()


def refuse(message: str) -> int:
    """Отказ изоляции: отдельная метка, чтобы мост ответил 503, а не 200."""
    print("LOWIL_REFUSED=1", file=sys.stderr)
    print("win_lowil: " + message, file=sys.stderr)
    return 1


def prepare_state(state: Path = STATE) -> str:
    """Создать runs/net и опустить метку до Low: иначе low-процесс не запишет журнал."""
    try:
        state.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return f"каталог состояния: {type(error).__name__}"
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    trusted = Path(system_root) / "System32" / "icacls.exe"
    icacls = str(trusted) if trusted.is_file() else (shutil.which("icacls") or "")
    if not icacls:
        return "icacls не найден"
    try:
        label = subprocess.run(
            [icacls, str(state), "/setintegritylevel", "(OI)(CI)L", "/T"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"метка состояния: {type(error).__name__}"
    if label.returncode != 0:
        tail = (label.stderr or label.stdout or "").strip().splitlines()[-1:]
        return f"метка состояния: icacls rc={label.returncode}" + (
            f" ({tail[0][:120]})" if tail else "")
    return ""


def own_integrity_rid() -> int | None:
    """RID последнего подключённого SID целостности: 4096 = Low, 8192 = Medium."""
    token = wintypes.HANDLE()
    if not _advapi.OpenProcessToken(
            _k32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        return None
    try:
        size = wintypes.DWORD()
        _advapi.GetTokenInformation(
            token, TOKEN_INTEGRITY_LEVEL, None, 0, ctypes.byref(size))
        if not size.value:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if not _advapi.GetTokenInformation(
                token, TOKEN_INTEGRITY_LEVEL, buffer, size, ctypes.byref(size)):
            return None
        label = ctypes.cast(buffer, ctypes.POINTER(TOKEN_MANDATORY_LABEL)).contents
        count = _advapi.GetSidSubAuthorityCount(label.Label.Sid)[0]
        if not count:
            return None
        return int(_advapi.GetSidSubAuthority(label.Label.Sid, count - 1)[0])
    finally:
        _k32.CloseHandle(token)


def _restricted_low_token() -> tuple[wintypes.HANDLE | None, str]:
    """Ограниченный токен текущего процесса с меткой Low (S-1-16-4096)."""
    current = wintypes.HANDLE()
    if not _advapi.OpenProcessToken(
            _k32.GetCurrentProcess(),
            TOKEN_DUPLICATE | TOKEN_QUERY | TOKEN_ASSIGN_PRIMARY | TOKEN_ADJUST_DEFAULT,
            ctypes.byref(current)):
        return None, f"OpenProcessToken err={ctypes.get_last_error()}"
    restricted = wintypes.HANDLE()
    ok = _advapi.CreateRestrictedToken(
        current, DISABLE_MAX_PRIVILEGE, 0, None, 0, None, 0, None,
        ctypes.byref(restricted))
    error = ctypes.get_last_error()
    _k32.CloseHandle(current)
    if not ok:
        return None, f"CreateRestrictedToken err={error}"
    sid = ctypes.c_void_p()
    if not _advapi.ConvertStringSidToSidW(LOW_IL_SID, ctypes.byref(sid)):
        _k32.CloseHandle(restricted)
        return None, f"ConvertStringSidToSidW err={ctypes.get_last_error()}"
    try:
        label = TOKEN_MANDATORY_LABEL()
        label.Label.Sid = sid
        label.Label.Attributes = SE_GROUP_INTEGRITY
        size = ctypes.sizeof(label) + _advapi.GetLengthSid(sid)
        if not _advapi.SetTokenInformation(
                restricted, TOKEN_INTEGRITY_LEVEL, ctypes.byref(label), size):
            error = ctypes.get_last_error()
            _k32.CloseHandle(restricted)
            return None, f"SetTokenInformation err={error}"
    finally:
        _k32.LocalFree(sid)
    return restricted, ""


def _env_block(environ: dict[str, str] | None = None) -> ctypes.Array:
    source = os.environ if environ is None else environ
    text = "".join(f"{key}={value}\0" for key, value in source.items()) + "\0"
    return ctypes.create_unicode_buffer(text)


def _reader(handle: wintypes.HANDLE, sink: list[bytes]) -> None:
    """Читает pipe в потоке: иначе ребёнок встанет на заполненном буфере."""
    try:
        fd = msvcrt.open_osfhandle(handle.value, os.O_RDONLY | os.O_BINARY)
    except OSError:
        _k32.CloseHandle(handle)
        return
    with os.fdopen(fd, "rb", closefd=True) as stream:
        sink.append(stream.read())


def run_low(command: list[str]) -> tuple[bytes, bytes, int | None, str]:
    """Запустить команду низкой целостности. Возвращает (stdout, stderr, код, ошибка)."""
    if _advapi is None or _k32 is None:
        return b"", b"", None, "не Windows"
    token, error = _restricted_low_token()
    if token is None:
        return b"", b"", None, error
    job = wintypes.HANDLE()
    out_read = wintypes.HANDLE()
    out_write = wintypes.HANDLE()
    err_read = wintypes.HANDLE()
    err_write = wintypes.HANDLE()
    nul = wintypes.HANDLE()
    process = wintypes.HANDLE()
    thread = wintypes.HANDLE()
    try:
        security = SECURITY_ATTRIBUTES()
        security.nLength = ctypes.sizeof(security)
        security.bInheritHandle = True
        if not _k32.CreatePipe(ctypes.byref(out_read), ctypes.byref(out_write),
                               ctypes.byref(security), 0):
            return b"", b"", None, f"CreatePipe(out) err={ctypes.get_last_error()}"
        if not _k32.CreatePipe(ctypes.byref(err_read), ctypes.byref(err_write),
                               ctypes.byref(security), 0):
            return b"", b"", None, f"CreatePipe(err) err={ctypes.get_last_error()}"
        _k32.SetHandleInformation(out_read, HANDLE_FLAG_INHERIT, 0)
        _k32.SetHandleInformation(err_read, HANDLE_FLAG_INHERIT, 0)
        nul = wintypes.HANDLE(_k32.CreateFileW(
            "NUL", 0x80000000, 0x00000003, ctypes.byref(security), 3, 0, None))
        if not nul or nul.value == ctypes.c_void_p(-1).value:
            return b"", b"", None, f"CreateFile(NUL) err={ctypes.get_last_error()}"

        job = wintypes.HANDLE(_k32.CreateJobObjectW(None, None))
        if not job:
            return b"", b"", None, f"CreateJobObject err={ctypes.get_last_error()}"
        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _k32.SetInformationJobObject(
                job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits), ctypes.sizeof(limits)):
            return b"", b"", None, f"SetInformationJobObject err={ctypes.get_last_error()}"

        startup = STARTUPINFOW()
        startup.cb = ctypes.sizeof(startup)
        startup.dwFlags = STARTF_USESTDHANDLES
        startup.hStdInput = nul
        startup.hStdOutput = out_write
        startup.hStdError = err_write
        info = PROCESS_INFORMATION()
        command_line = ctypes.create_unicode_buffer(
            subprocess.list2cmdline([str(part) for part in command]))
        environment = _env_block()
        if not _advapi.CreateProcessAsUserW(
                token, None, command_line, None, None, True,
                CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT,
                environment, None, ctypes.byref(startup), ctypes.byref(info)):
            return b"", b"", None, f"CreateProcessAsUser err={ctypes.get_last_error()}"
        process = wintypes.HANDLE(info.hProcess)
        thread = wintypes.HANDLE(info.hThread)
        _k32.CloseHandle(out_write)
        out_write = wintypes.HANDLE()
        _k32.CloseHandle(err_write)
        err_write = wintypes.HANDLE()
        if not _k32.AssignProcessToJobObject(job, process):
            error = f"AssignProcessToJobObject err={ctypes.get_last_error()}"
            _k32.TerminateProcess(process, 1)
            return b"", b"", None, error
        if _k32.ResumeThread(thread) == 0xFFFFFFFF:
            error = f"ResumeThread err={ctypes.get_last_error()}"
            _k32.TerminateProcess(process, 1)
            return b"", b"", None, error

        out_chunks: list[bytes] = []
        err_chunks: list[bytes] = []
        readers = [
            threading.Thread(target=_reader, args=(out_read, out_chunks), daemon=True),
            threading.Thread(target=_reader, args=(err_read, err_chunks), daemon=True),
        ]
        for reader in readers:
            reader.start()
        _k32.WaitForSingleObject(process, INFINITE)
        code = wintypes.DWORD()
        _k32.GetExitCodeProcess(process, ctypes.byref(code))
        _k32.CloseHandle(job)
        job = wintypes.HANDLE()
        for reader in readers:
            reader.join(timeout=10)
        return b"".join(out_chunks), b"".join(err_chunks), int(code.value), ""
    finally:
        for handle in (job, out_read, out_write, err_read, err_write, nul, process, thread):
            _close(handle)
        _close(token)


def _close(handle) -> None:
    """Закрыть HANDLE, который ctypes может вернуть как int или как c_void_p."""
    if not handle:
        return
    value = handle if isinstance(handle, int) else handle.value
    if value:
        _k32.CloseHandle(wintypes.HANDLE(value))


def write_stream(stream, data: bytes) -> None:
    if not data:
        return
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(data)
        buffer.flush()
    else:
        stream.write(data.decode("utf-8", errors="replace"))
        stream.flush()


def probe_child(state: Path) -> int:
    """Ребёнок пробы: измеряет свой реальный уровень целостности и запись состояния."""
    rid = own_integrity_rid()
    print("PROBE_RAN=1")
    print(f"IL_RID={rid if rid is not None else 0}")
    if rid == LOW_IL_RID:
        print("LOWIL_CHILD=1")
    target = state / f".lowil-probe-{os.getpid()}.txt"
    try:
        target.write_text("ok\n", encoding="utf-8")
        print("STATE_WRITE=1")
        target.unlink(missing_ok=True)
    except OSError as error:
        print("STATE_WRITE=0")
        print("STATE_ERR=" + type(error).__name__)
    return 0 if rid == LOW_IL_RID else 1


def probe() -> int:
    error = prepare_state()
    if error:
        return refuse(error)
    command = [sys.executable, str(Path(__file__).resolve()), "--probe-child", str(STATE)]
    out, err, code, error = run_low(command)
    text = out.decode("utf-8", errors="replace")
    if error:
        return refuse(f"проба: {error}")
    if code != 0 or "LOWIL_CHILD=1" not in text or "STATE_WRITE=1" not in text:
        detail = " ".join((text + err.decode("utf-8", errors="replace")).split())[-300:]
        return refuse(f"проба не подтвердила low IL и запись состояния: rc={code} {detail}")
    print("LOWIL_PROBE=1")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="low-integrity запуск /v1/net")
    parser.add_argument("--probe", action="store_true", help="внутреннее: проба изоляции")
    parser.add_argument("--probe-child", metavar="STATE", help="внутреннее: ребёнок пробы")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if not sys.platform.startswith("win"):
        print("N/A: win_lowil применим только к Windows", file=sys.stderr)
        return 2
    if args.probe_child:
        return probe_child(Path(args.probe_child))
    if args.probe:
        return probe()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        return refuse("нет команды: нужно -- <команда...>")
    error = prepare_state()
    if error:
        return refuse(error)
    out, err, code, error = run_low(command)
    if error:
        return refuse(f"запуск: {error}")
    write_stream(sys.stdout, out)
    write_stream(sys.stderr, err)
    return int(code or 0)


if __name__ == "__main__":
    sys.exit(main())
