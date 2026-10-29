"""profiles — выбор модели и режима под класс задачи.

Правило (K149): модель выбирается по классу задачи и замеру, а не по общему впечатлению.
Здесь только чтение профиля; числа и обоснования живут в docs/MODELS.md.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path | None = None) -> dict:
    return json.loads((path or ROOT / "profiles.json").read_text(encoding="utf-8"))


def for_class(class_id: str | None, data: dict | None = None) -> dict:
    """Профиль для класса; неизвестный класс получает профиль по умолчанию."""
    table = data or load()
    base = dict(table.get("default") or {})
    if class_id and class_id in table.get("classes", {}):
        profile = dict(base)
        profile.update(table["classes"][class_id])
        profile["class"] = class_id
        return profile
    base["class"] = class_id or "?"
    base["why"] = "класс не определён: профиль по умолчанию"
    return base
