"""Тест карточки инструмента: замыкание, отказы, примеры, рендер."""

from __future__ import annotations

import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import tool_card  # noqa: E402

RESULTS: list[tuple[bool, str]] = []
CARD = json.loads((ROOT / "lab" / "tools" / "cards" / "head.json").read_text(encoding="utf-8"))


def check(flag: bool, message: str) -> None:
    RESULTS.append((flag, message))


def broken(mutator) -> dict:
    card = copy.deepcopy(CARD)
    mutator(card)
    return card


def main() -> int:
    check(tool_card.validate(CARD) == [], "валидная карточка head проходит")

    wide = broken(lambda c: c["closure"]["fs"].__setitem__("read", ["/etc/**"]))
    issues = tool_card.validate(wide)
    check(any("за пределы комнаты" in issue for issue in issues), f"чтение вне /mnt отвергнуто: {issues}")

    net = broken(lambda c: c["closure"].__setitem__("net", ["https://example.com"]))
    issues = tool_card.validate(net)
    check(any("сеть" in issue for issue in issues), f"сеть отвергнута: {issues}")

    no_refusal = broken(lambda c: c.__setitem__(
        "examples", [e for e in c["examples"] if "отказ" not in e["expect"].lower()]))
    issues = tool_card.validate(no_refusal)
    check(any("нет примера с отказом" in issue for issue in issues), f"пример без отказа отвергнут: {issues}")

    unknown = broken(lambda c: c.__setitem__("refusals", ["NOPE_CODE"]))
    issues = tool_card.validate(unknown)
    check(any("нет в словаре" in issue for issue in issues), f"неизвестный код отвергнут: {issues}")

    banned = broken(lambda c: c.__setitem__("purpose", "быстро вернуть первые строки файла."))
    issues = tool_card.validate(banned)
    check(any("непроверяемое слово" in issue for issue in issues), f"«быстро» отвергнуто: {issues}")

    bad_write = broken(lambda c: c["closure"]["fs"].__setitem__("write", ["/mnt/**"]))
    issues = tool_card.validate(bad_write)
    check(any("запись только внутрь" in issue for issue in issues), f"запись вне /mnt/work отвергнута: {issues}")

    text = tool_card.render(CARD)
    check(0 < len(text) <= 1600, f"карточка для модели короткая: {len(text)} символов (≈{len(text)//4} токенов)")
    check("S6_CLOSURE_BREACH" in text and "пример" in text, "в рендере есть отказы и примеры")

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
