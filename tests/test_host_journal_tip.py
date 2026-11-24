"""HOST-JOURNAL-SAFETY-R2-TIP: внешний per-record anchor в lock-файле.

Запуск: python tests/test_host_journal_tip.py
Windows и POSIX: 12/12 без N/A.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
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


def journal_path(directory: Path, run: str) -> Path:
    return directory / f"{run}.jsonl"


def anchor_path(directory: Path, run: str) -> Path:
    return directory / f"{run}.lock"


def read_anchor(path: Path) -> list[str]:
    raw = path.read_bytes()
    if not raw:
        return []
    assert raw.endswith(b"\n"), raw
    return [line.decode("ascii") for line in raw.splitlines()]


def write_anchor(path: Path, hashes: list[str]) -> None:
    path.write_bytes(b"".join(value.encode("ascii") + b"\n" for value in hashes))


def append_three(directory: Path, run: str = "tip-run") -> list[dict]:
    for event in ("a", "b", "c"):
        host_journal.append(run, event, directory)
    return read_rows(journal_path(directory, run))


def read_fd(fd: int) -> bytes:
    position = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.lseek(fd, position, os.SEEK_SET)


@case("positive anchor повторяет точные journal hashes")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        entries = append_three(directory)
        assert read_anchor(anchor_path(directory, "tip-run")) == [row["sha256"] for row in entries]
        assert host_journal.verify("tip-run", directory) == (3, [])


@case("renumbered deletion даёт точный trusted prefix")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        entries = append_three(directory, "renumbered-tip")
        path = journal_path(directory, "renumbered-tip")
        kept = [entries[0], entries[2]]
        kept[1]["seq"] = 2
        kept[1]["prev"] = kept[0]["sha256"]
        rehash(kept[1])
        write_rows(path, kept)
        good, problems = host_journal.verify("renumbered-tip", directory)
        assert good == 1 and problems, (good, problems)
        assert host_journal.events("renumbered-tip", directory) == []
        before = path.read_bytes()
        refuse(lambda: host_journal.append("renumbered-tip", "d", directory))
        assert path.read_bytes() == before


@case("rehashed event mutation ловится anchor position")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        entries = append_three(directory, "mutated-tip")
        entries[1]["event"] = "changed"
        for index in range(1, len(entries)):
            entries[index]["prev"] = entries[index - 1]["sha256"]
            rehash(entries[index])
        write_rows(journal_path(directory, "mutated-tip"), entries)
        good, problems = host_journal.verify("mutated-tip", directory)
        assert good == 1 and problems, (good, problems)
        assert host_journal.events("mutated-tip", directory) == []


@case("prefix truncation не выдаётся за полный журнал")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        entries = append_three(directory, "prefix-tip")
        write_rows(journal_path(directory, "prefix-tip"), entries[:2])
        good, problems = host_journal.verify("prefix-tip", directory)
        assert good == 2 and problems, (good, problems)
        assert host_journal.events("prefix-tip", directory) == []
        refuse(lambda: host_journal.append("prefix-tip", "d", directory))


@case("unanchored suffix отвергается")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        entries = append_three(directory, "suffix-tip")
        write_anchor(anchor_path(directory, "suffix-tip"), [row["sha256"] for row in entries[:2]])
        good, problems = host_journal.verify("suffix-tip", directory)
        assert good == 2 and problems, (good, problems)
        assert host_journal.events("suffix-tip", directory) == []
        refuse(lambda: host_journal.append("suffix-tip", "d", directory))


@case("missing anchor не мигрируется")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("missing-tip", "a", directory)
        anchor_path(directory, "missing-tip").write_bytes(b"")
        good, problems = host_journal.verify("missing-tip", directory)
        assert good == 0 and problems, (good, problems)
        assert host_journal.events("missing-tip", directory) == []
        refuse(lambda: host_journal.append("missing-tip", "b", directory))


@case("malformed anchor отвергается")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("bad-tip", "a", directory)
        anchor_path(directory, "bad-tip").write_bytes(b"g" * 64 + b"\n")
        good, problems = host_journal.verify("bad-tip", directory)
        assert good == 0 and problems, (good, problems)
        assert host_journal.events("bad-tip", directory) == []


@case("torn anchor отвергается")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        entry = host_journal.append("torn-tip", "a", directory)
        anchor_path(directory, "torn-tip").write_bytes(entry["sha256"].encode("ascii"))
        good, problems = host_journal.verify("torn-tip", directory)
        assert good == 0 and problems, (good, problems)
        assert host_journal.events("torn-tip", directory) == []


@case("journal fsync наблюдён до anchor fsync и ACK")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        observed: list[tuple[str, bytes]] = []
        original = os.fsync

        def tracked(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                observed.append(("dir", b""))
            else:
                observed.append(("file", read_fd(fd)))
            return original(fd)

        os.fsync = tracked
        try:
            entry = host_journal.append("order-tip", "a", directory)
        finally:
            os.fsync = original
        journal_snapshots = [index for index, (kind, data) in enumerate(observed) if kind == "file" and b'"sha256"' in data]
        anchor_snapshots = [index for index, (kind, data) in enumerate(observed) if kind == "file" and data == entry["sha256"].encode("ascii") + b"\n"]
        assert journal_snapshots and anchor_snapshots, observed
        assert min(journal_snapshots) < min(anchor_snapshots), observed


@case("anchor fsync failure не даёт ACK")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        original = os.fsync
        failed = False

        def tracked(fd):
            nonlocal failed
            if not stat.S_ISDIR(os.fstat(fd).st_mode):
                data = read_fd(fd)
                if len(data) == 65 and data.endswith(b"\n") and all(chr(byte) in "0123456789abcdef" for byte in data[:-1]):
                    failed = True
                    raise OSError("injected anchor fsync failure")
            return original(fd)

        os.fsync = tracked
        try:
            refuse(lambda: host_journal.append("anchor-fail", "a", directory))
        finally:
            os.fsync = original
        assert failed, "anchor fsync не был инъецирован"


@case("crash gap journal без anchor fail-closed")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("gap-tip", "a", directory)
        host_journal.append("gap-tip", "b", directory)
        entries = read_rows(journal_path(directory, "gap-tip"))
        write_anchor(anchor_path(directory, "gap-tip"), [entries[0]["sha256"]])
        good, problems = host_journal.verify("gap-tip", directory)
        assert good == 1 and problems, (good, problems)
        assert host_journal.events("gap-tip", directory) == []
        before = journal_path(directory, "gap-tip").read_bytes()
        refuse(lambda: host_journal.append("gap-tip", "c", directory))
        assert journal_path(directory, "gap-tip").read_bytes() == before


@case("4 процесса дают 80 точных journal/anchor пар")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        script = (
            "import json,sys\n"
            "from pathlib import Path\n"
            "from bin import host_journal as h\n"
            "print('ready', flush=True)\n"
            "sys.stdin.readline()\n"
            "run, worker, directory = sys.argv[1:4]\n"
            "out=[]\n"
            "for i in range(20):\n"
            "    out.append(h.append(run, f'worker-{worker}-{i}', Path(directory)))\n"
            "print(json.dumps(out), flush=True)\n"
        )
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", script, "concurrent-tip", str(index), str(directory)],
                cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            for index in range(4)
        ]
        try:
            assert all(process.stdout.readline().strip() == "ready" for process in processes)
            for process in processes:
                process.stdin.write("go\n")
                process.stdin.flush()
            results = [process.communicate(timeout=30) for process in processes]
            assert all(process.returncode == 0 for process in processes), results
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        entries = read_rows(journal_path(directory, "concurrent-tip"))
        anchors = read_anchor(anchor_path(directory, "concurrent-tip"))
        assert len(entries) == 80
        assert [entry["seq"] for entry in entries] == list(range(1, 81))
        assert anchors == [entry["sha256"] for entry in entries]
        assert host_journal.verify("concurrent-tip", directory) == (80, [])


def main() -> int:
    passed = 0
    failed = 0
    na = 0
    for name, fn in CASES:
        try:
            result = fn()
            if result == "N/A":
                na += 1
                print(f"[N/A] {name}")
            else:
                passed += 1
                print(f"[ok] {name}")
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {name} — {type(exc).__name__}: {exc}")
    print(f"\nhost journal tip: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    return 0 if failed == 0 and na == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
