"""Почему search не находит C-0295 в CLAIMS.md.

Гипотеза: collect_files идёт по алфавиту и упирается в MAX_FILES=500 раньше,
чем доходит до CLAIMS.md в корне. В образе 346 файлов, но обход начинается
с каталогов (docs/, failures/, runs/), и до файлов корня может не дойти.

Проверяем: считаем, на каком месте по алфавитному обходу стоит CLAIMS.md.

    python work/why_search_misses.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(r"C:\111\herness")
MAX_FILES = 500
MAX_DEPTH = 8


def wsl(script: str) -> str:
    result = subprocess.run(["wsl", "-e", "bash", "-lc", script],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
    return (result.stdout or "") + (result.stderr or "")


def main() -> int:
    # Обход как в collect_files: сортировка по имени на каждом уровне, вглубь.
    script = (
        "cd /mnt/c/111/herness && mkdir -p /tmp/r3 && mount -o loop share.img /tmp/r3 && "
        "cd /tmp/r3 && find . -type f | sed 's|^\\./||' | sort | nl | grep -n 'CLAIMS.md' ; "
        "echo '---' ; find . -type f | wc -l ; cd / && umount /tmp/r3"
    )
    out = wsl(script)
    print(out.strip()[-600:])

    # Сколько файлов идёт до CLAIMS.md в отсортированном списке.
    script2 = (
        "cd /mnt/c/111/herness && mkdir -p /tmp/r4 && mount -o loop share.img /tmp/r4 && "
        "cd /tmp/r4 && find . -type f | sed 's|^\\./||' | sort > /tmp/all.txt && "
        "grep -n '^CLAIMS.md$' /tmp/all.txt ; "
        "echo 'всего:' ; wc -l < /tmp/all.txt ; cd / && umount /tmp/r4"
    )
    print(wsl(script2).strip()[-300:])
    print(f"\nMAX_FILES = {MAX_FILES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
