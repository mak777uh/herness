"""plan — раскладка запроса на типы задач и выбор уровня вмешательства.

Слабое место здесь — распознавание. Поэтому правило: не уверен — не угадывай.
Неизвестный фрагмент получает уровень L1 и пометку «нужна проба», а не случайный тип.
"""

from __future__ import annotations

import re

# тип -> (название, уровень, признаки)
TYPES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "T-0001": ("разведка", "L1", ("найди", "поищи", "проверь как", "исследуй", "сравни", "что известно",
                                 "разведка", "источник")),
    "T-0002": ("аудит утверждений", "L2", ("аудит", "расхожден", "где врёт", "где врёт", "обещает",
                                           "надёжн", "claim", "утвержден", "ревью")),
    "T-0003": ("локальная правка", "L1", ("переименуй", "поправь", "исправь", "замени", "убери",
                                          "добавь", "отредактируй")),
    "T-0004": ("сборка и тесты", "L1", ("собери", "сборк", "тест", "lake", "forge", "cargo", "npm",
                                        "прогони тесты")),
    "T-0005": ("публикация", "L2", ("опублику", "запушь", "push", "коммит", "выложи", "оплати",
                                    "переведи")),
    "T-0006": ("анализ журналов", "L1", ("сколько раз", "как часто", "статистик", "журнал", "лог",
                                         "метрик", "посчитай")),
    "T-0007": ("уточнение", "L0", ("как лучше", "что думаешь", "посоветуй", "объясни", "уточни")),
}

LEVEL_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}


def classify(text: str) -> list[dict]:
    low = text.lower()
    hits = []
    for tid, (name, level, signals) in TYPES.items():
        matched = [s for s in signals if s in low]
        if matched:
            hits.append({"type": tid, "name": name, "level": level, "signals": matched})
    return hits


def plan(text: str) -> dict:
    hits = classify(text)
    if not hits:
        return {"request": text, "fragments": [], "level": "L1",
                "unknown": True, "note": "тип не распознан: L1 и проба, не догадка"}
    level = max((h["level"] for h in hits), key=lambda l: LEVEL_ORDER[l])
    # необратимые типы поднимают уровень независимо от свидетельства
    if any(h["type"] == "T-0005" for h in hits):
        level = "L2"
    return {"request": text, "fragments": hits, "level": level, "unknown": False,
            "note": "минимально достаточный уровень по типу"}


def summarize(texts: list[str]) -> dict:
    total = len(texts)
    unknown = 0
    levels: dict[str, int] = {}
    types: dict[str, int] = {}
    for text in texts:
        result = plan(text)
        if result["unknown"]:
            unknown += 1
        levels[result["level"]] = levels.get(result["level"], 0) + 1
        for frag in result["fragments"]:
            types[frag["type"]] = types.get(frag["type"], 0) + 1
    return {"total": total, "unknown": unknown,
            "unknown_pct": round(100 * unknown / total, 1) if total else 0,
            "levels": levels, "types": types}


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def compare(texts: list[str]) -> dict:
    """Насколько правила отличаются от «всегда L1»: верхняя граница их пользы."""
    total = len(texts)
    same = 0
    lower = 0
    higher = 0
    unknown = 0
    for text in texts:
        result = plan(text)
        if result["unknown"]:
            unknown += 1
            continue
        level = result["level"]
        if level == "L1":
            same += 1
        elif LEVEL_ORDER[level] < 1:
            lower += 1
        else:
            higher += 1
    return {
        "total": total,
        "rules_unknown": unknown,
        "rules_l1": same,
        "rules_lower_than_l1": lower,
        "rules_higher_than_l1": higher,
        "differ_pct": round(100 * (lower + higher) / total, 1) if total else 0,
    }
