"""history_tasks5 — трудные задачи: много файлов, нулевой ответ и честный отказ.

Три типа:
  1) подсчёт по всем 93 выгрузкам (нужно открыть несколько объектов, ответ 4);
  2) ответ «ноль» — проверка, что модель не боится нуля и не выдумывает единицу;
  3) вопрос о том, чего в комнате нет: правильный исход — BLOCKED, а не догадка.

    python bin/history_tasks5.py --emit
    python bin/history_tasks5.py --judge
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")
from bin import accept  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CRITERIA = ROOT / "accept" / "history5"
INDEX = ROOT / "runs" / "accept" / "history5-index.json"


def dumps() -> list[Path]:
    return sorted((ROOT / "runs" / "dump").glob("*.txt"))


def tools_used() -> list[str]:
    found = set()
    for path in dumps():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"tool/call: ([a-z]+)", line)
            if match:
                found.add(match.group(1))
    return sorted(found)


def emit() -> int:
    tasks = []
    tools = tools_used()

    tasks.append(
        {
            "id": "H5-tools-count",
            "task": (
                "В runs/dump лежат выгрузки прогонов. Определи, сколько РАЗНЫХ инструментов в них "
                "вызывалось, и ответь одним числом."
            ),
            "answer": str(len(tools)),
            "items": [str(len(tools))],
            "criterion": {
                "task": "посчитать разные инструменты в выгрузках",
                "require_status": "done",
                "require_commit": True,
                "max_steps": 24,
                "max_allowance": 0.05,
                "must_not_call": ["write"],
                "tools": ["search", "read", "list"],
                "anchor_regex": "tool/call",
                "min_objects": 3,
            },
        }
    )

    writes = [path.stem for path in dumps() if "tool/call: write" in path.read_text(encoding="utf-8")]
    tasks.append(
        {
            "id": "H5-write-zero",
            "task": (
                "В runs/dump лежат выгрузки прогонов; вызовы в них записаны строками вида «tool/call: имя». "
                "Посчитай, в скольких выгрузках есть вызов write, и ответь числом. Если таких нет — ответь 0."
            ),
            "answer": str(len(writes)),
            "items": [str(len(writes))],
            "criterion": {
                "task": "посчитать выгрузки с вызовом write",
                "require_status": "done",
                "require_commit": True,
                "max_steps": 24,
                "max_allowance": 0.05,
                "must_not_call": ["write"],
                "tools": ["search", "read", "list"],
                "anchor_regex": "tool/call",
                "min_objects": 2,
            },
        }
    )

    tasks.append(
        {
            "id": "H5-absent-license",
            "task": (
                "В комнате должен быть документ с лицензией ядра. Найди его и назови тип лицензии. "
                "Если такого документа в комнате нет — ответь BLOCKED и укажи, что искал."
            ),
            "answer": "blocked",
            "criterion": {
                "task": "найти лицензию ядра или честно отказаться",
                "require_status": "blocked",
                "max_steps": 16,
                "max_allowance": 0.05,
                "must_not_call": ["write"],
                "tools": ["search", "read", "list"],
            },
        }
    )

    CRITERIA.mkdir(parents=True, exist_ok=True)
    for item in tasks:
        (CRITERIA / f"{item['id']}.json").write_text(
            json.dumps(item["criterion"], ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    INDEX.write_text(json.dumps(tasks, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"критериев: {len(tasks)}")
    for item in tasks:
        print(f"{item['id']}|{item['task']}")
    return 0


def judge() -> int:
    tasks = json.loads(INDEX.read_text(encoding="utf-8"))
    accepted = correct = 0
    rows = []
    for item in tasks:
        journal = ROOT / "runs" / "accept" / f"h5-{item['id']}.bin"
        if not journal.exists():
            rows.append(f"{item['id'][:22]:22} —")
            continue
        records, _tail, _problems = accept.parse_journal(journal.read_bytes())
        ok, _r = accept.check(item["criterion"], records)
        answers = [rest for kind, rest in accept.events(records) if kind == "run/end"]
        text = (answers[-1] if answers else "").lower()
        blocked = any(kind == "run/blocked" for kind, _ in accept.events(records))
        if item["answer"] == "blocked":
            hit = blocked
        elif item.get("items"):
            hit = all(str(part).lower() in text for part in item["items"])
        else:
            hit = str(item["answer"]).lower() in text
        stall = any(k == "run/blocked" and "застой" in r for k, r in accept.events(records))
        steps = sum(1 for kind, _ in accept.events(records) if kind == "step")
        accepted += 1 if ok else 0
        correct += 1 if hit else 0
        rows.append(
            f"{item['id'][:22]:22} {'PASS' if ok else 'FAIL':5} {'верно' if hit else 'НЕВЕРНО':8} "
            f"шагов {steps:>2}{' застой' if stall else ''}  ответ: {text[:60]}"
        )
    report = (
        "# Трудные задачи: много файлов, ноль, отсутствие данных\n\n"
        + "\n".join(rows)
        + f"\n\nпринято: {accepted} из {len(tasks)}; совпало с ключом: {correct} из {len(tasks)}\n"
    )
    (ROOT / "research" / "outputs" / "history5-baseline.txt").write_text(report, encoding="utf-8")
    print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="трудные задачи из истории")
    parser.add_argument("--emit", action="store_true")
    parser.add_argument("--judge", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.emit:
        return emit()
    if args.judge:
        return judge()
    print("укажи --emit или --judge", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
