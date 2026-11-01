"""baseline_history2 — задачи, где ответ не в реестре, а в истории прогонов и коммитов.

Комната для этой серии содержит: runs/dump (журналы текстом) и history/gitlog.txt (описания
коммитов). Семейства: исход прогона (done/blocked/unverified) и описание коммита.

    python bin/baseline_history2.py --emit
    python bin/baseline_history2.py --judge
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from bin import accept  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DUMPS = ROOT / "runs" / "dump"
GITLOG = ROOT / "history" / "gitlog.txt"
CRITERIA = ROOT / "accept" / "history2"
INDEX = ROOT / "runs" / "accept" / "history2-index.json"

PICK_JOURNALS = ["musique-0", "journal-set-3", "journal-hard", "journal-set-7"]
PICK_FILES = ["README.md", "NOT-CLAIMED.md", "docs/STATUS.md"]


def outcome_of(path: Path) -> str:
    kinds = [line.split(":", 1)[0] for line in path.read_text(encoding="utf-8").splitlines() if line]
    if "run/blocked" in kinds:
        return "blocked"
    if "claim/anchored" in kinds:
        return "done"
    return "unverified"


def git_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not GITLOG.exists():
        return mapping
    for line in GITLOG.read_text(encoding="utf-8").splitlines():
        if " " not in line:
            continue
        sha, subject = line.split(" ", 1)
        mapping[sha] = subject.strip()
    return mapping


def emit() -> int:
    tasks = []
    for stem in PICK_JOURNALS:
        path = DUMPS / f"{stem}.txt"
        if not path.exists():
            print(f"нет выгрузки {stem}", file=sys.stderr)
            continue
        tasks.append(
            {
                "id": f"H2-journal-{stem}",
                "task": (
                    f"В каталоге runs лежит выгрузка прогона {stem}.txt. Определи по ней, чем закончился "
                    "прогон: done, blocked или unverified. Ответь одним словом."
                ),
                "answer": outcome_of(path),
                "criterion": {
                    "task": f"определить исход прогона {stem}",
                    "require_status": "done",
                    "require_commit": True,
                    "max_steps": 14,
                    "max_allowance": 0.05,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": stem[:10],
                },
            }
        )

    commits = list(git_map().items())
    for sha, subject in commits[3:6]:
        tasks.append(
            {
                "id": f"H2-commit-{sha}",
                "task": (
                    f"В history/gitlog.txt лежит история коммитов. Найди строку с коммитом {sha} и ответь "
                    "его описанием (тем, что идёт после хеша)."
                ),
                "answer": subject,
                "criterion": {
                    "task": f"назвать описание коммита {sha}",
                    "require_status": "done",
                    "require_commit": True,
                    "max_steps": 14,
                    "max_allowance": 0.05,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": sha,
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
        journal = ROOT / "runs" / "accept" / f"h2-{item['id']}.bin"
        if not journal.exists():
            rows.append(f"{item['id'][:34]:34} —")
            continue
        records, _tail, _problems = accept.parse_journal(journal.read_bytes())
        ok, _rows = accept.check(item["criterion"], records)
        answers = [rest for kind, rest in accept.events(records) if kind == "run/end"]
        text = (answers[-1] if answers else "").lower()
        hit = str(item["answer"]).lower() in text
        accepted += 1 if ok else 0
        correct += 1 if hit else 0
        rows.append(f"{item['id'][:34]:34} {'PASS' if ok else 'FAIL':5} {'верно' if hit else 'НЕВЕРНО'}")
    report = "\n".join(rows) + f"\n\nпринято: {accepted} из {len(tasks)}; ответ верен: {correct} из {len(tasks)}\n"
    (ROOT / "research" / "outputs" / "history2-baseline.txt").write_text(
        "# Задачи по истории прогонов и коммитов\n\n" + report, encoding="utf-8"
    )
    print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="вторая серия задач из истории")
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
