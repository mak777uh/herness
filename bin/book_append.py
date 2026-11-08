"""book_append — дописать блок инсайтов в файл, не перезаписывая его.

Проблема, которая уже случилась: `write` заменяет файл целиком, и вставка только нового
блока стирает все предыдущие. Потеряно 18 блоков.

Правило: файл только дописывается. Скрипт проверяет, что число блоков выросло.

    python bin/book_append.py --check          # сколько блоков сейчас
    python bin/book_append.py --file <путь>    # дописать блок из файла
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TARGET = Path("C:/111/herness/research/book/INSIGHTS.md")


def count_blocks(text: str) -> int:
    return len(re.findall(r"^## Блок ", text, re.MULTILINE))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="дописать блок инсайтов")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--file", metavar="ПУТЬ")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    before = count_blocks(TARGET.read_text(encoding="utf-8")) if TARGET.exists() else 0

    if args.check:
        print(f"блоков: {before}")
        print(f"размер: {TARGET.stat().st_size if TARGET.exists() else 0} байт")
        return 0

    if args.file:
        source = Path(args.file)
        if not source.exists():
            print(f"нет файла: {source}", file=sys.stderr)
            return 2
        block = source.read_text(encoding="utf-8").strip()
        if not block.startswith("## Блок"):
            print("файл не начинается с '## Блок'", file=sys.stderr)
            return 2
        with TARGET.open("a", encoding="utf-8") as handle:
            handle.write("\n\n" + block + "\n")
        after = count_blocks(TARGET.read_text(encoding="utf-8"))
        print(f"блоков: {before} → {after}")
        if after != before + 1:
            print("ОШИБКА: число блоков не выросло на один", file=sys.stderr)
            return 1
        return 0

    print("укажи --check или --file", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
