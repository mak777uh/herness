"""history_tasks3 — задачи, где нужен счёт и сравнение по комнате, а не одна строка.

Ключ считается из тех же файлов, что видит агент (failures/, runs/dump, history/gitlog.txt).
Такие задачи проверяют не поиск, а умение собрать ответ из нескольких источников и остановиться.

    python bin/history_tasks3.py --emit
    python bin/history_tasks3.py --judge
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
CRITERIA = ROOT / "accept" / "history3"
INDEX = ROOT / "runs" / "accept" / "history3-index.json"


def failures() -> list[tuple[str, str]]:
    out = []
    for path in sorted((ROOT / "lab" / "failures").glob("F-*.md")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^class:\s*(\S+)", text, re.MULTILINE)
        if match:
            out.append((path.stem, match.group(1)))
    return out


def dumps() -> list[Path]:
    return sorted((ROOT / "runs" / "dump").glob("*.txt"))


def gitlog() -> list[tuple[str, str]]:
    path = ROOT / "history" / "gitlog.txt"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if " " in line:
            sha, subject = line.split(" ", 1)
            out.append((sha, subject.strip()))
    return out


def emit() -> int:
    tasks = []

    items = failures()
    counts: dict[str, int] = {}
    for _stem, klass in items:
        counts[klass] = counts.get(klass, 0) + 1
    top_class, top_count = max(counts.items(), key=lambda pair: (pair[1], pair[0]))
    tasks.append(
        {
            "id": "H3-fail-class-count",
            "task": (
                "В каталоге failures лежит по файлу на каждый отказ. Определи, какой класс отказов "
                "встречается чаще всего, и ответь строкой «класс N», где N — сколько таких файлов."
            ),
            "answer": f"{top_class} {top_count}",
            "criterion": {
                "task": "назвать самый частый класс отказов и их число",
                "require_status": "done",
                "require_commit": True,
                "max_steps": 20,
                "max_allowance": 0.05,
                "must_not_call": ["write"],
                "tools": ["search", "read", "list"],
                "anchor_regex": "failures|F-0",
                "min_objects": 3,
            },
        }
    )

    blocked = 0
    for path in dumps():
        kinds = [line.split(":", 1)[0] for line in path.read_text(encoding="utf-8").splitlines() if line]
        if "run/blocked" in kinds:
            blocked += 1
    tasks.append(
        {
            "id": "H3-blocked-count",
            "task": (
                "В runs/dump лежат выгрузки прогонов. Посчитай, в скольких выгрузках есть событие "
                "run/blocked, и ответь одним числом."
            ),
            "answer": str(blocked),
            "criterion": {
                "task": "посчитать выгрузки с run/blocked",
                "require_status": "done",
                "require_commit": True,
                "max_steps": 20,
                "max_allowance": 0.05,
                "must_not_call": ["write"],
                "tools": ["search", "read", "list"],
                "anchor_regex": "run/blocked",
            },
        }
    )

    target = "ADR-0052"
    owners = [
        stem
        for stem, _klass in items
        if target in (ROOT / "lab" / "failures" / f"{stem}.md").read_text(encoding="utf-8")
    ]
    if owners:
        tasks.append(
            {
                "id": "H3-adr-link",
                "task": (
                    f"Найди в каталоге failures отказ, в тексте которого упомянуто решение {target}. "
                    "Ответь его номером (F-XXXX)."
                ),
                "answer": owners[0],
                "criterion": {
                    "task": f"найти отказ, связанный с {target}",
                    "require_status": "done",
                    "require_commit": True,
                    "max_steps": 20,
                    "max_allowance": 0.05,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": r"F-0\d{3}",
                },
            }
        )

    commits = gitlog()
    if len(commits) > 3:
        # Два несмежных коммита: сколько строк между ними в истории.
        left, right = commits[2][0], commits[9][0]
        tasks.append(
            {
                "id": "H3-commit-span",
                "task": (
                    f"В history/gitlog.txt коммиты идут от новых к старым. Посчитай, сколько коммитов "
                    f"расположено строго между {left} и {right} (не считая обоих), и ответь числом."
                ),
                "answer": "6",
                "criterion": {
                    "task": f"посчитать коммиты между {left} и {right}",
                    "require_status": "done",
                    "require_commit": True,
                    "max_steps": 20,
                    "max_allowance": 0.05,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": left,
                },
            }
        )

    # Считать строки во всех 93 выгрузках в пределах 20 шагов нельзя (F-0040), поэтому берём
    # размер файла: он виден из одного list, а максимум уникален.
    lengths = {path.stem: path.stat().st_size for path in dumps()}
    best = max(lengths.values())
    tied = sorted(stem for stem, value in lengths.items() if value == best)
    tasks.append(
        {
            "id": "H3-longest-run",
            "task": (
                "В runs/dump лежат выгрузки прогонов. Найди выгрузку самого большого размера в байтах "
                "и ответь её именем без расширения."
            ),
            "answer": tied[0],
            "criterion": {
                "task": "назвать самый длинный прогон",
                "require_status": "done",
                "require_commit": True,
                "max_steps": 20,
                "max_allowance": 0.05,
                "must_not_call": ["write"],
                "tools": ["search", "read", "list"],
                "anchor_regex": __import__("re").escape(tied[0]),
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
        journal = ROOT / "runs" / "accept" / f"h3-{item['id']}.bin"
        if not journal.exists():
            rows.append(f"{item['id'][:28]:28} —")
            continue
        records, _tail, _problems = accept.parse_journal(journal.read_bytes())
        ok, _r = accept.check(item["criterion"], records)
        answers = [rest for kind, rest in accept.events(records) if kind == "run/end"]
        text = (answers[-1] if answers else "").lower()
        hit = str(item["answer"]).lower() in text
        stall = any(k == "run/blocked" and "застой" in r for k, r in accept.events(records))
        loop = any(k == "run/blocked" and "петля" in r for k, r in accept.events(records))
        steps = sum(1 for kind, _ in accept.events(records) if kind == "step")
        accepted += 1 if ok else 0
        correct += 1 if hit else 0
        rows.append(
            f"{item['id'][:28]:28} {'PASS' if ok else 'FAIL':5} {'верно' if hit else 'НЕВЕРНО':8} "
            f"шагов {steps:>2}{' застой' if stall else ''}{' петля' if loop else ''}"
        )
    report = (
        "# Задачи на счёт и сравнение по комнате\n\n"
        + "\n".join(rows)
        + f"\n\nпринято: {accepted} из {len(tasks)}; совпало с ключом: {correct} из {len(tasks)}\n"
    )
    (ROOT / "research" / "outputs" / "history3-baseline.txt").write_text(report, encoding="utf-8")
    print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="задачи на счёт по комнате")
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
