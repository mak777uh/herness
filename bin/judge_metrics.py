"""judge_metrics — метрики приёмки по уже лежащим журналам.

Считает то, чего у нас не было: долю ложных «готово», точность и полноту заявлений, pass^k и цену
принятого решения. Данные не новые — берутся журналы `runs/accept/*.bin` и критерии из `accept/`.

    python bin/judge_metrics.py            # записать research/outputs/acceptance-metrics.txt

Правила:
  заявление  «готово»  — в журнале есть run/end и статус выведен как done;
  вердикт              — accept.check по критерию задачи;
  pass@1 / pass^k      — по повторам одной и той же задачи (k = число прогонов);
  цена                 — сумма allowance из событий step (если их нет, прогон не учитывается).
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, ".")
from bin import accept  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SERIES = [
    ("p27", "accept/p27", "runs/accept/p27-{i}.bin"),
    ("p27r2", "accept/p27", "runs/accept/p27r2-{i}.bin"),
    ("musique3", "accept/musique", "runs/accept/musique3-{i}.bin"),
    ("musique4", "accept/musique", "runs/accept/musique4-{i}.bin"),
    ("musique5", "accept/musique", "runs/accept/musique5-{i}.bin"),
    ("musique7", "accept/musique", "runs/accept/musique7-{i}.bin"),
]


def criteria_for(folder: str) -> dict[str, dict]:
    result = {}
    base = ROOT / folder
    for path in sorted(base.glob("*.json")):
        result[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return result


def spend(records) -> float:
    total = 0.0
    for kind, rest in accept.events(records):
        if kind == "step":
            match = re.search(r"потрачено\s+([0-9.]+)", rest)
            if match:
                total += float(match.group(1))
    return total


def main() -> int:
    by_task: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for series, folder, pattern in SERIES:
        criteria = criteria_for(folder)
        index = 0
        while True:
            path = ROOT / pattern.format(i=index)
            if not path.exists():
                break
            index += 1
            names = list(criteria)
            if index - 1 >= len(names):
                break
            name = names[index - 1]
            records, _tail, _problems = accept.parse_journal(path.read_bytes())
            ok, _rows = accept.check(criteria[name], records)
            kinds = [kind for kind, _ in accept.events(records)]
            claimed = "run/end" in kinds and "claim/anchored" in kinds
            status = accept.derive_status(records) if hasattr(accept, "derive_status") else None
            by_task[name][series].append(
                {"ok": ok, "claimed": claimed, "spend": spend(records), "status": status,
                 "anchored": "claim/anchored" in kinds}
            )

    lines = ["# Метрики приёмки по существующим журналам", ""]
    lines.append(f"{'задача':34} прогонов  принято  заявлено  pass@1   pass^k")
    claims = confirmed = 0
    accepts = 0
    total_spend = 0.0
    unknown = 0
    for name, runs in sorted(by_task.items()):
        flat = [run for series in runs.values() for run in series]
        if not flat:
            continue
        n = len(flat)
        a = sum(1 for run in flat if run["ok"])
        c = sum(1 for run in flat if run["claimed"])
        claims += c
        confirmed += sum(1 for run in flat if run["ok"] and run["claimed"])
        accepts += a
        total_spend += sum(run["spend"] for run in flat)
        unknown += sum(1 for run in flat if not run["ok"] and not run["claimed"])
        pass1 = a / n
        # pass^k при равном числе прогонов: доля задач, где ВСЕ прогоны приняты
        best = max((len(series) for series in runs.values()), default=0)
        full = 0
        for series in runs.values():
            if len(series) == best and best > 1 and all(run["ok"] for run in series):
                full += 1
        passk = f"{full}/{len([s for s in runs.values() if len(s) == best])}" if best > 1 else "—"
        lines.append(f"{name[:34]:34} {n:<8} {a:<8} {c:<9} {pass1:<8.2f} {passk}")

    lines += [
        "",
        f"заявлений «готово»: {claims}; подтверждено приёмкой: {confirmed}",
        f"принято: {accepts}; ложных заявлений: {claims - confirmed}",
        f"false_completion_rate: {(claims - confirmed) / claims:.2f}" if claims else "false_completion_rate: —",
        f"completion_precision: {confirmed / claims:.2f}" if claims else "completion_precision: —",
        f"цена всех прогонов (allowance): {total_spend:.4f}",
        f"цена одного принятого: {total_spend / accepts:.4f}" if accepts else "цена одного принятого: —",
        f"прогонов без заявления и без вердикта: {unknown}",
        "",
        "# Оговорки: «заявлено» = есть claim/anchored и run/end; часть журналов могла не иметь",
        "# заявления, поэтому precision считается только по заявившим. pass^k показан как доля",
        "# задач, где ВСЕ прогоны серии приняты, и только для серий равной длины.",
    ]
    text = "\n".join(lines) + "\n"
    out = ROOT / "research" / "outputs" / "acceptance-metrics.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
