"""refusal_series — коды отказа для серии отказов.

Каждый отказ в серии получает код из закрытого словаря. Зачем: «не прошло» без кода
не отличимо от «проверка сломалась». С кодом видно, что именно не прошло.

    python bin/refusal_series.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "outputs" / "refusal-coded.txt"

# Серия отказов: задача, что произошло, код из словаря.
SERIES = [
    ("R1-present-control", "утверждение с опорой принято", "PASS", None),
    ("R2-absent", "утверждение без опоры отвергнуто", "REFUSED", "S3_ANCHOR_ABSENT"),
    ("R3-stale", "опора из старого результата отвергнута", "REFUSED", "S3_ANCHOR_STALE"),
    ("R4-present-control", "утверждение с опорой принято", "PASS", None),
    ("R5-no-artifact", "артефакт утверждения отсутствует", "REFUSED", "S2_ARTIFACT_MISSING"),
    ("R6-expect-missing", "ожидание не найдено в артефакте", "REFUSED", "S2_EXPECT_MISSING"),
    ("R7-undecidable", "ожидание нельзя проверить машинно", "REFUSED", "S2_EXPECT_UNDECIDABLE"),
]


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from bin import refusal_codes as rc

    lines = ["# Серия отказов с кодами", ""]
    lines.append("| задача | что произошло | вердикт | код | что делать |")
    lines.append("|---|---|---|---|---|")
    problems = 0
    for task, what, verdict, code in SERIES:
        if code is None:
            lines.append(f"| {task} | {what} | {verdict} | — | — |")
            continue
        if code not in rc.VOCABULARY:
            problems += 1
            lines.append(f"| {task} | {what} | {verdict} | **{code}** | НЕ ИЗ СЛОВАРЯ |")
            continue
        _, remedy = rc.VOCABULARY[code]
        lines.append(f"| {task} | {what} | {verdict} | `{code}` | {remedy} |")

    lines += [
        "",
        f"кодов вне словаря: {problems}",
        "",
        "## Правило",
        "",
        "Код не переиспользуется для другого дефекта и не перенумеровывается.",
        "Отказ — это находка о входе, а не о настроении проверяющего.",
    ]
    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
