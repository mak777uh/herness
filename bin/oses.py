"""Реестр ОС: что известно, где расходятся, что проверить."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    data = json.loads((ROOT / "oses.json").read_text(encoding="utf-8"))
    items = data["items"]
    args = [a for a in argv if not a.startswith("--")]

    if "--splits" in argv:
        print("клетки, где модели расходятся:")
        for item in items:
            splits = [key for key, value in item.items() if key.endswith("_conf") and value == "split"]
            if splits:
                fields = ", ".join(split.replace("_conf", "") for split in splits)
                print(f"  {item['name']}: {fields}")
        return 0

    if args:
        term = args[0].lower()
        items = [i for i in items if term in (i["name"] + " " + i.get("rollback", "") + " " + i.get("init", "")).lower()]
        print(f"по запросу «{args[0]}»: {len(items)}")

    print(f"{'ОС':<26} {'откат':<28} {'согл.':<10} {'lean4':<28} согл.")
    for item in items:
        print(f"{item['name'][:25]:<26} {item['rollback'][:27]:<28} {item['rollback_conf']:<10} "
              f"{item.get('lean4', '')[:27]:<28} {item.get('lean4_conf', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
