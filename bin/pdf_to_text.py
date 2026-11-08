"""pdf_to_text — извлечь PDF в удобный формат: markdown по страницам.

Формат: каждая страница — отдельная секция с номером, чтобы можно было ссылаться
на место («стр. 205»). Без этого цитаты не проверить.

    python bin/pdf_to_text.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pypdf import PdfReader

PDF = Path("C:/Users/Admin/Downloads/Krishnamurti - The Awakening of Intelligence.pdf")
OUT = Path("C:/111/herness/research/book/krishnamurti.md")
PAGES_DIR = Path("C:/111/herness/research/book/pages")


def clean(text: str) -> str:
    """Убрать артефакты извлечения: лишние пробелы, переносы по слогам."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Перенос слова через дефис в конце строки.
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Склеить строки внутри абзаца: одиночный перенос без пустой строки.
    text = re.sub(r"(?<![.!?:;])\n(?=[a-zа-яё])", " ", text)
    # Схлопнуть больше двух пустых строк.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main() -> int:
    reader = PdfReader(str(PDF))
    total = len(reader.pages)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    lines = ["# The Awakening of Intelligence — Krishnamurti", "",
             f"Источник: `{PDF.name}`, страниц {total}.", "",
             "Формат: каждая страница отдельной секцией, чтобы цитаты были проверяемы.", ""]

    empty = []
    for index in range(total):
        raw = reader.pages[index].extract_text() or ""
        text = clean(raw)
        number = index + 1
        if len(text) < 40:
            empty.append(number)
        (PAGES_DIR / f"p{number:03d}.md").write_text(text + "\n", encoding="utf-8")
        lines.append(f"## Стр. {number}")
        lines.append("")
        lines.append(text if text else "_(пустая страница)_")
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")

    print(f"страниц: {total}")
    print(f"пустых или почти пустых: {len(empty)}")
    if empty:
        print(f"  номера: {empty[:30]}{'...' if len(empty) > 30 else ''}")
    print(f"записано: {OUT}")
    print(f"страницы по отдельности: {PAGES_DIR}")
    print(f"размер markdown: {OUT.stat().st_size / 1024:.0f} КБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
