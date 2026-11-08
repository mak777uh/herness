"""pdf_probe — что внутри PDF: страниц, текстовый слой или скан."""

from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader

PDF = Path("C:/Users/Admin/Downloads/Krishnamurti - The Awakening of Intelligence.pdf")


def main() -> int:
    reader = PdfReader(str(PDF))
    total = len(reader.pages)
    print(f"файл: {PDF.name}")
    print(f"размер: {PDF.stat().st_size / (1024 * 1024):.2f} МБ")
    print(f"страниц: {total}")

    # Проверяем текстовый слой на первых трёх и трёх случайных страницах.
    checks = [0, 1, 2, total // 2, total - 2, total - 1]
    text_pages = 0
    for index in checks:
        if 0 <= index < total:
            text = reader.pages[index].extract_text() or ""
            has = len(text.strip()) > 50
            text_pages += 1 if has else 0
            print(f"  стр. {index + 1}: символов {len(text.strip())}, текст {'есть' if has else 'НЕТ'}")

    print(f"\nстраниц с текстом из проверенных: {text_pages} из {len(checks)}")
    if text_pages == 0:
        print("ВЕРДИКТ: это скан без текстового слоя — нужен OCR")
    else:
        print("ВЕРДИКТ: текстовый слой есть, можно извлекать")

    # Метаданные.
    meta = reader.metadata or {}
    for key in ("/Title", "/Author", "/Creator", "/Producer"):
        if key in meta:
            print(f"{key}: {meta[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
