"""Генерирует capabilities.json из кода: инструменты описывают себя сами.

Источник истины — метаданные классов в core/tools.py и внешние инструменты (fetch, browser).
Файл capabilities.json — производная; гейт «способности» падает, если он разошёлся с кодом.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.tools import GrepTool, ListTool, ReadTool, ShellTool  # noqa: E402

MODALITIES = {
    "requires": "должно быть сделано",
    "permits": "разрешено, но не обязательно",
    "prohibits": "запрещено",
    "asks": "запрос информации",
    "periodic": "должно повторяться: сторож и проверялка",
}

EXTERNAL = [
    {"id": "fetch", "actions": ["проверить", "получить", "скачать", "открыть"],
     "objects": ["url", "страница", "api", "источник"], "effects": ["read", "net"]},
    {"id": "browser", "actions": ["найти", "искать", "поиск"],
     "objects": ["выдача", "поиск", "результат"], "effects": ["read", "net"]},
    {"id": "schedule", "actions": ["следить", "регулярно", "периодически", "наблюдать"],
     "objects": ["состояние", "изменения", "событие"], "effects": ["periodic"]},
]

WORKFLOW = [
    {"id": "WF-VERIFY", "actions": ["проверить"], "objects": ["утверждение", "факт"],
     "produces": "утверждение с ожиданием"},
    {"id": "WF-RECORD", "actions": ["добавить", "записать"], "objects": ["реестр", "запись"],
     "produces": "запись в реестре"},
    {"id": "WF-DECIDE", "actions": ["решить", "выбрать"], "objects": ["вариант", "решение"],
     "produces": "решение с причиной"},
    {"id": "WF-WATCH", "actions": ["следить", "проверять"], "objects": ["изменения", "состояние"],
     "produces": "сторож, который будит проверялку"},
]


def build() -> dict:
    tools = []
    for cls in (ShellTool, ReadTool, GrepTool, ListTool):
        tools.append({"id": cls.name, "actions": list(cls.meta["actions"]),
                      "objects": list(cls.meta["objects"]), "effects": list(cls.meta["effects"])})
    tools.extend(EXTERNAL)
    return {
        "note": ("Способности инструментов и шагов воркфлоу. Файл генерируется: "
                 "bin/gen_capabilities.py. Источник истины — meta в core/tools.py и EXTERNAL в генераторе."),
        "modalities": MODALITIES,
        "tools": tools,
        "workflow": WORKFLOW,
    }


def main() -> int:
    data = build()
    target = ROOT / "capabilities.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"записано {target}: инструментов {len(data['tools'])}, шагов воркфлоу {len(data['workflow'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
