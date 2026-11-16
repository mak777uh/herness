"""binary_version — версия формата журнала, зашитая в бинарник комнаты.

Зачем (F-0087). Смена формата HSJ1 → HSJ2 не завершилась: исходник обновили, а musl-бинарник
комнаты не пересобрали, и комната писала старый формат. Приёмка это поймала — но поздно, уже
в живом прогоне. Урок: «смена формата не завершена, пока не пересобран каждый писатель».

Проверка читает константу MAGIC из `core-rs/src/journal.rs` и ищет ту же строку в бинарнике.
Расхождение означает, что писатель отстал от формата; отсутствие строки — что бинарник собран
не из этого кода или обрезан.

    python bin/binary_version.py --check     # 0 — совпадает, 1 — расхождение, 3 — бинарника нет
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "core-rs" / "src" / "journal.rs"
BINARIES = (
    "core-rs/target/x86_64-unknown-linux-musl/release/hs-core",
    "core-rs/target/release/hs-core",
    "core-rs/target/release/hs-core.exe",
)
MAGIC_IN_SOURCE = re.compile(r'pub\s+const\s+MAGIC:\s*&\[u8;\s*4\]\s*=\s*b"([A-Za-z0-9]{3,8})"')
MAGIC_IN_BINARY = re.compile(rb"HSJ[0-9]")


def source_magic(path: Path = SOURCE) -> str | None:
    if not path.exists():
        return None
    found = MAGIC_IN_SOURCE.search(path.read_text(encoding="utf-8", errors="replace"))
    return found.group(1) if found else None


def find_binary(root: Path = ROOT) -> Path | None:
    for rel in BINARIES:
        candidate = root / rel
        if candidate.exists():
            return candidate
    return None


def binary_magics(path: Path) -> set[str]:
    data = path.read_bytes()[:4_000_000]
    return {chunk.decode("ascii") for chunk in MAGIC_IN_BINARY.findall(data)}


def problems(root: Path = ROOT) -> list[str]:
    """Расхождения формата. Пусто — совпадает; исключение MissingData — проверять нечего."""
    expected = source_magic(root / "core-rs" / "src" / "journal.rs")
    if expected is None:
        return ["core-rs/src/journal.rs: не найдена константа MAGIC — проверить нечем"]
    binary = find_binary(root)
    if binary is None:
        from bin.hs import MissingData

        raise MissingData("нет собранного hs-core: версию формата в бинарнике проверить нечем")
    seen = binary_magics(binary)
    if not seen:
        return [f"{binary.name}: в бинарнике нет строки формата HSJ* — собран не из этого кода?"]
    if expected in seen:
        return []
    return [
        f"{binary.name}: формат {sorted(seen)} против {expected} в исходнике — "
        f"бинарник отстал, комната напишет старый журнал (F-0087)"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="версия формата журнала: исходник против бинарника")
    parser.add_argument("--check", action="store_true", help="проверить и вернуть код")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    expected = source_magic()
    binary = find_binary()
    if binary is None:
        print("бинарь не собран: python bin/rust_tests.py --build")
        return 3
    seen = sorted(binary_magics(binary))
    if expected in seen:
        print(f"формат совпадает: {expected} (исходник и {binary.name})")
        return 0
    print(f"[FAIL] формат {seen} в бинарнике против {expected} в исходнике")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
