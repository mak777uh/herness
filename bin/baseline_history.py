"""baseline_history — 8 задач из собственной истории для точки отсчёта.

Берём только то, что реально лежит в комнате (CLAIMS.md, docs/, failures/), иначе задача
непроверяема: агент физически не увидит файла. Семейства: утверждения, отказы, решения.

    python bin/baseline_history.py --emit     # записать accept/history/*.json и список задач
    python bin/baseline_history.py --judge    # сверить ответы прогонов с ключами
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
DATASET = ROOT / "lab" / "p27" / "history" / "dataset.json"
CRITERIA = ROOT / "accept" / "history"
INDEX = ROOT / "runs" / "accept" / "history-index.json"

PICK = [
    ("T-claim-C-0196", "Какой тип свидетельства у утверждения C-0196? Ответь одним словом."),
    ("T-claim-C-0205", "Какой тип свидетельства у утверждения C-0205? Ответь одним словом."),
    ("T-claim-C-0211", "Какой тип свидетельства у утверждения C-0211? Ответь одним словом."),
    ("T-fail-F-0029", "К какому классу относится отказ F-0029 в каталоге failures? Ответь одним словом."),
    ("T-fail-F-0033", "К какому классу относится отказ F-0033 в каталоге failures? Ответь одним словом."),
    ("T-fail-F-0034", "К какому классу относится отказ F-0034 в каталоге failures? Ответь одним словом."),
]


def load_tasks() -> dict[str, dict]:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    return {task["id"]: task for task in data["tasks"]}


def emit() -> int:
    tasks = load_tasks()
    chosen = []
    for ident, text in PICK:
        task = tasks.get(ident)
        if not task:
            print(f"нет задачи {ident}", file=sys.stderr)
            continue
        criterion = dict(task["criterion"])
        criterion["task"] = text
        chosen.append({"id": ident, "task": text, "answer": task["answer"], "criterion": criterion})

    adr = [task for task in tasks.values() if task["source"] == "docs/ADR"][:2]
    for task in adr:
        criterion = dict(task["criterion"])
        text = task["task"]
        chosen.append({"id": task["id"], "task": text, "answer": task["answer"], "criterion": criterion})

    CRITERIA.mkdir(parents=True, exist_ok=True)
    for item in chosen:
        (CRITERIA / f"{item['id']}.json").write_text(
            json.dumps(item["criterion"], ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    (ROOT / "runs" / "accept").mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(chosen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"критериев: {len(chosen)}")
    for item in chosen:
        print(f"{item['id']}|{item['task']}")
    return 0


def judge() -> int:
    chosen = json.loads(INDEX.read_text(encoding="utf-8"))
    lines = ["# Baseline на задачах из истории", "", f"{'задача':24} {'приёмка':8} {'ответ':10} ключ"]
    accepted = correct = 0
    for item in chosen:
        journal = ROOT / "runs" / "accept" / f"hist-{item['id']}.bin"
        if not journal.exists():
            lines.append(f"{item['id'][:24]:24} {'—':8} {'—':10} {item['answer'][:20]}")
            continue
        records, _tail, _problems = accept.parse_journal(journal.read_bytes())
        ok, _rows = accept.check(item["criterion"], records)
        answers = [rest for kind, rest in accept.events(records) if kind == "run/end"]
        text = (answers[-1] if answers else "").lower()
        expected = str(item["answer"]).lower()
        hit = expected in text or re.search(rf"\b{re.escape(expected)}\b", text) is not None
        accepted += 1 if ok else 0
        correct += 1 if hit else 0
        lines.append(f"{item['id'][:24]:24} {'PASS' if ok else 'FAIL':8} {'верно' if hit else 'НЕВЕРНО':10} {item['answer'][:20]}")
    lines += ["", f"принято: {accepted} из {len(chosen)}; ответ верен: {correct} из {len(chosen)}"]
    text = "\n".join(lines) + "\n"
    (ROOT / "research" / "outputs" / "history-baseline.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="baseline по истории")
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
