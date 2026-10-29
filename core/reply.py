"""reply — какой тип ответа нужен задаче.

Не «какой инструмент», а «что вообще делать»: исполнять, предложить варианты, уточнить, искать
вовне, спросить собеседника или отказать. Основание: и я, и собеседник можем заблуждаться,
поэтому при неопределённости правильный ход — вопрос, а не догадка.
"""

from __future__ import annotations

import re

from . import routing

TYPES = {
    "EXECUTE": "исполнять: задача понятна, инструменты известны",
    "OPTIONS": "предложить варианты: классов несколько, они близки",
    "CLARIFY": "уточнить: в задаче есть неоднозначный термин",
    "SEARCH": "искать вовне: нужен факт, которого у меня нет",
    "ASK_PEER": "спросить собеседника: факт есть только у него",
    "REFUSE": "отказать: действие необратимо и нет явного подтверждения",
}

# признаки неоднозначности: слова, которые каждый понимает по-своему
AMBIGUOUS = re.compile(r"(?i)\b(красив|оптимальн|быстр|лучше|удобн|правильн|нормальн|понятн)\w*")
# признаки внешнего факта: то, что нельзя знать из памяти
EXTERNAL = re.compile(r"(?i)\b(сегодня|сейчас|курс|цена|погода|новост|последн|актуальн|скачай|проверь в сети)\w*")
# необратимые действия
IRREVERSIBLE = re.compile(r"(?i)\b(опублику|запуш|оплати|переведи деньг|удали|отправь)\w*")
# то, что знает только собеседник
PEER_ONLY = re.compile(r"(?i)\b(что ты решил|как ты хотел|тво[её] мнение|что имел в виду|уточни у)\w*")

GAP_MIN = 0.15   # если два класса ближе этого зазора — они неразличимы


def decide(text: str) -> dict:
    routes = routing.route(text, top=3)
    top_score = routes[0]["score"] if routes else 0.0
    gap = (routes[0]["score"] - routes[1]["score"]) if len(routes) > 1 else 1.0

    reasons: list[str] = []
    alternatives: list[str] = []

    if PEER_ONLY.search(text):
        alternatives.append("CLARIFY")
        return {"type": "ASK_PEER", "score": top_score,
                "reason": "факт известен только собеседнику", "alternatives": alternatives}
    if IRREVERSIBLE.search(text) and "да" not in text.lower():
        alternatives.append("CLARIFY")
        return {"type": "REFUSE", "score": top_score,
                "reason": "действие необратимо, нужно явное подтверждение", "alternatives": alternatives}
    if AMBIGUOUS.search(text):
        alternatives.append("OPTIONS")
        return {"type": "CLARIFY", "score": top_score,
                "reason": "в задаче есть неоднозначный термин", "alternatives": alternatives}
    if EXTERNAL.search(text) and top_score < 0.3:
        alternatives.append("CLARIFY")
        return {"type": "SEARCH", "score": top_score,
                "reason": "нужен факт извне, класс задачи при этом не определён", "alternatives": alternatives}
    if len(routes) > 1 and gap < GAP_MIN:
        alternatives.append("CLARIFY")
        reasons.append(f"два класса близки: {routes[0]['class']} и {routes[1]['class']} (зазор {gap:.3f})")
        return {"type": "OPTIONS", "score": top_score,
                "reason": "; ".join(reasons), "alternatives": alternatives}

    return {"type": "EXECUTE", "score": top_score,
            "reason": f"класс {routes[0]['class']} определён, зазор {gap:.3f}" if routes else "класс не найден",
            "alternatives": ["CLARIFY"] if not routes else []}
