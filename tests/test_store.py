"""Тесты store: атомарная запись не оставляет полу-файлов и не врёт про durable."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import store  # noqa: E402

CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


@case("запись создаёт файл с точным содержимым и LF")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "state.json"
        store.write_text(target, '{"a": 1}\n')
        raw = target.read_bytes()
        assert raw == b'{"a": 1}\n', raw
        assert b"\r\n" not in raw


@case("временный файл не остаётся после успеха")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "state.json"
        store.write_text(target, "x\n")
        leftovers = list(Path(tmp).glob(".state.json.*.tmp"))
        assert leftovers == [], leftovers


@case("при сбое замены старый файл цел, временный убран")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "state.json"
        store.write_text(target, "старое\n")

        def boom(*_args, **_kwargs):
            raise OSError("замена не удалась")

        original = store.os.replace
        store.os.replace = boom
        try:
            try:
                store.write_text(target, "новое\n")
            except OSError:
                pass
            else:
                raise AssertionError("сбой замены должен был проброситься")
        finally:
            store.os.replace = original

        assert target.read_text(encoding="utf-8") == "старое\n"
        assert list(Path(tmp).glob(".state.json.*.tmp")) == []


@case("JSON пишется с переводом строки и читается обратно")
def _():
    import json

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "q.json"
        store.write_json(target, {"total": 1, "имя": "тест"})
        text = target.read_text(encoding="utf-8")
        assert text.endswith("\n") and not text.endswith("\n\n"), repr(text[-4:])
        assert json.loads(text) == {"total": 1, "имя": "тест"}


@case("отсутствующий каталог создаётся, а не роняет запись")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "нет" / "такого" / "x.txt"
        store.write_text(target, "ok\n")
        assert target.read_text(encoding="utf-8") == "ok\n"


@case("durable_dir честно говорит про платформу")
def _():
    assert store.durable_dir() == (store.os.name != "nt")


@case("fsync каталога не падает на существующем каталоге")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        store._fsync_dir(Path(tmp))


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            ok = True
        except AssertionError:
            ok = False
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {name}")
    print(f"\nstore: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
