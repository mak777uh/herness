"""loop_audit — считать петли по определению DeLoop на уже лежащих журналах.

Определение (arXiv 2610.19376): шаг — петля, если канонизированный вызов уже встречался в этом
прогоне И инструмент вернул байт-в-байт тот же результат. «Тот же файл» петлёй не считается:
повторное чтение после изменения состояния даёт новый результат и является полезным.

Зачем: у нас 15 из 26 молчаний списаны на «зацикливание на одном файле», но это была наша метрика
по пути, а не по информации. Здесь считается то же самое по информации — и сравнивается.

    python bin/loop_audit.py     # research/outputs/loop-audit.txt
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, ".")
from bin import accept  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
JOURNALS = ROOT / "runs" / "accept"


def canon(call: str) -> str:
    return re.sub(r"\s+", " ", call.strip().lower())


def analyse(path: Path) -> dict:
    records, _tail, _problems = accept.parse_journal(path.read_bytes())
    pairs: list[tuple[str, str]] = []
    pending: str | None = None
    for kind, rest in accept.events(records):
        if kind == "tool/call":
            pending = canon(rest)
        elif kind == "tool/result" and pending is not None:
            pairs.append((pending, rest))
            pending = None
    seen: dict[str, str] = {}
    loops = 0
    informative = 0
    for call, result in pairs:
        previous = seen.get(call)
        if previous is None:
            seen[call] = result
            continue
        if previous == result:
            loops += 1
        else:
            informative += 1
            seen[call] = result
    kinds = [kind for kind, _ in accept.events(records)]
    return {
        "steps": len(pairs),
        "loops": loops,
        "informative": informative,
        "rate": loops / len(pairs) if pairs else 0.0,
        "anchored": "claim/anchored" in kinds,
        "blocked": "run/blocked" in kinds,
    }


def main() -> int:
    rows = []
    for path in sorted(JOURNALS.glob("*.bin")):
        try:
            rows.append((path.stem, analyse(path)))
        except Exception:  # noqa: BLE001
            continue

    total_steps = sum(row["steps"] for _, row in rows)
    total_loops = sum(row["loops"] for _, row in rows)
    with_loops = [row for _, row in rows if row["loops"] > 0]
    clean = [row for _, row in rows if row["loops"] == 0]
    inf_with = sum(1 for row in with_loops if not row["anchored"] and not row["blocked"])
    inf_clean = sum(1 for row in clean if not row["anchored"] and not row["blocked"])

    lines = [
        "# Петли по определению DeLoop (тот же вызов + тот же результат)",
        "",
        f"журналов: {len(rows)}; шагов: {total_steps}; петель: {total_loops} "
        f"({total_loops / total_steps:.1%})" if total_steps else "журналов нет",
        f"прогонов хотя бы с одной петлёй: {len(with_loops)}; без петель: {len(clean)}",
        "",
        f"доля прогонов без терминального исхода (ни DONE с опорой, ни отказ):",
        f"  среди прогонов с петлями: {inf_with}/{len(with_loops)} = "
        f"{(inf_with / len(with_loops) if with_loops else 0):.0%}",
        f"  среди прогонов без петель: {inf_clean}/{len(clean)} = "
        f"{(inf_clean / len(clean) if clean else 0):.0%}",
        "",
        "## По журналам (только с петлями)",
        f"{'журнал':28} шагов петель доля исход",
    ]
    for name, row in rows:
        if row["loops"] == 0:
            continue
        outcome = "отказ" if row["blocked"] else ("DONE+опора" if row["anchored"] else "молчание")
        lines.append(f"{name[:28]:28} {row['steps']:>5} {row['loops']:>6} {row['rate']:>5.0%} {outcome}")
    lines += [
        "",
        "# Сравнение с прежней метрикой: раньше в 15 из 26 молчаний усматривали «зацикливание на",
        "# одном файле» по повтору пути. Здесь петля — повтор ВЫЗОВА с ТЕМ ЖЕ результатом; повторное",
        "# чтение после изменения или другой запрос к тому же файлу петлёй не считается.",
    ]
    text = "\n".join(lines) + "\n"
    out = ROOT / "research" / "outputs" / "loop-audit.txt"
    out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
