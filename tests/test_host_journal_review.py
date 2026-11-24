"""HOST-JOURNAL-SAFETY-R1-REVIEW: отдельные controls для находок review.

Запуск: python tests/test_host_journal_review.py
Windows: 11/11 без N/A. POSIX: 10/11 + ровно один явный N/A (Windows handle branch).
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import host_journal  # noqa: E402

CASES: list[tuple[str, callable]] = []
HASH_DOMAIN = b"HOST-JOURNAL-RECORD-V2\0"


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def refuse(action) -> None:
    try:
        action()
    except Exception:
        return
    raise AssertionError("опасная операция завершилась успешно")


def canonical(entry: dict) -> bytes:
    return json.dumps(
        entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def rehash(entry: dict) -> None:
    body = {key: value for key, value in entry.items() if key != "sha256"}
    entry["sha256"] = hashlib.sha256(HASH_DOMAIN + canonical(body)).hexdigest()


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def write_rows(path: Path, entries: list[dict]) -> None:
    path.write_bytes(b"".join(canonical(entry) + b"\n" for entry in entries))


@case("genesis prev с пересчётом hash отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("genesis-prev", "a", directory)
        host_journal.append("genesis-prev", "b", directory)
        path = directory / "genesis-prev.jsonl"
        entries = read_rows(path)
        entries[0]["prev"] = "1" * 64
        rehash(entries[0])
        entries[1]["prev"] = entries[0]["sha256"]
        rehash(entries[1])
        write_rows(path, entries)
        good, problems = host_journal.verify("genesis-prev", directory)
        assert good == 0 and problems, (good, problems)
        assert host_journal.events("genesis-prev", directory) == []
        before = path.read_bytes()
        refuse(lambda: host_journal.append("genesis-prev", "c", directory))
        assert path.read_bytes() == before


@case("later prev с пересчётом цепочки отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for event in ("a", "b", "c"):
            host_journal.append("later-prev", event, directory)
        path = directory / "later-prev.jsonl"
        entries = read_rows(path)
        entries[1]["prev"] = "2" * 64
        rehash(entries[1])
        entries[2]["prev"] = entries[1]["sha256"]
        rehash(entries[2])
        write_rows(path, entries)
        good, problems = host_journal.verify("later-prev", directory)
        assert good == 1 and problems, (good, problems)
        assert host_journal.events("later-prev", directory) == []


@case("удаление середины с перенумерацией отвергнуто")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for event in ("a", "b", "c"):
            host_journal.append("renumbered", event, directory)
        path = directory / "renumbered.jsonl"
        entries = read_rows(path)
        kept = [entries[0], entries[2]]
        kept[1]["seq"] = 2
        kept[1]["prev"] = kept[0]["sha256"]
        rehash(kept[1])
        write_rows(path, kept)
        good, problems = host_journal.verify("renumbered", directory)
        assert good == 1 and problems, (good, problems)


@case("escaped events проходят append→verify round trip")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        events = ("\x00" * 65536, '"' * 65536, "\\" * 65536, "é" * 32768)
        for index, event in enumerate(events):
            run = f"escaped-{index}"
            host_journal.append(run, event, directory)
            good, problems = host_journal.verify(run, directory)
            assert good == 1 and problems == [], (index, good, problems)
            assert host_journal.events(run, directory) == [event]
            assert len((directory / f"{run}.jsonl").read_bytes()) <= host_journal.MAX_RECORD_BYTES


@case("RecursionError нормализован в fail-closed отказ")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("deep-json", "a", directory)
        path = directory / "deep-json.jsonl"
        line = path.read_bytes().rstrip(b"\n")
        nested = ("[" * 5000 + "0" + "]" * 5000).encode("ascii")
        path.write_bytes(line[:-1] + b',"extra":' + nested + b"}\n")
        good, problems = host_journal.verify("deep-json", directory)
        assert good == 0 and problems, (good, problems)
        assert host_journal.events("deep-json", directory) == []
        refuse(lambda: host_journal.append("deep-json", "b", directory))


@case("Windows fd закрыт при пост-transfer отказе")
def _():
    if os.name != "nt":
        return "N/A"
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        captured: list[int] = []
        original_open = host_journal.msvcrt.open_osfhandle
        original_validate = host_journal._validate_descriptor

        def tracked_open(handle, flags):
            fd = original_open(handle, flags)
            captured.append(fd)
            return fd

        def fail_journal(fd, path):
            if Path(path).name == "handle-run.jsonl":
                raise host_journal.JournalError("injected post-transfer validation failure")
            return original_validate(fd, path)

        host_journal.msvcrt.open_osfhandle = tracked_open
        host_journal._validate_descriptor = fail_journal
        try:
            refuse(lambda: host_journal.append("handle-run", "a", directory))
        finally:
            host_journal.msvcrt.open_osfhandle = original_open
            host_journal._validate_descriptor = original_validate
        leaked: list[int] = []
        for fd in captured:
            try:
                os.fstat(fd)
            except OSError:
                continue
            leaked.append(fd)
            os.close(fd)
        assert leaked == [], leaked


@case("journal open использует O_APPEND")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        observed: list[int] = []
        if os.name == "nt":
            original = host_journal.msvcrt.open_osfhandle

            def tracked(handle, flags):
                observed.append(flags)
                return original(handle, flags)

            host_journal.msvcrt.open_osfhandle = tracked
            try:
                host_journal.append("append-flag", "a", directory)
            finally:
                host_journal.msvcrt.open_osfhandle = original
        else:
            original = os.open

            def tracked(path, flags, *args, **kwargs):
                fd = original(path, flags, *args, **kwargs)
                if str(path).endswith(".jsonl"):
                    observed.append(flags)
                return fd

            os.open = tracked
            try:
                host_journal.append("append-flag", "a", directory)
            finally:
                os.open = original
        assert observed and all(flags & os.O_APPEND for flags in observed), observed


@case("8 threads дописывают 80 непрерывных записей")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)

        def worker(index: int) -> None:
            for step in range(10):
                host_journal.append("thread-run", f"thread-{index}-{step}", directory)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, range(8)))
        good, problems = host_journal.verify("thread-run", directory)
        entries = read_rows(directory / "thread-run.jsonl")
        assert good == 80 and problems == [], (good, problems)
        assert [entry["seq"] for entry in entries] == list(range(1, 81))


@case("fsync наблюдён после полной финальной записи")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        observed: list[bytes] = []
        original = os.fsync

        def tracked(fd):
            original(fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return
            position = os.lseek(fd, 0, os.SEEK_CUR)
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                chunks: list[bytes] = []
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                observed.append(b"".join(chunks))
            finally:
                os.lseek(fd, position, os.SEEK_SET)

        os.fsync = tracked
        try:
            host_journal.append("fsync-complete", "a", Path(tmp))
        finally:
            os.fsync = original
        assert any(data.endswith(b"\n") and json.loads(data)["event"] == "a" for data in observed)


@case("положительная связанная цепочка проходит")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for event in ("a", "b", "c"):
            host_journal.append("linked-positive", event, directory)
        good, problems = host_journal.verify("linked-positive", directory)
        entries = read_rows(directory / "linked-positive.jsonl")
        assert good == 3 and problems == []
        assert entries[0]["prev"] == "0" * 64
        assert all(entries[index]["prev"] == entries[index - 1]["sha256"] for index in (1, 2))


@case("platform dispatch явно различает Windows и POSIX")
def _():
    if os.name == "nt":
        assert hasattr(host_journal, "msvcrt")
    else:
        assert not hasattr(host_journal, "msvcrt")


def main() -> int:
    failed = 0
    na = 0
    passed = 0
    for name, fn in CASES:
        try:
            result = fn()
            if result == "N/A":
                na += 1
                print(f"[N/A] {name}")
                continue
            passed += 1
            print(f"[ok] {name}")
        except Exception as exc:  # noqa: BLE001 — печатаем все провалы
            failed += 1
            print(f"[FAIL] {name} — {type(exc).__name__}: {exc}")
    print(f"\nhost journal review: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    expected_na = 0 if os.name == "nt" else 1
    good = failed == 0 and na == expected_na and len(CASES) == 11
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
