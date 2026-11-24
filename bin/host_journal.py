"""host_journal — fail-closed журнал, который ведёт ХОСТ, а не комната.

Граница W07A: run ID не становится путём, файловый объект проверяется по открытому
descriptor, append координируется per-run lock, полный canonical envelope входит в hash,
а запись не получает ACK до fsync. Legacy v1 не мигрируется и не подтверждается.

Формат v2 (одна canonical compact JSONL строка):

    {"at":"…Z","event":"…","prev":"00…00","run":"opaque-run","seq":1,
     "sha256":"…","v":2}

`sha256 = SHA256("HOST-JOURNAL-RECORD-V2\\0" + canonical(envelope без sha256))`.
Хеш покрывает v/seq/at/run/event/prev. `prev` первой записи — 64 нуля.
Тот же `<run>.lock` хранит append-only SHA-256 каждой записи; journal и anchor
сверяются по индексу под per-run lock, а anchor fsync выполняется до ACK.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

ZERO = "0" * 64
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "runs" / "host-journal"
VERSION = 2
HASH_DOMAIN = b"HOST-JOURNAL-RECORD-V2\0"
RUN_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")
MAX_RUN_ID_BYTES = 128
MAX_EVENT_BYTES = 64 * 1024
MAX_JOURNAL_BYTES = 64 * 1024 * 1024
MAX_TIP_BYTES = 64 * 1024 * 1024
TIP_LINE_BYTES = 65
MAX_RECORD_BYTES = 6 * MAX_EVENT_BYTES + 4096
RECORD_FIELDS = frozenset(("v", "seq", "prev", "sha256", "at", "event", "run"))
FILE_ATTRIBUTE_REPARSE_POINT = 0x400

_thread_guard = threading.Lock()
_thread_locks: dict[str, threading.Lock] = {}


class JournalError(OSError):
    """Отказ storage boundary; содержимое события в сообщение не попадает."""


def _validate_run(run: str) -> str:
    if not isinstance(run, str) or not RUN_RE.fullmatch(run):
        raise JournalError("run ID должен быть opaque: 1..128 строчных латинских цифр/дефисов")
    if len(run.encode("ascii")) > MAX_RUN_ID_BYTES:
        raise JournalError("run ID длиннее 128 байт")
    return run


def _validate_event(event: str) -> str:
    if not isinstance(event, str) or not event:
        raise JournalError("event должен быть непустой строкой")
    try:
        size = len(event.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise JournalError("event не является корректным UTF-8") from exc
    if size > MAX_EVENT_BYTES:
        raise JournalError(f"event больше {MAX_EVENT_BYTES} байт")
    return event


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def record_hash(entry: dict) -> str:
    """Hash полного envelope; единственное исключённое поле — сам sha256."""
    body = {key: value for key, value in entry.items() if key != "sha256"}
    return hashlib.sha256(HASH_DOMAIN + _canonical(body)).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _is_reparse(file_stat: os.stat_result) -> bool:
    return bool(getattr(file_stat, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def _prepare_directory(directory: Path, *, create: bool) -> tuple[Path, list[Path]]:
    path = Path(directory)
    created: list[Path] = []
    try:
        if create:
            cursor = Path(os.path.abspath(path))
            while not cursor.exists():
                created.append(cursor)
                parent = cursor.parent
                if parent == cursor:
                    break
                cursor = parent
            path.mkdir(parents=True, exist_ok=True)
            created = [item.resolve(strict=True) for item in created]
        resolved = path.resolve(strict=True)
        info = resolved.stat()
        original_info = path.lstat()
    except (OSError, RuntimeError) as exc:
        raise JournalError(f"journal directory недоступен: {type(exc).__name__}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise JournalError("journal directory не является каталогом")
    if stat.S_ISLNK(original_info.st_mode) or _is_reparse(original_info):
        raise JournalError("journal directory является symlink/reparse point")
    return resolved, created


def _identity(file_stat: os.stat_result) -> tuple[int, int]:
    return int(file_stat.st_dev), int(file_stat.st_ino)


def _validate_descriptor(fd: int, path: Path) -> None:
    try:
        info = os.fstat(fd)
    except OSError as exc:
        raise JournalError(f"descriptor недоступен: {type(exc).__name__}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise JournalError("journal object не является регулярным файлом")
    if info.st_nlink != 1:
        raise JournalError("journal object имеет hardlink: nlink != 1")
    if _is_reparse(info):
        raise JournalError("journal object является reparse point")
    try:
        path_info = path.lstat()
    except OSError as exc:
        raise JournalError("journal path исчез: дескриптор не подтверждён путём") from exc
    if stat.S_ISLNK(path_info.st_mode) or _is_reparse(path_info):
        raise JournalError("journal path заменён на symlink/reparse point")
    if _identity(path_info) != _identity(info):
        raise JournalError("journal path заменён: descriptor identity не совпадает")


if os.name == "nt":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _OPEN_EXISTING = 3
    _CREATE_NEW = 1
    _FILE_NAME_NORMALIZED = 0
    _VOLUME_NAME_DOS = 0
    _LOCKFILE_EXCLUSIVE_LOCK = 0x00000002

    class _Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_ulonglong),
            ("InternalHigh", ctypes.c_ulonglong),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ByHandleFileInformation)]
    _kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    _kernel32.GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
    ]
    _kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    _kernel32.LockFileEx.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, ctypes.POINTER(_Overlapped),
    ]
    _kernel32.LockFileEx.restype = wintypes.BOOL
    _kernel32.UnlockFileEx.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(_Overlapped),
    ]
    _kernel32.UnlockFileEx.restype = wintypes.BOOL

    def _windows_error(what: str) -> JournalError:
        code = ctypes.get_last_error()
        return JournalError(f"{what}: WinError {code}")

    def _windows_final_path(handle: int, path: Path) -> None:
        buffer = ctypes.create_unicode_buffer(32768)
        size = _kernel32.GetFinalPathNameByHandleW(
            handle, buffer, len(buffer), _FILE_NAME_NORMALIZED | _VOLUME_NAME_DOS,
        )
        if size == 0:
            raise _windows_error("final path не прочитан")
        if size >= len(buffer):
            raise JournalError("final path слишком длинный")
        final = buffer.value
        if final.startswith("\\\\?\\UNC\\"):
            final = "\\\\" + final[8:]
        elif final.startswith("\\\\?\\"):
            final = final[4:]
        if os.path.normcase(os.path.abspath(final)) != os.path.normcase(os.path.abspath(path)):
            raise JournalError("descriptor final path не подтверждает containment")

    def _windows_open(path: Path, *, create: bool) -> tuple[int, bool]:
        created = False
        dispositions = [_CREATE_NEW, _OPEN_EXISTING] if create else [_OPEN_EXISTING]
        for disposition in dispositions:
            handle = _kernel32.CreateFileW(
                str(path), _GENERIC_READ | _GENERIC_WRITE,
                _FILE_SHARE_READ | _FILE_SHARE_WRITE, None, disposition,
                _FILE_FLAG_OPEN_REPARSE_POINT, None,
            )
            if handle != _INVALID_HANDLE_VALUE:
                created = disposition == _CREATE_NEW
                break
            error = ctypes.get_last_error()
            if create and error in (80, 183):
                continue
            raise JournalError(f"safe open не выполнен: WinError {error}")
        else:
            raise JournalError("safe open не выполнен")
        try:
            info = _ByHandleFileInformation()
            if not _kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
                raise _windows_error("handle information не прочитана")
            if info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT:
                raise JournalError("journal object является reparse point")
            if info.nNumberOfLinks != 1:
                raise JournalError("journal object имеет hardlink: nlink != 1")
            _windows_final_path(handle, path)
            fd = msvcrt.open_osfhandle(
                handle, os.O_RDWR | os.O_BINARY | os.O_NOINHERIT | os.O_APPEND,
            )
            handle = None  # fd теперь владеет native handle
            try:
                _validate_descriptor(fd, path)
                return fd, created
            except BaseException:
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise
        finally:
            if handle is not None:
                _kernel32.CloseHandle(handle)

    def _lock_descriptor(fd: int) -> None:
        overlapped = _Overlapped()
        if not _kernel32.LockFileEx(
            msvcrt.get_osfhandle(fd), _LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0,
            ctypes.byref(overlapped),
        ):
            raise _windows_error("per-run lock не получен")

    def _unlock_descriptor(fd: int) -> None:
        overlapped = _Overlapped()
        if not _kernel32.UnlockFileEx(
            msvcrt.get_osfhandle(fd), 0, 1, 0, ctypes.byref(overlapped),
        ):
            raise _windows_error("per-run lock не освобождён")

else:
    import fcntl

    def _posix_open(path: Path, *, create: bool) -> tuple[int, bool]:
        directory = path.parent
        name = path.name
        directory_fd = os.open(
            directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        created = False
        try:
            flags = os.O_RDWR | os.O_APPEND | os.O_CLOEXEC | os.O_NOFOLLOW
            if create:
                try:
                    fd = os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd)
                    created = True
                except FileExistsError:
                    fd = os.open(name, flags, dir_fd=directory_fd)
            else:
                fd = os.open(name, flags, dir_fd=directory_fd)
            try:
                info = os.fstat(fd)
                path_info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if _identity(info) != _identity(path_info):
                    raise JournalError("journal path заменён: descriptor identity не совпадает")
            except BaseException:
                os.close(fd)
                raise
            return fd, created
        finally:
            os.close(directory_fd)

    def _posix_safe_open(path: Path, *, create: bool) -> tuple[int, bool]:
        fd, created = _posix_open(path, create=create)
        try:
            _validate_descriptor(fd, path)
            return fd, created
        except BaseException:
            os.close(fd)
            raise

    def _lock_descriptor(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock_descriptor(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _safe_open(path: Path, *, create: bool) -> tuple[int, bool]:
    if os.name == "nt":
        return _windows_open(path, create=create)
    return _posix_safe_open(path, create=create)


def _thread_lock(key: str) -> threading.Lock:
    with _thread_guard:
        return _thread_locks.setdefault(key, threading.Lock())


@contextmanager
def _run_lock(run: str, directory: Path, *, create: bool) -> Iterator[int]:
    key = os.path.normcase(str(directory / run))
    with _thread_lock(key):
        lock_path = directory / f"{run}.lock"
        fd, _created = _safe_open(lock_path, create=create)
        locked = False
        try:
            _lock_descriptor(fd)
            locked = True
            _validate_descriptor(fd, lock_path)
            yield fd
        finally:
            try:
                if locked:
                    _unlock_descriptor(fd)
            finally:
                os.close(fd)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        try:
            count = os.write(fd, view[written:])
        except InterruptedError:
            continue
        if count <= 0:
            raise JournalError("zero write: запись не завершена")
        written += count


def _read_descriptor(fd: int) -> bytes:
    try:
        size = os.fstat(fd).st_size
        if size > MAX_JOURNAL_BYTES:
            raise JournalError("journal больше 64 MiB")
        os.lseek(fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, MAX_JOURNAL_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_JOURNAL_BYTES:
                raise JournalError("journal вырос за пределы 64 MiB")
        raw = b"".join(chunks)
        if len(raw) != os.fstat(fd).st_size:
            raise JournalError("journal изменился во время чтения")
        return raw
    except OSError as exc:
        if isinstance(exc, JournalError):
            raise
        raise JournalError(f"journal read не выполнен: {type(exc).__name__}") from exc


def _read_tip_descriptor(fd: int) -> list[str]:
    """Прочитать append-only anchor под уже удержанным per-run lock."""
    try:
        size = os.fstat(fd).st_size
        if size > MAX_TIP_BYTES:
            raise JournalError("anchor больше 64 MiB")
        os.lseek(fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, MAX_TIP_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_TIP_BYTES:
                raise JournalError("anchor вырос за пределы 64 MiB")
        raw = b"".join(chunks)
        if len(raw) != os.fstat(fd).st_size:
            raise JournalError("anchor изменился во время чтения")
    except OSError as exc:
        if isinstance(exc, JournalError):
            raise
        raise JournalError(f"anchor read не выполнен: {type(exc).__name__}") from exc
    if not raw:
        return []
    if len(raw) % TIP_LINE_BYTES or not raw.endswith(b"\n"):
        raise JournalError("anchor имеет оборванную или неканоническую строку")
    tips: list[str] = []
    for offset in range(0, len(raw), TIP_LINE_BYTES):
        if raw[offset + 64:offset + 65] != b"\n":
            raise JournalError("anchor имеет неканонический разделитель строк")
        line = raw[offset:offset + 64]
        try:
            value = line.decode("ascii")
        except UnicodeDecodeError as exc:
            raise JournalError("anchor не является lowercase SHA-256") from exc
        if not SHA256_RE.fullmatch(value):
            raise JournalError("anchor не является lowercase SHA-256")
        tips.append(value)
    return tips


def _validate_anchor(records: list[dict], tips: list[str]) -> tuple[int, list[str]]:
    """Вернуть доверенный префикс и первую проблему journal/anchor связи."""
    common = min(len(records), len(tips))
    for index in range(common):
        if records[index]["sha256"] != tips[index]:
            return index, [f"anchor {index + 1}: hash не совпадает с journal записью"]
    if len(tips) > len(records):
        return len(records), [f"journal не содержит закреплённую запись {len(records) + 1}"]
    if len(records) > len(tips):
        return len(tips), [f"запись {len(tips) + 1} не закреплена anchor"]
    return len(records), []


def _reject_float(_text: str):
    raise JournalError("float в canonical JSON запрещён")


def _reject_constant(_text: str):
    raise JournalError("NaN/Infinity в canonical JSON запрещены")


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise JournalError("duplicate JSON key запрещён")
        result[key] = value
    return result


def _parse_record(line: bytes, run: str, seq: int, expected_prev: str) -> dict:
    if len(line) > MAX_RECORD_BYTES:
        raise JournalError("запись больше разрешённого размера")
    try:
        text = line.decode("utf-8")
        entry = json.loads(
            text, parse_float=_reject_float, parse_constant=_reject_constant,
            object_pairs_hook=_pairs_without_duplicates,
        )
    except JournalError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise JournalError("строка не является canonical UTF-8 JSON") from exc
    if not isinstance(entry, dict) or set(entry) != RECORD_FIELDS:
        raise JournalError("schema envelope не совпадает")
    if isinstance(entry["v"], bool) or entry["v"] != VERSION:
        raise JournalError("версия не поддерживается: нужен v2")
    if isinstance(entry["seq"], bool) or not isinstance(entry["seq"], int) or entry["seq"] != seq:
        raise JournalError(f"seq не непрерывен: ждали {seq}")
    if entry["run"] != run:
        raise JournalError("run ID записи не совпадает с именем журнала")
    if not isinstance(entry["prev"], str) or not SHA256_RE.fullmatch(entry["prev"]):
        raise JournalError("prev не является SHA-256")
    if entry["prev"] != expected_prev:
        raise JournalError("prev не связан с предыдущей записью")
    if not isinstance(entry["sha256"], str) or not SHA256_RE.fullmatch(entry["sha256"]):
        raise JournalError("sha256 не является SHA-256")
    at = entry["at"]
    if not isinstance(at, str) or not TIME_RE.fullmatch(at):
        raise JournalError("at не является UTC microseconds")
    try:
        parsed = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise JournalError("at не разбирается как UTC время") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise JournalError("at не является UTC")
    _validate_event(entry["event"])
    if line != _canonical(entry):
        raise JournalError("строка не является canonical compact JSON")
    if not hmac.compare_digest(entry["sha256"], record_hash(entry)):
        raise JournalError("хеш не сходится — полный envelope изменён")
    return entry


def _validate_records(raw: bytes, run: str, *, allow_empty: bool = False) -> tuple[list[dict], list[str]]:
    if not raw:
        return [], [] if allow_empty else ["пустой журнал"]
    records: list[dict] = []
    expected_prev = ZERO
    parts = raw.split(b"\n")
    torn = not raw.endswith(b"\n")
    complete = parts[:-1]
    for index, line in enumerate(complete, 1):
        if not line:
            return records, [f"строка {index}: пустая строка запрещена"]
        try:
            entry = _parse_record(line, run, index, expected_prev)
            records.append(entry)
            expected_prev = entry["sha256"]
        except JournalError as exc:
            return records, [f"строка {index}: {exc}"]
    if torn:
        return records, [f"строка {len(complete) + 1}: оборванный хвост"]
    return records, []


def _journal_path(directory: Path, run: str) -> Path:
    # Run уже проверен; имя фиксировано и не содержит separators/dot segments.
    return directory / f"{run}.jsonl"


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return  # Windows не даёт directory fsync; это не выдаётся за выполненный шаг.
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def append(run: str, event: str, directory: Path | None = None) -> dict:
    """Дописать событие и вернуть ACK только после journal/anchor fsync."""
    run = _validate_run(run)
    event = _validate_event(event)
    base, _created_directories = _prepare_directory(
        Path(directory) if directory is not None else DEFAULT_DIR, create=True,
    )
    path = _journal_path(base, run)
    lock_path = base / f"{run}.lock"
    with _run_lock(run, base, create=True) as lock_fd:
        _validate_descriptor(lock_fd, lock_path)
        tips = _read_tip_descriptor(lock_fd)
        lock_before = os.fstat(lock_fd)
        if lock_before.st_size + TIP_LINE_BYTES > MAX_TIP_BYTES:
            raise JournalError("anchor превысит 64 MiB")
        fd, created = _safe_open(path, create=True)
        try:
            raw = _read_descriptor(fd)
            records, problems = _validate_records(raw, run, allow_empty=created)
            if problems:
                raise JournalError(f"append отказан: {problems[0]}")
            trusted, anchor_problems = _validate_anchor(records, tips)
            if anchor_problems:
                raise JournalError(f"append отказан: {anchor_problems[0]}")
            if trusted != len(records):
                raise JournalError("append отказан: journal/anchor prefix не совпадает")
            before = os.fstat(fd)
            if before.st_size != len(raw):
                raise JournalError("journal изменился до append")
            seq = len(records) + 1
            prev = records[-1]["sha256"] if records else ZERO
            entry = {
                "v": VERSION, "seq": seq, "prev": prev, "at": _now(),
                "run": run, "event": event,
            }
            entry["sha256"] = record_hash(entry)
            line = _canonical(entry) + b"\n"
            if len(line) > MAX_RECORD_BYTES:
                raise JournalError("canonical запись больше разрешённого размера")
            if len(raw) + len(line) > MAX_JOURNAL_BYTES:
                raise JournalError("journal превысит 64 MiB")
            _write_all(fd, line)
            os.fsync(fd)
            _validate_descriptor(fd, path)
            _write_all(lock_fd, entry["sha256"].encode("ascii") + b"\n")
            os.fsync(lock_fd)
            _validate_descriptor(lock_fd, lock_path)
            after = os.fstat(fd)
            lock_after = os.fstat(lock_fd)
            if _identity(before) != _identity(after) or after.st_size != len(raw) + len(line):
                raise JournalError("journal identity/size изменились до ACK")
            if _identity(lock_before) != _identity(lock_after) or lock_after.st_size != lock_before.st_size + TIP_LINE_BYTES:
                raise JournalError("anchor identity/size изменились до ACK")
            # Fsync каталога сохраняет его entries, но не собственную entry в parent.
            # Поэтому перед каждым ACK закрепляем всю ancestry, а не только новые
            # каталоги текущего вызова: retry после сбоя не должен обойти durability.
            for directory in (base, *base.parents):
                _fsync_directory(directory)
            _validate_descriptor(fd, path)
            _validate_descriptor(lock_fd, lock_path)
            return entry
        except OSError as exc:
            if isinstance(exc, JournalError):
                raise
            raise JournalError(f"append не выполнен: {type(exc).__name__}") from exc
        finally:
            os.close(fd)


def _read_verified(run: str, directory: Path | None) -> tuple[bytes, list[dict], list[str]]:
    run = _validate_run(run)
    base, _created_directories = _prepare_directory(
        Path(directory) if directory is not None else DEFAULT_DIR, create=False,
    )
    path = _journal_path(base, run)
    try:
        path.lstat()
    except FileNotFoundError:
        return b"", [], [f"нет хостового журнала прогона {run}"]
    except OSError as exc:
        return b"", [], [f"journal path недоступен: {type(exc).__name__}"]
    try:
        with _run_lock(run, base, create=False) as lock_fd:
            _validate_descriptor(lock_fd, base / f"{run}.lock")
            tips = _read_tip_descriptor(lock_fd)
            fd, _created = _safe_open(path, create=False)
            try:
                _validate_descriptor(fd, path)
                raw = _read_descriptor(fd)
                records, journal_problems = _validate_records(raw, run)
                trusted, anchor_problems = _validate_anchor(records, tips)
                records = records[:trusted]
                problems = list(journal_problems)
                problems.extend(anchor_problems)
                _validate_descriptor(fd, path)
                _validate_descriptor(lock_fd, base / f"{run}.lock")
                return raw, records, problems
            finally:
                os.close(fd)
    except (OSError, ValueError) as exc:
        return b"", [], [f"journal refusal: {exc}"]


def verify(run: str, directory: Path | None = None) -> tuple[int, list[str]]:
    """Пересчитать всю цепочку. Возвращает (верный префикс, проблемы)."""
    try:
        _raw, records, problems = _read_verified(run, directory)
        return len(records), problems
    except (JournalError, ValueError) as exc:
        return 0, [str(exc)]


def events(run: str, directory: Path | None = None) -> list[str]:
    """События только целиком проверенной цепочки; повреждение даёт [], не префикс."""
    try:
        _raw, records, problems = _read_verified(run, directory)
    except (JournalError, ValueError):
        return []
    if problems:
        return []
    return [entry["event"] for entry in records]


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print("host_journal <append|verify|get> <прогон> [событие]", file=sys.stderr)
        return 2
    action, run = argv[0], argv[1] if len(argv) > 1 else ""
    if action == "append":
        if len(argv) < 3:
            print("нужно событие", file=sys.stderr)
            return 2
        try:
            entry = append(run, argv[2])
        except JournalError as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"seq": entry["seq"], "sha256": entry["sha256"]}))
        return 0
    if action == "verify":
        good, problems = verify(run)
        print(f"записей верно: {good}")
        for problem in problems:
            print(f"  [!] {problem}")
        return 0 if not problems else 1
    if action == "get":
        try:
            raw, _records, problems = _read_verified(run, DEFAULT_DIR)
        except JournalError as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 1
        if problems:
            print(f"  [!] {problems[0]}", file=sys.stderr)
            return 1
        sys.stdout.write(raw.decode("utf-8"))
        return 0
    print(f"неизвестное действие: {action}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
