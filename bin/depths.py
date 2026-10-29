"""Лестница глубины: где мы на каждой ступени и что стоит следующая."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    data = json.loads((ROOT / "depths.json").read_text(encoding="utf-8"))
    levels = {item["id"]: item for item in data["levels"]}
    classes = data["classes"]
    args = [a for a in argv if not a.startswith("--")]
    if args:
        term = args[0].lower()
        classes = [c for c in classes if term in (c["name"] + " " + c["id"]).lower()]

    if "--ladders" in argv:
        for cls in classes:
            print(f"\n=== {cls['name']} — сейчас {cls['ours']['level']}")
            for step in cls["ladder"]:
                mark = "→" if step["level"] == cls["ours"]["level"] else " "
                print(f" {mark} {step['level']} {step['what']}  [{step['cost']}]")
        return 0

    print(f"{'класс':<34} {'сейчас':<7} следующий шаг")
    for cls in classes:
        current = cls["ours"]["level"]
        order = [step["level"] for step in cls["ladder"]]
        nxt = order[order.index(current) + 1] if current in order and order.index(current) + 1 < len(order) else "—"
        nxt_what = next((s["what"] for s in cls["ladder"] if s["level"] == nxt), "предел")
        print(f"{cls['name'][:33]:<34} {current:<7} {nxt}: {nxt_what[:60]}")
    print("\nуровни:", ", ".join(f"{k}={v['name']}" for k, v in levels.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
