"""judge_metrics — метрики приёмки по журналам: ложные «готово», precision, pass@1, pass^k, цена.

Отличие от первой версии: журналы находятся по имени задачи, а не по номеру серии, поэтому в счёт
попадают и P27, и MuSiQue, и серия на отказ.

    python bin/judge_metrics.py     # research/outputs/acceptance-metrics.txt

Формулы (tau-bench, arxiv.org/pdf/2406.12045):
  pass@1 = доля принятых прогонов;
  pass^k  = среднее по задачам от C(c,k)/C(n,k) — успех ВСЕХ k прогонов (k = 2);
  false_completion_rate = |{claim=done ∧ не принято}| / |{claim=done}|;
  цена принятого = сумма allowance / число принятых.
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
JOURNALS = ROOT / "runs" / "accept"
SERIES = ["p27-", "p27r2-", "refusal-", "refusal2-", "refusal3-", "musique3-", "musique4-",
          "musique5-", "musique6-", "musique7-"]


def all_criteria() -> dict[str, dict]:
    result: dict[str, dict] = {}
    # Все папки критериев: серии из истории лежат в accept/history*, и без них индекс ссылается
    # на несуществующие критерии.
    for folder in ("accept/p27", "accept/musique", "accept/refusal", "accept/history",
                   "accept/history2", "accept/history3", "accept/history4", "accept/history5",
                   "accept/history6", "accept/long"):
        for path in sorted((ROOT / folder).glob("*.json")):
            result[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return result


def musique_order() -> list[str]:
    data = json.loads((ROOT / "lab/p27/musique/tasks.json").read_text(encoding="utf-8"))
    return [task["id"] for task in data["tasks"]]


INDEX = ROOT / "runs" / "index.json"


def resolve(name: str, criteria: dict[str, dict], order: list[str]) -> str | None:
    # Сначала явный индекс: имя журнала перестало быть единственным источником правды.
    # Если индекса нет, работает прежнее правило по префиксу серии.
    if INDEX.exists():
        data = json.loads(INDEX.read_text(encoding="utf-8")).get("runs", {})
        stem = name[:-4] if name.endswith(".bin") else name
        entry = data.get(stem)
        if entry is not None:
            return entry.get("task")
    stem = name[:-4] if name.endswith(".bin") else name
    for prefix in SERIES:
        if stem.startswith(prefix):
            rest = stem[len(prefix):]
            if rest in criteria:
                return rest
            if rest.isdigit():
                index = int(rest)
                if prefix.startswith("musique") and index < len(order):
                    return order[index]
    return stem if stem in criteria else None


def spend(records) -> float:
    total = 0.0
    for kind, rest in accept.events(records):
        if kind == "step":
            match = re.search(r"потрачено\s+([0-9.]+)", rest)
            if match:
                total += float(match.group(1))
    return total


def choose(count: int, k: int) -> int:
    return math.comb(count, k) if count >= k else 0


def main() -> int:
    criteria = all_criteria()
    order = musique_order()
    runs: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(JOURNALS.glob("*.bin")):
        task = resolve(path.name, criteria, order)
        if task is None:
            continue
        try:
            records, _tail, _problems = accept.parse_journal(path.read_bytes())
        except Exception:  # noqa: BLE001
            continue
        ok, _rows = accept.check(criteria[task], records)
        kinds = [kind for kind, _ in accept.events(records)]
        runs[task].append({"ok": ok, "claimed": "claim/anchored" in kinds, "spend": spend(records)})

    lines = ["# Метрики приёмки по журналам", "",
             f"{'задача':34} {'прогонов':>9} {'принято':>8} {'pass@1':>7} {'pass^2':>7}"]
    claims = confirmed = accepts = unknown = 0
    total_spend = 0.0
    pass2_values = []
    for task in sorted(runs):
        items = runs[task]
        n = len(items)
        a = sum(1 for item in items if item["ok"])
        c = sum(1 for item in items if item["claimed"])
        claims += c
        accepts += a
        confirmed += sum(1 for item in items if item["ok"] and item["claimed"])
        unknown += sum(1 for item in items if not item["ok"] and not item["claimed"])
        total_spend += sum(item["spend"] for item in items)
        if n >= 2:
            pass2_values.append(choose(a, 2) / choose(n, 2))
        pass2 = f"{choose(a,2)/choose(n,2):.2f}" if n >= 2 else "—"
        lines.append(f"{task[:34]:34} {n:>9} {a:>8} {a/n:>7.2f} {pass2:>7}")

    lines += [
        "",
        f"заявлений «готово»: {claims}; подтверждено: {confirmed}; ложных: {claims - confirmed}",
        f"false_completion_rate: {(claims - confirmed) / claims:.2f}" if claims else "false_completion_rate: —",
        f"completion_precision: {confirmed / claims:.2f}" if claims else "completion_precision: —",
        f"pass@1 (по всем прогонам): {accepts / sum(len(v) for v in runs.values()):.2f}",
        f"pass^2 (среднее C(c,2)/C(n,2) по задачам с n≥2): {sum(pass2_values)/len(pass2_values):.2f}"
        if pass2_values else "pass^2: —",
        f"цена всех прогонов: {total_spend:.4f}; цена принятого: {total_spend/accepts:.4f}" if accepts
        else f"цена всех прогонов: {total_spend:.4f}",
        f"прогонов без заявления и без вердикта: {unknown}",
        "",
        "# Оговорки: journal с неизвестным именем задачи пропущен; «заявлено» = claim/anchored;",
        "# pass^2 = вероятность, что ОБА прогона задачи приняты (надёжность, а не удача).",
    ]
    text = "\n".join(lines) + "\n"
    out = ROOT / "research" / "outputs" / "acceptance-metrics.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
