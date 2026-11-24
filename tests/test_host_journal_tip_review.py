"""HOST-JOURNAL-SAFETY-R2-DURABILITY: strengthened post-review controls.

Запуск: python tests/test_host_journal_tip_review.py
Windows: 2 passed + 2 явных POSIX-only N/A. POSIX: 4/4 без N/A.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
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


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def write_rows(path: Path, entries: list[dict]) -> None:
    path.write_bytes(b"".join(canonical(entry) + b"\n" for entry in entries))


@case("промежуточный anchor LF проверяется")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("delimiter", "a", directory)
        host_journal.append("delimiter", "b", directory)
        path = directory / "delimiter.lock"
        raw = bytearray(path.read_bytes())
        assert raw[64] == 10
        raw[64] = ord("0")
        path.write_bytes(raw)
        good, problems = host_journal.verify("delimiter", directory)
        assert good == 0 and problems, (good, problems)
        assert host_journal.events("delimiter", directory) == []
        before = (directory / "delimiter.jsonl").read_bytes()
        refuse(lambda: host_journal.append("delimiter", "c", directory))
        assert (directory / "delimiter.jsonl").read_bytes() == before


@case("compound corruption не завышает trusted prefix")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for event in ("a", "b", "c"):
            host_journal.append("compound", event, directory)
        path = directory / "compound.jsonl"
        entries = rows(path)
        entries[0]["event"] = "changed"
        rehash(entries[0])
        entries[1]["prev"] = entries[0]["sha256"]
        rehash(entries[1])
        entries[2]["prev"] = entries[1]["sha256"]
        entries[2]["seq"] = 99
        rehash(entries[2])
        write_rows(path, entries)
        good, problems = host_journal.verify("compound", directory)
        assert good == 0 and problems, (good, problems)
        assert any("anchor" in problem for problem in problems), problems
        assert host_journal.events("compound", directory) == []


@case("POSIX append fsync закрепляет всю ancestry каталогов")
def _():
    if os.name != "posix":
        return "N/A"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        parent = root / "new-parent"
        child = parent / "new-child"
        journal = child / "new-journal"
        observed: list[Path] = []
        original = os.fsync

        def tracked(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                target = os.readlink(f"/proc/self/fd/{fd}")
                observed.append(Path(target).resolve())
            return original(fd)

        os.fsync = tracked
        try:
            host_journal.append("durable", "a", journal)
        finally:
            os.fsync = original
        resolved = journal.resolve()
        assert observed == [resolved, *resolved.parents], observed


@case("POSIX retry после directory fsync failure повторяет durability шаг")
def _():
    if os.name != "posix":
        return "N/A"
    with tempfile.TemporaryDirectory() as tmp:
        journal = Path(tmp) / "new-parent" / "new-journal"
        resolved = journal.resolve()
        observed: list[Path] = []
        fail_once = [True]
        original = os.fsync

        def tracked(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                target = Path(os.readlink(f"/proc/self/fd/{fd}")).resolve()
                observed.append(target)
                if fail_once[0] and target == resolved:
                    fail_once[0] = False
                    raise OSError("injected directory fsync failure")
            return original(fd)

        os.fsync = tracked
        try:
            refuse(lambda: host_journal.append("retry-durable", "a", journal))
            assert observed == [resolved], observed
            assert len(rows(journal / "retry-durable.jsonl")) == 1
            assert (journal / "retry-durable.lock").stat().st_size == 65
            observed.clear()
            entry = host_journal.append("retry-durable", "b", journal)
        finally:
            os.fsync = original
        assert entry["seq"] == 2, entry
        assert observed == [resolved, *resolved.parents], observed


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
    print(f"\nhost journal durability: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
