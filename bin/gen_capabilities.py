"""Генерирует capabilities.json из кода: инструменты описывают себя сами.

Источник истины — метаданные классов в core/tools.py и внешние инструменты (fetch, browser).
Файл capabilities.json — производная; гейт «способности» падает, если он разошёлся с кодом.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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


def build(root: Path = ROOT, tools_module=None) -> dict:
    if tools_module is None:
        path = (root / "core" / "tools.py").resolve()
        data = path.read_bytes()
        token = hashlib.sha256(str(path).encode("utf-8") + b"\0" + data).hexdigest()
        name = "_herness_tools_" + token
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"не удалось загрузить {path}")
        tools_module = importlib.util.module_from_spec(spec)
        sys.modules[name] = tools_module
        previous = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            # Никакого get_code/exec_module: stale timestamp-valid .pyc не должен
            # подменять source bytes выбранного root (E-0087 review F3).
            code = compile(data, str(path), "exec", dont_inherit=True)
            exec(code, tools_module.__dict__)
        finally:
            sys.dont_write_bytecode = previous

    tools = []
    for cls in (tools_module.ShellTool, tools_module.ReadTool,
                tools_module.GrepTool, tools_module.ListTool):
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


def main(root: Path = ROOT) -> int:
    data = build(root)
    target = root / "capabilities.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"записано {target}: инструментов {len(data['tools'])}, шагов воркфлоу {len(data['workflow'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
