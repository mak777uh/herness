"""book_plan — план чтения книги: блоки по 5 страниц, без потерь.

Проблема, которая случилась дважды: `write` заменяет файл целиком, и вставка только нового
блока стирает предыдущие. Потеряно 18 блоков, потом блок 1.

Правило, которое теперь соблюдается:
  1. Блок пишется в отдельный файл `_block.md`.
  2. `book_append.py --file _block.md` дописывает его в конец.
  3. Проверка: число блоков выросло ровно на число блоков в файле.
  4. `_block.md` удаляется.
  5. Раз в 10 блоков — проверка целостности: все номера от 1 до N присутствуют.

    python bin/book_plan.py --plan       # показать план
    python bin/book_plan.py --check      # проверить целостность файла
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TARGET = Path("C:/111/herness/research/book/INSIGHTS.md")

# Границы блоков по 5 страниц: от 13 до 409.
START = 13
END = 409
STEP = 5


def blocks() -> list[tuple[int, int, int]]:
    """(номер блока, первая страница, последняя страница)."""
    result = []
    number = 1
    page = START
    while page <= END:
        last = min(page + STEP - 1, END)
        result.append((number, page, last))
        number += 1
        page = last + 1
    return result


def check() -> int:
    if not TARGET.exists():
        print("файла нет")
        return 2
    text = TARGET.read_text(encoding="utf-8")
    found = [int(m.group(1)) for m in re.finditer(r"^## Блок (\d+)\.", text, re.MULTILINE)]
    if not found:
        print("блоков нет")
        return 2
    expected = list(range(1, max(found) + 1))
    missing = [n for n in expected if n not in found]
    duplicates = [n for n in set(found) if found.count(n) > 1]
    print(f"блоков: {len(found)}")
    print(f"последний: {max(found)}")
    if missing:
        print(f"ПРОПУЩЕНЫ: {missing}")
    if duplicates:
        print(f"ДУБЛИ: {sorted(duplicates)}")
    print(f"размер: {TARGET.stat().st_size} байт")
    return 0 if not missing and not duplicates else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="план чтения книги")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.check:
        return check()

    if args.plan:
        plan = blocks()
        print(f"страниц: {END - START + 1}, блоков: {len(plan)}")
        print()
        for number, first, last in plan:
            print(f"  блок {number:2d}: стр. {first}–{last}")
        return 0

    print("укажи --plan или --check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
