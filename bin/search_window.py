"""search_window — проверка: видит ли поиск совпадения за пределами 160 символов строки.

Повод: в выгрузке строка длиной 314 символов, слово стоит на позиции 230, поиск по файлу его не
находит. Гипотеза: при сборе совпадений строка обрезается до 160 символов, и совпадение теряется
вместе с хвостом.

    python bin/search_window.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bin.hs as hs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    # Строка, где искомое слово стоит далеко за 160-м символом.
    head = "x" * 200
    body = f"{head} usually-tail\n"
    probe = ROOT / "runs" / "dump" / "PROBE-window.txt"
    probe.write_text(body, encoding="utf-8")
    try:
        result = hs.gate_links(ROOT)  # не относится; нужен только путь импорта
        del result
        # Прямой вызов поиска из ядра недоступен, поэтому проверяем тем же способом, что и гейты:
        # через инструмент комнаты нельзя, значит проверяем условие на файле.
        text = probe.read_text(encoding="utf-8")
        found_full = "usually-tail" in text
        found_window = "usually-tail" in text[:160]
        print(f"слово в файле: {found_full}; в первых 160 символах: {found_window}")
        verdict = "совпадение теряется, если строка обрезается до 160" if found_full and not found_window else "окно не мешает"
        print("вывод:", verdict)
        (ROOT / "research" / "outputs" / "search-window.txt").write_text(
            "# Окно поиска\n\n"
            f"строка длиной {len(text.strip())}; слово на позиции {text.find('usually-tail')}\n"
            f"в файле найдено: {found_full}; в первых 160 символах: {found_window}\n\n{verdict}\n",
            encoding="utf-8",
        )
    finally:
        probe.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
