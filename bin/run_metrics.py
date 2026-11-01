"""run_metrics — что можно измерить по журналу прогона, не спрашивая модель.

Зачем: гипотеза H-0004 («детектор барахтания») требует числа, а не мнения. Здесь считается то,
что видно в журнале: шаги, вызовы, повторы одних и тех же вызовов (барахтание), исход и вердикт
приёмки. Никаких оценок «качества» — только счётчики.

    python bin/run_metrics.py accept/<критерий>.json runs/accept/*.bin
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import accept, false_done  # noqa: E402


def metrics(path: Path, criteria: dict) -> dict:
    records, tail, problems = accept.parse_journal(path.read_bytes())
    evs = accept.events(records)
    kinds = [kind for kind, _ in evs]
    calls = [rest.split(" ", 1)[0] for kind, rest in evs if kind == "tool/call"]
    full_calls = [rest for kind, rest in evs if kind == "tool/call"]
    repeats = sum(count - 1 for count in Counter(full_calls).values() if count > 1)
    form_ok, _note = false_done.form_verdict(path)
    verdict, _rows = accept.check(criteria, records)
    ratio = (repeats / len(full_calls)) if full_calls else 0.0
    anchored = "claim/anchored" in kinds
    # Режим провала: два измеренных класса (C-0183 и C-0186). Разделять их важно: лечится
    # барахтание (порог повторов) и «упорство без результата» (много вызовов, нет опоры)
    # по-разному, и общий вердикт FAIL их не различает.
    if verdict:
        mode = "принят"
    elif ratio > 0.35:
        mode = "барахтание (повторы)"
    elif not anchored and len(full_calls) >= 10:
        mode = "упорство без результата"
    elif not anchored:
        mode = "нет опоры (мало вызовов)"
    else:
        mode = "отказ по другим условиям"
    return {
        "файл": path.name,
        "формой": "ok" if form_ok else "нет",
        "приёмка": "PASS" if verdict else "FAIL",
        "режим": mode,
        "шагов": len([k for k in kinds if k == "step"]),
        "вызовов": len(calls),
        "повторов": repeats,
        "доля повторов": ratio,
        "хвост": tail,
        "проблем разбора": len(problems),
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if len(argv) < 2:
        print("run_metrics <критерий.json> <журнал.bin>...", file=sys.stderr)
        return 2
    criteria = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    rows = [metrics(Path(name), criteria) for name in argv[1:] if Path(name).exists()]
    if not rows:
        print("нет журналов", file=sys.stderr)
        return 1
    keys = list(rows[0])
    print(" | ".join(keys))
    for row in rows:
        print(" | ".join(f"{row[key]:.2f}" if isinstance(row[key], float) else str(row[key])
                         for key in keys))
    total_calls = sum(row["вызовов"] for row in rows)
    total_repeats = sum(row["повторов"] for row in rows)
    print(f"\nжурналов: {len(rows)}; вызовов всего: {total_calls}; повторов: {total_repeats}"
          + (f" ({total_repeats / total_calls:.0%})" if total_calls else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
