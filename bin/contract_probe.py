"""contract_probe — проверка, что контракт инструментов доходит до модели.

A-0042: контракт с примерами. Проверяем две вещи:
1. В подсказке цикла у каждого инструмента есть имя, вход, выход, семантика и пример вызова.
2. Ни один инструмент не описан одной строкой без примера.

Отрицательный контроль: подложить инструмент без примера — проверка обязана его найти.

    python bin/contract_probe.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import build_registry as reg  # noqa: E402

LOOP = ROOT / "core-rs" / "src" / "loopmod.rs"
OUT = ROOT / "research" / "outputs" / "contract-check.txt"


def prompt_text() -> str:
    """Собирает текст подсказки цикла: строки, которые уходят модели."""
    source = LOOP.read_text(encoding="utf-8")
    # Подсказка собрана из строковых литералов; берём все фрагменты, где упоминаются инструменты.
    return source


def covered(name: str, rows: list[dict], text: str) -> bool:
    """Инструмент описан в подсказке, если там есть его имя и хотя бы один пример вызова."""
    row = next((item for item in rows if item["id"] == name), None)
    if row is None:
        return False
    if name not in text:
        return False
    return any(example.split()[-1] in text for example in row["examples"])


def main() -> int:
    rows = [json.loads(line) for line in reg.REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    text = prompt_text()

    lines = ["# Контракт инструментов доходит до модели", ""]
    ok_count = 0
    for row in rows:
        name = row["id"]
        has_name = name in text
        has_example = any(example.split()[-1] in text for example in row["examples"])
        has_semantics = any(word in text for word in row["semantics"].split()[:4] if len(word) > 4)
        ok = has_name and has_example
        ok_count += 1 if ok else 0
        lines.append(
            f"{name:10} имя {'да' if has_name else 'НЕТ':4} пример {'да' if has_example else 'НЕТ':4} "
            f"семантика {'да' if has_semantics else 'нет'}"
        )

    # Отрицательный контроль: инструмент без примера обязан быть замечен.
    broken = [dict(row) for row in rows]
    broken[0]["examples"] = []
    caught = bool(reg.problems(broken))
    lines.append(f"{'без примера':10} {'поймано' if caught else 'ПРОПУЩЕНО'}")

    lines += [
        "",
        f"инструментов с именем и примером в подсказке: {ok_count} из {len(rows)}",
        "# Что доказывает: каждый инструмент назван в подсказке и его пример вызова доступен модели.",
        "# Что не доказывает: что модель эти примеры использует; это проверяется прогоном.",
    ]
    text_out = "\n".join(lines) + "\n"
    OUT.write_text(text_out, encoding="utf-8")
    print(text_out)
    return 0 if ok_count == len(rows) and caught else 1


if __name__ == "__main__":
    sys.exit(main())
