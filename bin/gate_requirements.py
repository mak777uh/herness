"""gate_requirements — у каждого принятого требования есть инвариант или явное «не проверяется».

Почему это гейт, а не документ: требование без инварианта — пожелание. Из ресёрча
(контрактное программирование, применённое к требованиям): «требование X должно сделать
в коде доказательство Z, что оно исполнено».

    python bin/gate_requirements.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "REQUIREMENTS.md"

# Обязательные поля записи.
FIELDS = ("Требование", "Источник", "Инвариант", "Статус")


def parse(text: str) -> list[dict]:
    """Разобрать записи R-NNNN."""
    entries = []
    current = None
    for line in text.splitlines():
        match = re.match(r"^## (R-\d{4}) · (.+)$", line)
        if match:
            if current:
                entries.append(current)
            current = {"id": match.group(1), "anchor": match.group(2).strip()}
            continue
        if current is None:
            continue
        field = re.match(r"^\*\*(.+?)\.\*\*\s*(.*)$", line)
        if field:
            current[field.group(1)] = field.group(2).strip()
            continue
        # Продолжение поля на следующей строке.
        if line.strip() and current:
            last = list(current.keys())[-1]
            if last in FIELDS:
                current[last] = (current[last] + " " + line.strip()).strip()
    if current:
        entries.append(current)
    return entries


def check() -> list[str]:
    if not REQUIREMENTS.exists():
        return ["нет REQUIREMENTS.md"]
    entries = parse(REQUIREMENTS.read_text(encoding="utf-8"))
    if not entries:
        return ["в REQUIREMENTS.md нет записей R-NNNN"]
    problems = []
    for entry in entries:
        rid = entry["id"]
        if not entry.get("anchor"):
            problems.append(f"{rid}: нет якоря")
        for field in FIELDS:
            if not entry.get(field):
                problems.append(f"{rid}: нет поля «{field}»")
        status = entry.get("Статус", "")
        invariant = entry.get("Инвариант", "")
        # Принятое требование обязано иметь инвариант или явное «не проверяется».
        if status.startswith("принято") and not invariant:
            problems.append(f"{rid}: принято, но инварианта нет")
        if invariant and invariant.startswith("не проверяется") and "—" not in invariant:
            problems.append(f"{rid}: «не проверяется» без причины")
    return problems


def main() -> int:
    problems = check()
    if problems:
        print(f"[FAIL] требования: {len(problems)} проблем")
        for problem in problems[:20]:
            print(f"   - {problem}")
        return 1
    entries = parse(REQUIREMENTS.read_text(encoding="utf-8"))
    print(f"[ok] требования: {len(entries)} записей, у каждой якорь и инвариант")
    return 0


if __name__ == "__main__":
    sys.exit(main())
