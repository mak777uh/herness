"""book_index — карта книги: где какая часть и глава.

Нужна, чтобы анализ ссылался на место, а не на «где-то в книге».

    python bin/book_index.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PAGES = Path("C:/111/herness/research/book/pages")
OUT = Path("C:/111/herness/research/book/INDEX.md")

# Заголовки, которые ищем в тексте: части и главы.
PART = re.compile(r"^\s*(PART\s+[IVX]+)\s*$", re.MULTILINE)
CHAPTER = re.compile(r"^\s*(\d{1,2})\s+([A-Z][A-Z\s,'’\-—:]{6,})\s*$", re.MULTILINE)


def main() -> int:
    files = sorted(PAGES.glob("p*.md"))
    lines = ["# Карта книги", "", "| страница | что |", "|---|---|"]
    found = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        number = int(path.stem[1:])
        marks = []
        for match in PART.finditer(text):
            marks.append(match.group(1))
        for match in CHAPTER.finditer(text):
            title = match.group(2).strip()
            if len(title) > 8 and not title.startswith("THE "):
                marks.append(f"{match.group(1)}. {title[:50]}")
            elif len(title) > 8:
                marks.append(f"{match.group(1)}. {title[:50]}")
        if marks:
            found += 1
            lines.append(f"| {number} | {'; '.join(marks[:3])} |")
    lines += ["", f"страниц с заголовками: {found} из {len(files)}"]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:40]))
    print(f"\n... всего строк: {len(lines)}")
    print(f"записано: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
