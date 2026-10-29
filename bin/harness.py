"""Список харнессов для сравнения подходов.

Числа (звёзды, лицензия, дата push) проверены через API; свойства взяты из переписи и помечены как
непроверенные. Задача команды — быстро найти, чей подход посмотреть под конкретный вопрос.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load() -> dict:
    return json.loads((ROOT / "harnesses.json").read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    data = load()
    items = data["items"]
    args = [a for a in argv if not a.startswith("--")]

    if "--stale" in argv:
        items = [i for i in items if i["last_push"] < "2026-09-01"]
        print("давно не обновлялись:")
    if args:
        term = args[0].lower()
        items = [i for i in items if term in (i["name"] + " " + i["what"] + " " + i["when"] + " " + i["id"]).lower()]
        print(f"по запросу «{args[0]}»:")

    if not args and "--stale" not in argv:
        print(f"харнессов в реестре: {len(items)} (проверено {data['checked_at']})")
        print(f"{'id':<14} {'★':>8}  {'push':<11} чем полезен для сравнения")
        for item in sorted(items, key=lambda i: -i["stars"]):
            print(f"{item['id']:<14} {item['stars']:>8}  {item['last_push']:<11} {item['when'][:64]}")
        return 0

    for item in sorted(items, key=lambda i: -i["stars"]):
        print(f"\n{item['name']} — {item['repo']} ({item['stars']}, {item['license']}, push {item['last_push']})")
        print(f"  что: {item['what']}")
        print(f"  когда смотреть: {item['when']}")
        props = {k: item[k] for k in ("loop", "state", "tools", "permissions", "secrets",
                                      "recovery", "evidence", "budget", "multiagent")}
        print("  свойства:", ", ".join(f"{k}={v}" for k, v in props.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
