"""book_ref — добавить книгу и инсайты в справочник как постоянный ориентир.

Справочник (`hs.py refs`) — это то, куда смотрим перед любым новым механизмом.
Книга Кришнамурти и 76 блоков инсайтов должны быть там, чтобы к ним возвращаться.

    python bin/book_ref.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SOURCES = ROOT / "sources.json"

# Записи справочника: книга и инсайты как постоянный ориентир.
ENTRIES = [
    {
        "id": "krishnamurti/awakening-of-intelligence",
        "kind": "local",
        "title": "Krishnamurti — The Awakening of Intelligence",
        "path": "research/book/krishnamurti.md",
        "pages": 409,
        "role": "постоянный ориентир: как ум создаёт себе клетку",
        "why": "обоснование того, почему проверка должна быть вне контекста агента",
    },
    {
        "id": "krishnamurti/insights",
        "kind": "local",
        "title": "Инсайты по книге: 76 блоков, 296 действий",
        "path": "research/book/INSIGHTS.md",
        "role": "применение каждого тезиса к нашему коду, продуктам и процессу",
        "why": "справочник конкретных решений, выведенных из книги",
    },
    {
        "id": "krishnamurti/report",
        "kind": "local",
        "title": "Итоговый разбор книги и 7 предложений",
        "path": "research/book/REPORT.md",
        "role": "сводка: 10 главных тезисов и что они значат для проекта",
        "why": "короткий вход в книгу без чтения 397 страниц",
    },
]


def main() -> int:
    data = {}
    if SOURCES.exists():
        data = json.loads(SOURCES.read_text(encoding="utf-8"))
    items = data.get("sources", data if isinstance(data, list) else [])
    if isinstance(data, dict) and "sources" not in data:
        data["sources"] = items

    added = 0
    for entry in ENTRIES:
        if any(item.get("id") == entry["id"] for item in items):
            continue
        items.append(entry)
        added += 1

    if isinstance(data, dict):
        data["sources"] = items
    else:
        data = {"sources": items}
    SOURCES.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"добавлено в справочник: {added}; всего записей: {len(items)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
