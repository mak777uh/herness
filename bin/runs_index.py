"""runs_index — явный индекс прогонов: журнал → задача, критерий, серия, дата.

Зачем: метрики определяли задачу по имени журнала (`p27-T-exact-C-0179` → задача после префикса).
Любое новое имя серии ломало счёт молча. Здесь соответствие записано один раз и проверяется:
каждый журнал в runs/accept обязан иметь запись, и каждая запись — существующий критерий.

    python bin/runs_index.py --build    # пересобрать runs/index.json
    python bin/runs_index.py --check    # сверить индекс с журналами
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "runs" / "index.json"
JOURNALS = ROOT / "runs" / "accept"
SERIES = [
    "p27-", "p27r2-", "refusal-", "refusal2-", "refusal3-", "musique3-", "musique4-",
    "musique5-", "musique6-", "musique7-", "hist-", "fix-", "h2-", "h3-", "h4-", "h5-", "h6-", "long-", "beam-",
]
FOLDERS = ("accept/p27", "accept/musique", "accept/refusal", "accept/history", "accept/history2",
           "accept/history3", "accept/history4", "accept/history5", "accept/history6", "accept/long")


def criteria_map() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for folder in FOLDERS:
        for path in sorted((ROOT / folder).glob("*.json")):
            found[path.stem] = path
    return found


def musique_order() -> list[str]:
    path = ROOT / "lab/p27/musique/tasks.json"
    if not path.exists():
        return []
    return [task["id"] for task in json.loads(path.read_text(encoding="utf-8"))["tasks"]]


def build() -> int:
    criteria = criteria_map()
    order = musique_order()
    entries = {}
    unresolved = []
    for path in sorted(JOURNALS.glob("*.bin")):
        stem = path.stem
        task = None
        series = ""
        for prefix in SERIES:
            if stem.startswith(prefix):
                series = prefix.rstrip("-")
                rest = stem[len(prefix):]
                if rest in criteria:
                    task = rest
                elif rest.isdigit() and series.startswith("musique") and int(rest) < len(order):
                    task = order[int(rest)]
                break
        if task is None and stem in criteria:
            task = stem
        if task is None:
            unresolved.append(stem)
        entries[stem] = {
            "task": task,
            "series": series,
            "criteria": str(criteria[task].relative_to(ROOT)).replace("\\", "/") if task else None,
        }
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(
        json.dumps({"schema": 1, "runs": entries}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"записано: {INDEX.relative_to(ROOT)}; журналов {len(entries)}; без задачи {len(unresolved)}")
    for name in unresolved[:10]:
        print("  без задачи:", name)
    return 0


def check() -> int:
    if not INDEX.exists():
        print("нет runs/index.json: собрать bin/runs_index.py --build")
        return 1
    data = json.loads(INDEX.read_text(encoding="utf-8"))["runs"]
    problems = []
    journals = {path.stem for path in JOURNALS.glob("*.bin")}
    for stem in sorted(journals - set(data)):
        problems.append(f"{stem}: журнал без записи в индексе")
    for stem in sorted(set(data) - journals):
        problems.append(f"{stem}: запись без журнала")
    for stem, entry in data.items():
        if entry.get("task") and entry.get("criteria") and not (ROOT / entry["criteria"]).exists():
            problems.append(f"{stem}: критерий {entry['criteria']} не существует")
    if problems:
        print("ПРОБЛЕМЫ:")
        for problem in problems[:20]:
            print("  -", problem)
        return 1
    print(f"[ok] индекс прогонов: {len(data)} журналов, у всех есть запись")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="индекс прогонов")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.build:
        return build()
    if args.check:
        return check()
    print("укажи --build или --check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
