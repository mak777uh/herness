"""Тест версии формата в бинарнике: расхождение ловится, отсутствие бинарника — отказ."""

from __future__ import annotations

import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import binary_version  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, message: str) -> None:
    RESULTS.append((ok, message))


def make_repo(tmp: pathlib.Path, magic: str, binary_magic: str | None) -> pathlib.Path:
    (tmp / "core-rs" / "src").mkdir(parents=True)
    (tmp / "core-rs" / "src" / "journal.rs").write_text(
        f'pub const MAGIC: &[u8; 4] = b"{magic}";\n', encoding="utf-8"
    )
    if binary_magic is not None:
        target = tmp / "core-rs" / "target" / "x86_64-unknown-linux-musl" / "release"
        target.mkdir(parents=True)
        (target / "hs-core").write_bytes(b"\x7fELF" + binary_magic.encode() + b"\x00" * 64)
    return tmp


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        # 1. Совпадение: исходник и бинарник — HSJ2.
        base = make_repo(pathlib.Path(tmp) / "same", "HSJ2", "HSJ2")
        check(binary_version.problems(base) == [], "совпадение формата не даёт проблем")

        # 2. Бинарник отстал: в исходнике HSJ3, в бинарнике HSJ2 (класс F-0087).
        lag = make_repo(pathlib.Path(tmp) / "lag", "HSJ3", "HSJ2")
        issues = binary_version.problems(lag)
        check(len(issues) == 1 and "HSJ2" in issues[0] and "HSJ3" in issues[0],
              f"отставший бинарник назван с обеими версиями (получено {issues})")

        # 3. В бинарнике нет строки формата — собран не из этого кода.
        empty = make_repo(pathlib.Path(tmp) / "empty", "HSJ2", "AAAA")
        issues = binary_version.problems(empty)
        check(len(issues) == 1 and "нет строки формата" in issues[0],
              "бинарник без маркера назван отдельно")

        # 4. Бинарника нет — отказ с MissingData, а не «всё хорошо».
        missing = make_repo(pathlib.Path(tmp) / "missing", "HSJ2", None)
        try:
            binary_version.problems(missing)
            check(False, "без бинарника должно быть MissingData")
        except Exception as exc:  # noqa: BLE001
            check(type(exc).__name__ == "MissingData",
                  f"без бинарника — MissingData (получено {type(exc).__name__})")

    for ok, message in RESULTS:
        print(f"[{'ok' if ok else 'FAIL'}] {message}")
    failed = sum(1 for ok, _ in RESULTS if not ok)
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
