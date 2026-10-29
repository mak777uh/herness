"""matrix — покрытие: сколько клеток «харнесс × проблема» размечено.

Читает `problems` в harnesses.json (разметка по путям репозитория). Пустая клетка — «нет данных»,
а не «нет»: это разные вещи, и смешивать их нельзя.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# какое свойство реестра чем подтверждается
OLD = {"P2": "state", "P3": "tools", "P6": "permissions", "P7": "evidence", "P8": "multiagent"}


def main() -> int:
    harnesses = json.loads((ROOT / "harnesses.json").read_text(encoding="utf-8"))["items"]
    problems = json.loads((ROOT / "problems.json").read_text(encoding="utf-8"))["problems"]
    ids = [p["id"] for p in problems]
    names = {p["id"]: p["name"] for p in problems}

    total = len(harnesses) * len(ids)
    known = 0
    per_problem = {pid: {"есть": 0, "частично": 0, "нет": 0, "нет данных": 0} for pid in ids}

    for harness in harnesses:
        marks = harness.get("problems") or {}
        for pid in ids:
            value = marks.get(pid)
            if value is None:
                prop = OLD.get(pid)
                value = harness.get(prop, "нет данных") if prop else "нет данных"
            if value not in per_problem[pid]:
                value = "нет данных"
            per_problem[pid][value] += 1
            if value != "нет данных":
                known += 1

    marked = sum(1 for h in harnesses if h.get("marked_from"))
    print(f"харнессов: {len(harnesses)} (размечено по путям: {marked}), проблем: {len(ids)}, клеток: {total}")
    print(f"размечено: {known} ({round(100 * known / total)}%), пусто: {total - known}")
    print(f"\n{'проблема':<46} {'есть':>5} {'част':>5} {'нет':>5} {'н/д':>5}")
    for pid in ids:
        stats = per_problem[pid]
        print(f"{pid} {names[pid][:44]:<44} {stats['есть']:>5} {stats['частично']:>5} "
              f"{stats['нет']:>5} {stats['нет данных']:>5}")

    empty = [pid for pid in ids if per_problem[pid]["нет данных"] == len(harnesses)]
    print(f"\nне размечено ни у кого: {', '.join(empty) or '—'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
