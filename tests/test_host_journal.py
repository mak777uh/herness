"""W07A: хостовый журнал обязан отказать до ACK, а не красиво сообщить о повреждении.

Запуск: python tests/test_host_journal.py
Порог зарегистрирован до кода: HOST-JOURNAL-SAFETY-R1, 34/34 без N/A.
"""

from __future__ import annotations

import hashlib
import json
import os
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
    """Любой отказ принимается; главное — операция не завершилась успешно."""
    try:
        action()
    except Exception:
        return
    raise AssertionError("опасная операция завершилась успешно")


def verify_refused(run: str, directory: Path) -> bool:
    try:
        good, problems = host_journal.verify(run, directory)
    except Exception:
        return True
    return good == 0 and bool(problems)


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_rows(path: Path, entries: list[dict]) -> None:
    """Каноническая перезапись мутанта: проверяемый инвариант меняется в одиночку."""
    text = "".join(json.dumps(
        entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ) + "\n" for entry in entries)
    path.write_bytes(text.encode("utf-8"))


def expected_hash(entry: dict) -> str:
    body = {key: value for key, value in entry.items() if key != "sha256"}
    canonical = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(HASH_DOMAIN + canonical).hexdigest()


def make_reparse(target: Path, link: Path) -> None:
    """Фактический symlink на POSIX или junction/reparse point на Windows."""
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
        )
        if result.returncode != 0:
            raise AssertionError(f"не удалось создать junction: rc={result.returncode}")
    else:
        os.symlink(target, link, target_is_directory=True)


@case("цепочка растёт и проверяется")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for index in range(3):
            host_journal.append("run-1", f"событие {index}", directory)
        good, problems = host_journal.verify("run-1", directory)
        assert good == 3, (good, problems)
        assert problems == [], problems


@case("подмена события ломает проверку")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("run-2", "run/start task: честная", directory)
        host_journal.append("run-2", "tool/call read a.md", directory)
        path = directory / "run-2.jsonl"
        entries = rows(path)
        entries[0]["event"] = "run/start task: подделанная"
        write_rows(path, entries)
        good, problems = host_journal.verify("run-2", directory)
        assert good == 0 and problems, (good, problems)
        assert "измен" in problems[0] or "хеш" in problems[0], problems


@case("выкинутая запись ломает цепочку prev")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for index in range(3):
            host_journal.append("run-3", f"событие {index}", directory)
        path = directory / "run-3.jsonl"
        entries = rows(path)
        write_rows(path, [entries[0], entries[2]])
        good, problems = host_journal.verify("run-3", directory)
        assert good == 1 and problems, (good, problems)
        assert "prev" in problems[0] or "seq" in problems[0], problems


@case("дописывание идёт за последней записью")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        first = host_journal.append("run-4", "a", directory)
        second = host_journal.append("run-4", "b", directory)
        assert first["seq"] == 1 and second["seq"] == 2
        assert second["prev"] == first["sha256"]
        good, problems = host_journal.verify("run-4", directory)
        assert good == 2 and problems == []


@case("чужого журнала нет — проблема, а не пустой успех")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        good, problems = host_journal.verify("нет-такого", Path(tmp))
        assert good == 0 and problems, (good, problems)


@case("canonical v2 хеширует полный envelope")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        entry = host_journal.append("canonical-run", "run/start", directory)
        assert entry["v"] == 2 and entry["run"] == "canonical-run", entry
        assert entry["sha256"] == expected_hash(entry), entry
        raw = (directory / "canonical-run.jsonl").read_bytes()
        canonical = json.dumps(
            entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8") + b"\n"
        assert raw == canonical, raw


@case("traversal run ID отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        directory = root / "journal"
        directory.mkdir()
        refuse(lambda: host_journal.append("../outside", "run/start", directory))
        assert not (root / "outside.jsonl").exists()


@case("absolute run ID отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        directory = root / "journal"
        directory.mkdir()
        target = root / "absolute"
        refuse(lambda: host_journal.append(str(target), "run/start", directory))
        assert not Path(str(target) + ".jsonl").exists()


@case("не-opaque алфавит run ID отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for run in ("Run-1", "run_1", "run.1", "прогон", "-run", "run-"):
            refuse(lambda run=run: host_journal.append(run, "run/start", directory))
        assert list(directory.glob("*.jsonl")) == []


@case("overlong run ID отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        refuse(lambda: host_journal.append("a" * 129, "run/start", Path(tmp)))


@case("NUL в run ID отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        refuse(lambda: host_journal.append("run\0x", "run/start", Path(tmp)))


@case("legacy v1 отвергнут без миграции")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        event = "run/start legacy"
        prev = "0" * 64
        entry = {
            "v": 1, "seq": 1, "prev": prev,
            "sha256": hashlib.sha256((prev + "\n" + event).encode("utf-8")).hexdigest(),
            "at": "2026-11-24T00:00:00+00:00", "event": event,
        }
        write_rows(directory / "legacy.jsonl", [entry])
        good, problems = host_journal.verify("legacy", directory)
        assert good == 0 and problems, (good, problems)


@case("подмена seq обнаружена")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("seq-run", "a", directory)
        host_journal.append("seq-run", "b", directory)
        path = directory / "seq-run.jsonl"
        entries = rows(path)
        entries[1]["seq"] = 99
        write_rows(path, entries)
        good, problems = host_journal.verify("seq-run", directory)
        assert good <= 1 and problems, (good, problems)


@case("подмена версии обнаружена")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("version-run", "a", directory)
        path = directory / "version-run.jsonl"
        entries = rows(path)
        entries[0]["v"] = 3
        write_rows(path, entries)
        good, problems = host_journal.verify("version-run", directory)
        assert good == 0 and problems, (good, problems)


@case("подмена timestamp полного envelope обнаружена")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("time-run", "a", directory)
        path = directory / "time-run.jsonl"
        entries = rows(path)
        entries[0]["at"] = "2000-01-01T00:00:00Z"
        write_rows(path, entries)
        good, problems = host_journal.verify("time-run", directory)
        assert good == 0 and problems, (good, problems)


@case("валидная цепочка чужого run ID отвергнута")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("run-a", "a", directory)
        (directory / "run-b.jsonl").write_bytes((directory / "run-a.jsonl").read_bytes())
        good, problems = host_journal.verify("run-b", directory)
        assert good == 0 and problems, (good, problems)


@case("неизвестное поле envelope отвергнуто")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("field-run", "a", directory)
        path = directory / "field-run.jsonl"
        entries = rows(path)
        entries[0]["extra"] = "not-in-schema"
        write_rows(path, entries)
        good, problems = host_journal.verify("field-run", directory)
        assert good == 0 and problems, (good, problems)


@case("неcanonical JSON строка отвергнута")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("format-run", "a", directory)
        path = directory / "format-run.jsonl"
        entry = rows(path)[0]
        path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
        good, problems = host_journal.verify("format-run", directory)
        assert good == 0 and problems, (good, problems)


@case("duplicate JSON key отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("duplicate-run", "a", directory)
        path = directory / "duplicate-run.jsonl"
        line = path.read_text(encoding="utf-8").rstrip("\n")
        path.write_text(line[:-1] + ',"seq":1}\n', encoding="utf-8")
        good, problems = host_journal.verify("duplicate-run", directory)
        assert good == 0 and problems, (good, problems)


@case("malformed середина блокирует append")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("middle-run", "a", directory)
        host_journal.append("middle-run", "b", directory)
        path = directory / "middle-run.jsonl"
        lines = path.read_bytes().splitlines(keepends=True)
        path.write_bytes(lines[0] + b"{broken\n" + lines[1])
        before = path.read_bytes()
        refuse(lambda: host_journal.append("middle-run", "c", directory))
        assert path.read_bytes() == before


@case("оборванный хвост блокирует append без обрезки")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("tail-run", "a", directory)
        path = directory / "tail-run.jsonl"
        with path.open("ab") as handle:
            handle.write(b'{"v":2')
        before = path.read_bytes()
        refuse(lambda: host_journal.append("tail-run", "b", directory))
        assert path.read_bytes() == before


@case("пустой журнал не является валидным")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        (directory / "empty.jsonl").write_bytes(b"")
        good, problems = host_journal.verify("empty", directory)
        assert good == 0 and problems, (good, problems)


@case("symlink/reparse журнала отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        directory = root / "journal"
        directory.mkdir()
        external = root / "external"
        external.mkdir()
        host_journal.append("target", "a", external)
        if os.name == "nt":
            make_reparse(external, directory / "link.jsonl")
        else:
            os.symlink(external / "target.jsonl", directory / "link.jsonl")
        assert verify_refused("link", directory)
        refuse(lambda: host_journal.append("link", "b", directory))


@case("hardlink журнала отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("hard-run", "a", directory)
        os.link(directory / "hard-run.jsonl", directory / "alias.jsonl")
        assert verify_refused("hard-run", directory)
        refuse(lambda: host_journal.append("hard-run", "b", directory))


@case("каталог на месте журнала отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        (directory / "dir-run.jsonl").mkdir()
        assert verify_refused("dir-run", directory)
        refuse(lambda: host_journal.append("dir-run", "a", directory))


@case("symlink/reparse базовый каталог отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        real = root / "real"
        real.mkdir()
        linked = root / "linked"
        make_reparse(real, linked)
        refuse(lambda: host_journal.append("base-run", "a", linked))
        assert not (real / "base-run.jsonl").exists()


@case("hardlinked lock отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        outside = directory / "outside.lock"
        outside.write_bytes(b"x")
        os.link(outside, directory / "locked-run.lock")
        refuse(lambda: host_journal.append("locked-run", "a", directory))
        assert not (directory / "locked-run.jsonl").exists()


@case("4 процесса дописывают 80 записей без гонки")
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
                [sys.executable, "-c", script, "concurrent-run", str(index), str(directory)],
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
        good, problems = host_journal.verify("concurrent-run", directory)
        entries = rows(directory / "concurrent-run.jsonl")
        seqs = [entry["seq"] for entry in entries]
        assert good == 80 and problems == [], (good, problems)
        assert seqs == list(range(1, 81)), seqs
        assert len({entry["event"] for entry in entries}) == 80


@case("fsync завершён до ACK")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        observed: list[int] = []
        original = os.fsync

        def tracked(fd):
            observed.append(os.fstat(fd).st_size)
            original(fd)

        os.fsync = tracked
        try:
            host_journal.append("sync-run", "a", Path(tmp))
        finally:
            os.fsync = original
        assert any(size > 0 for size in observed), observed


@case("сбой fsync не даёт ACK")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        original = os.fsync

        def broken(_fd):
            raise OSError("injected fsync failure")

        os.fsync = broken
        try:
            refuse(lambda: host_journal.append("sync-fail", "a", Path(tmp)))
        finally:
            os.fsync = original


@case("write-loop завершает частичные записи")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "partial.bin"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        original = os.write
        calls: list[int] = []

        def partial(descriptor, data):
            calls.append(len(data))
            return original(descriptor, data[: max(1, len(data) // 2)])

        os.write = partial
        try:
            host_journal._write_all(fd, b"abcdefghijk")
        finally:
            os.write = original
            os.close(fd)
        assert len(calls) >= 2 and path.read_bytes() == b"abcdefghijk", calls


@case("не-str event отвергнут")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for index, event in enumerate((None, 1, {}, [])):
            refuse(lambda event=event, index=index: host_journal.append(
                f"type-run-{index}", event, directory,
            ))


@case("граница event 65536 bytes исполняется")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        limit = host_journal.MAX_EVENT_BYTES
        assert limit == 65536, limit
        host_journal.append("size-run", "x" * limit, directory)
        refuse(lambda: host_journal.append("size-run", "x" * (limit + 1), directory))


@case("events не возвращает доверенный префикс повреждённой цепочки")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        host_journal.append("events-run", "a", directory)
        host_journal.append("events-run", "b", directory)
        path = directory / "events-run.jsonl"
        entries = rows(path)
        entries[0]["event"] = "tampered"
        write_rows(path, entries)
        assert host_journal.events("events-run", directory) == []


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            ok_case = True
            detail = ""
        except Exception as exc:  # noqa: BLE001 — корпус печатает все провалы
            ok_case = False
            detail = f" — {type(exc).__name__}: {exc}"
        failed += 0 if ok_case else 1
        print(f"[{'ok' if ok_case else 'FAIL'}] {name}{detail}")
    print(f"\nhost journal safety: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 and len(CASES) == 34 else 1


if __name__ == "__main__":
    sys.exit(main())
