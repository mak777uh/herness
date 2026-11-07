"""claims_audit — может ли автор утверждения подтвердить себя собой?

Находка из аудита гейтов: у утверждений опору выбирает автор. Проверяем на реальном
CLAIMS.md: есть ли утверждения, где ожидание — это слово из самого утверждения,
а не число или путь из артефакта.

Правило усиления: ожидание обязано быть числом, путём или кодом — тем, что можно
найти в артефакте, но нельзя придумать.

    python bin/claims_audit.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "CLAIMS.md"
OUT = ROOT / "research" / "outputs" / "claims-audit.txt"


def looks_checkable(expect: str) -> bool:
    """Ожидание проверяемо, если в нём есть число, путь или код — а не общее слово."""
    if re.search(r"\d", expect):
        return True
    if "/" in expect or ".md" in expect or ".txt" in expect or ".json" in expect:
        return True
    if re.search(r"[A-Z]-\d", expect):
        return True
    return False


def main() -> int:
    rows = []
    for line in CLAIMS.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| C-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        # Порядок колонок: id | утверждение | тип | команда | артефакт | дата | ожидание
        rows.append({"id": cells[0],
                     "artifact": cells[4] if len(cells) > 4 else "",
                     "expect": cells[6].strip("`") if len(cells) > 6 else ""})

    weak = [r for r in rows if not looks_checkable(r["expect"])]
    lines = ["# Утверждения: может ли автор подтвердить себя собой", ""]
    lines.append(f"утверждений: {len(rows)}")
    lines.append(f"слабых ожиданий: {len(weak)}")
    lines.append("")
    if weak:
        lines.append("| утверждение | ожидание | артефакт |")
        lines.append("|---|---|---|")
        for r in weak[:20]:
            lines.append(f"| {r['id']} | {r['expect']} | {r['artifact']} |")
        lines.append("")
    lines += [
        "## Правило",
        "",
        "Ожидание обязано быть числом, путём или кодом — тем, что можно найти в артефакте,",
        "но нельзя придумать. Общее слово вроде «ок» или «пройдено» подтверждает себя собой.",
        "",
        "## Граница",
        "",
        "Это проверка формы ожидания, а не содержания утверждения. Утверждение с числом",
        "всё ещё может быть ложным — но его ложность видна при сверке с артефактом.",
    ]
    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
