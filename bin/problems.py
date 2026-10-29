"""Справочник решений: какие подходы бывают и что выбрано у нас."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    data = json.loads((ROOT / "problems.json").read_text(encoding="utf-8"))
    problems = data["problems"]
    args = [a for a in argv if not a.startswith("--")]
    term = args[0].lower() if args else ""

    if term:
        problems = [p for p in problems
                    if term in (p["name"] + " " + " ".join(a["name"] + " " + " ".join(a["who"])
                                                           for a in p["approaches"])).lower()]
        print(f"по запросу «{args[0]}»: проблем {len(problems)}")

    if "--brief" in argv:
        for problem in problems:
            ours = problem["ours"]
            print(f"{problem['id']} {problem['name']}")
            print(f"    подходов: {len(problem['approaches'])}; у нас: {ours['choice']} ({ours['status']})")
        return 0

    for problem in problems:
        print(f"\n{problem['id']}. {problem['name']}")
        for approach in problem["approaches"]:
            who = ", ".join(approach["who"])
            print(f"  · {approach['name']} — {who} | {approach['popularity']}")
            print(f"    цена: {approach['price']}")
        ours = problem["ours"]
        print(f"  НАШЕ: {ours['choice']} — {ours['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
