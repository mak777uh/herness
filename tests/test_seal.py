"""Тесты печати: канонизация, независимость от переводов строк и хвоста, fail-closed."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin.seal import canonical, digest, seal, verify  # noqa: E402

CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


@case("CRLF и LF дают один и тот же хеш")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        first = Path(tmp) / "a.md"
        second = Path(tmp) / "b.md"
        first.write_bytes(b"# \xd0\x9c\xd0\xb5\xd1\x82\xd0\xbe\xd0\xb4\r\n\xd1\x81\xd1\x82\xd1\x80\xd0\xbe\xd0\xba\xd0\xb0\r\n")
        second.write_bytes(b"# \xd0\x9c\xd0\xb5\xd1\x82\xd0\xbe\xd0\xb4\n\xd1\x81\xd1\x82\xd1\x80\xd0\xbe\xd0\xba\xd0\xb0\n")
        assert digest(first) == digest(second)


@case("хвостовые пробелы не влияют")
def _():
    assert canonical("строка   \n\n") == canonical("строка")


@case("содержимое после маркера не входит в хеш")
def _():
    assert canonical("тело\n## Seal\nпечать 1") == canonical("тело\n## Seal\nсовсем другое")


@case("изменение до маркера меняет хеш")
def _():
    assert canonical("тело A\n## Seal") != canonical("тело B\n## Seal")


@case("проверка без печати падает (fail-closed)")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "x.md"
        target.write_text("тело", encoding="utf-8")
        ok, _ = verify(target)
        assert not ok


@case("после печати сходится, после правки — нет")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "y.md"
        target.write_text("тело\n", encoding="utf-8")
        seal(target)
        ok, _ = verify(target)
        assert ok
        target.write_text("другое тело\n", encoding="utf-8")
        ok, _ = verify(target)
        assert not ok


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
    print(f"\nпечати: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
