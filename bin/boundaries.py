"""Границы автовыбора: где класс определяется уверенно, а где нет."""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(r"C:\111\herness")))

from core import reply, routing

TASKS = [
    "посчитай, сколько файлов в папке bin",
    "проверь, не врёт ли README про число репозиториев",
    "опубликуй изменения",
    "объясни, что такое граница",
    "найди в сети актуальный курс",
    "сравни два документа",
    "поправь опечатку в README",
    "запусти тесты",
    "что ты решил вчера",
    "найди расхождения между README и кодом",
]

print(f"{'задача':<46} {'класс':<7} {'зазор':<6} {'тип':<9} альтернативы")
for task in TASKS:
    routes = routing.route(task, top=2)
    decision = reply.decide(task)
    top = routes[0]["class"] if routes else "-"
    gap = round(routes[0]["score"] - routes[1]["score"], 3) if len(routes) > 1 else None
    print(f"{task[:45]:<46} {top:<7} {str(gap):<6} {decision['type']:<9} {','.join(decision.get('alternatives', []))}")
