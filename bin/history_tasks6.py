"""history_tasks6 — серия «ответ в одном вызове».

Смысл: проверить, берёт ли модель готовый ответ, когда он уже лежит в последнем результате.
Каждая задача решается одним-двумя поисками; ключ считается по тем же файлам.

    python bin/history_tasks6.py --emit
    python bin/history_tasks6.py --judge
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
CRITERIA = ROOT / "accept" / "history6"
INDEX = ROOT / "runs" / "accept" / "history6-index.json"


def dumps() -> list[Path]:
    return sorted((ROOT / "runs" / "dump").glob("*.txt"))


def tools() -> list[str]:
    found = set()
    for path in dumps():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"tool/call: ([a-z]+)", line)
            if match:
                found.add(match.group(1))
    return sorted(found)


def classes() -> list[str]:
    found = set()
    for path in (ROOT / "lab" / "failures").glob("F-*.md"):
        match = re.search(r"^class:\s*(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            found.add(match.group(1))
    return sorted(found)


def emit() -> int:
    tasks = [
        {
            "id": "H6-tools",
            "task": (
                "Сколько РАЗНЫХ имён встречается после «tool/call:» во всех выгрузках runs/dump? "
                "Ответь одним числом."
            ),
            "answer": str(len(tools())),
            "items": [str(len(tools()))],
            "criterion": {
                "task": "посчитать разные вызовы в выгрузках",
                "require_status": "done",
                "require_commit": True,
                "max_steps": 16,
                "max_allowance": 0.05,
                "must_not_call": ["write"],
                "tools": ["search", "read", "list"],
                "anchor_regex": "tool/call",
            },
        },
        {
            "id": "H6-dump-count",
            "task": "Сколько выгрузок лежит в runs/dump? Ответь одним числом.",
            "answer": str(len(dumps())),
            "items": [str(len(dumps()))],
            "criterion": {
                "task": "посчитать выгрузки",
                "require_status": "done",
                "require_commit": True,
                "max_steps": 12,
                "max_allowance": 0.05,
                "must_not_call": ["write"],
                "tools": ["search", "read", "list"],
                "anchor_regex": r"dump|\.txt",
            },
        },
        {
            "id": "H6-classes",
            "task": "Сколько РАЗНЫХ классов отказов встречается в каталоге failures? Ответь одним числом.",
            "answer": str(len(classes())),
            "items": [str(len(classes()))],
            "criterion": {
                "task": "посчитать разные классы отказов",
                "require_status": "done",
                "require_commit": True,
                "max_steps": 16,
                "max_allowance": 0.05,
                "must_not_call": ["write"],
                "tools": ["search", "read", "list"],
                "anchor_regex": "class",
            },
        },
        {
            "id": "H6-blocked",
            "task": "В скольких выгрузках runs/dump есть событие run/blocked? Ответь одним числом.",
            "answer": "1",
            "items": ["1"],
            "criterion": {
                "task": "посчитать выгрузки с run/blocked",
                "require_status": "done",
                "require_commit": True,
                "max_steps": 12,
                "max_allowance": 0.05,
                "must_not_call": ["write"],
                "tools": ["search", "read", "list"],
                "anchor_regex": "run/blocked",
            },
        },
        {
            "id": "H6-starts",
            "task": "В скольких выгрузках runs/dump есть событие run/start? Ответь одним числом.",
            "answer": str(sum(1 for path in dumps() if "run/start" in path.read_text(encoding="utf-8"))),
            "items": [str(len(dumps()))],
            "criterion": {
                "task": "посчитать выгрузки с run/start",
                "require_status": "done",
                "require_commit": True,
                "max_steps": 12,
                "max_allowance": 0.05,
                "must_not_call": ["write"],
                "tools": ["search", "read", "list"],
                "anchor_regex": "run/start",
            },
        },
    ]

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
        journal = ROOT / "runs" / "accept" / f"h6-{item['id']}.bin"
        if not journal.exists():
            rows.append(f"{item['id'][:18]:18} —")
            continue
        records, _tail, _problems = accept.parse_journal(journal.read_bytes())
        ok, _r = accept.check(item["criterion"], records)
        answers = [rest for kind, rest in accept.events(records) if kind == "run/end"]
        text = (answers[-1] if answers else "").lower()
        finished = "шаги кончились" not in text and "провайдер не дал" not in text
        parts = item.get("items") or [item["answer"]]
        hit = finished and all(
            re.search(rf"(?<![0-9]){re.escape(str(part))}(?![0-9])", text) for part in parts
        )
        stall = any(k == "run/blocked" and "застой" in r for k, r in accept.events(records))
        steps = sum(1 for kind, _ in accept.events(records) if kind == "step")
        accepted += 1 if ok else 0
        correct += 1 if hit else 0
        rows.append(
            f"{item['id'][:18]:18} {'PASS' if ok else 'FAIL':5} {'верно' if hit else 'НЕВЕРНО':8} "
            f"шагов {steps:>2}{' застой' if stall else ''}  ответ: {text[:50]}"
        )
    report = (
        "# Серия «ответ в одном вызове»\n\n"
        + "\n".join(rows)
        + f"\n\nпринято: {accepted} из {len(tasks)}; совпало с ключом: {correct} из {len(tasks)}\n"
    )
    (ROOT / "research" / "outputs" / "history6-baseline.txt").write_text(report, encoding="utf-8")
    print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="серия «ответ в одном вызове»")
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
