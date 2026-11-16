"""Тест сведения карточки в атомы: право, обязанности, запреты, пробелы и противоречия."""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import card_atoms  # noqa: E402

RESULTS: list[tuple[bool, str]] = []
CARD = json.loads((ROOT / "lab" / "tools" / "cards" / "head.json").read_text(encoding="utf-8"))


def check(flag: bool, message: str) -> None:
    RESULTS.append((flag, message))


def main() -> int:
    derived = card_atoms.atoms(CARD)
    relations = [atom["relation"] for atom in derived]
    check(len(derived) >= 4, f"атомов выведено {len(derived)} (минимум 4)")
    check(relations.count("right") == 1, "одно право: чтение внутри комнаты")
    check(relations.count("duty") >= 3, "обязанности: лимит выдачи, отказ, запрет записи")

    capped = [a for a in derived if (a.get("action") or {}).get("verb") == "limit"]
    check(bool(capped) and "8192B" in capped[0]["action"]["quantity"],
          f"лимит выдачи взят из замыкания: {capped[0]['action'] if capped else '—'}")

    denied = [a for a in derived if a.get("negated")]
    check(any((a.get("action") or {}).get("verb") == "write" for a in denied),
          "запись не объявлена — атом-запрет есть")
    check(any((a.get("action") or {}).get("verb") == "net" for a in denied),
          "сеть не объявлена — атом-запрет есть")

    # У нового инструмента правил ещё нет: все атомы — пробелы.
    empty_rules: list[dict] = []
    items = card_atoms.gaps(CARD, empty_rules)
    check(len(items) == len(derived), f"без правил все {len(derived)} атомов — пробелы")

    # Правило появилось — пробелов меньше.
    rules = [{"id": "head-allow", "tool": "head", "action": "read", "effect": "allow"}]
    check(len(card_atoms.gaps(CARD, rules)) == len(derived) - 1, "правило на чтение закрывает один пробел")

    # Противоречие: политика разрешает запись, а карточка её запрещает.
    wrong = [{"id": "head-write", "tool": "head", "action": "write", "effect": "allow"}]
    issues = card_atoms.conflicts(CARD, wrong)
    check(any("S4_POLICY_CONFLICT" in issue for issue in issues),
          f"разрешение записи при запрете в карточке поймано: {issues}")
    check(card_atoms.conflicts(CARD, rules) == [], "правило на чтение противоречий не даёт")

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
