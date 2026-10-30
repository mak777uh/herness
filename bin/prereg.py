"""Пре-регистрация: проверка формата и поиск экспериментов без регистрации.

Правило взято у Morphogenesis: гипотеза и критерий фиксируются до запуска, а «разница между плечами»
не запускается, пока не посчитана арифметика, которая эту разницу создаёт.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "lab" / "prereg"
REQUIRED = ("id", "date", "question", "hypothesis", "criterion", "arms", "sensitivity")


def entries() -> tuple[list[dict], list[str]]:
    items, problems = [], []
    for path in sorted(PREREG.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}: не JSON ({exc.msg})")
            continue
        missing = [field for field in REQUIRED if not data.get(field)]
        if missing:
            problems.append(f"{path.name}: нет полей {', '.join(missing)}")
        if data.get("closed") and not data.get("conclusion"):
            problems.append(f"{path.name}: закрыто без conclusion")
        data["_file"] = path.name
        items.append(data)
    return items, problems


def experiment_dirs() -> list[Path]:
    runs = ROOT / "runs"
    if not runs.exists():
        return []
    return sorted(path for path in runs.iterdir() if path.is_dir() and path.name.startswith(("exp", "batch")))


def debt(items: list[dict]) -> list[str]:
    registered = {run for item in items for run in item.get("runs", [])}
    result = []
    for directory in experiment_dirs():
        relative = f"runs/{directory.name}"
        if relative not in registered:
            result.append(relative)
    return result


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "check"
    items, problems = entries()

    if command == "debt":
        missing = debt(items)
        print(f"пре-регистраций: {len(items)} | экспериментов без регистрации: {len(missing)}")
        for path in missing[:20]:
            print(" ", path)
        return 0

    print(f"пре-регистраций: {len(items)}")
    with_sensitivity = sum(1 for item in items if item.get("sensitivity"))
    print(f"чувствительность: есть у {with_sensitivity} из {len(items)}")
    for problem in problems:
        print(f"[FAIL] {problem}")
    unclosed = [item["id"] for item in items if not item.get("closed")]
    if unclosed:
        print(f"не закрыты: {', '.join(unclosed)}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
