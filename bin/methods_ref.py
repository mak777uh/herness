"""methods_ref — добавить каталог методов верификации в справочник.

Каталог — постоянный ориентир: перед выбором метода смотрим сюда, а не изобретаем.

    python bin/methods_ref.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources.json"

ENTRIES = [
    {
        "id": "herness/verification-methods",
        "kind": "local",
        "title": "Каталог методов формальной верификации для харнесса",
        "path": "docs/VERIFICATION-METHODS.md",
        "role": "что применяем, что не берём и почему",
        "why": "перед выбором метода смотреть сюда, а не изобретать",
    },
]


def main() -> int:
    data = json.loads(SOURCES.read_text(encoding="utf-8")) if SOURCES.exists() else {"sources": []}
    items = data.get("sources", [])
    added = 0
    for entry in ENTRIES:
        if any(item.get("id") == entry["id"] for item in items):
            continue
        items.append(entry)
        added += 1
    data["sources"] = items
    SOURCES.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"добавлено: {added}; всего записей: {len(items)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
