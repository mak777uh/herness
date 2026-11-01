"""history_tasks — задачи из собственной истории харнесса, с ответами, которые можно проверить.

Идея владельца: задач не надо придумывать — в репозитории тысячи настоящих, с историей. Здесь они
извлекаются из четырёх источников, и **ключ к каждой берётся из того же источника**, а не пишется
рукой:

  утверждения   CLAIMS.md            → «какой тип свидетельства у C-0123»
  отказы        lab/failures/*.md    → «к какому классу относится F-0033»
  журналы       runs/accept/*.bin    → «чем закончился прогон <имя>: DONE / отказ / молчание»
  коммиты       git log              → «сколько файлов изменено в коммите <sha7>»

    python bin/history_tasks.py               # записать lab/p27/history/dataset.json
    python bin/history_tasks.py --limit 40    # ограничить число задач на источник
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, ".")
from bin import accept  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "lab" / "p27" / "history" / "dataset.json"


def claim_tasks(limit: int) -> list[dict]:
    text = (ROOT / "CLAIMS.md").read_text(encoding="utf-8")
    tasks = []
    for line in text.splitlines():
        match = re.match(r"\| (C-\d{4}) \| (.+?) \| (\w+) \|", line)
        if not match:
            continue
        ident, statement, kind = match.groups()
        tasks.append(
            {
                "id": f"T-claim-{ident}",
                "source": "CLAIMS.md",
                "task": f"Какой тип свидетельства у утверждения {ident}? Ответь одним словом.",
                "answer": kind,
                "criterion": {
                    "task": f"назвать тип свидетельства {ident}",
                    "require_status": "done",
                    "require_commit": True,
                    "max_steps": 14,
                    "max_allowance": 0.05,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": ident,
                },
            }
        )
    return tasks[:limit] if limit else tasks


def failure_tasks(limit: int) -> list[dict]:
    tasks = []
    for path in sorted((ROOT / "lab" / "failures").glob("F-*.md")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^class:\s*(\S+)", text, re.MULTILINE)
        if not match:
            continue
        tasks.append(
            {
                "id": f"T-fail-{path.stem}",
                "source": "lab/failures",
                "task": f"К какому классу относится отказ {path.stem}? Ответь одним словом из файла.",
                "answer": match.group(1),
                "criterion": {
                    "task": f"назвать класс отказа {path.stem}",
                    "require_status": "done",
                    "require_commit": True,
                    "max_steps": 12,
                    "max_allowance": 0.05,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": path.stem,
                },
            }
        )
    return tasks[:limit] if limit else tasks


def journal_tasks(limit: int) -> list[dict]:
    tasks = []
    for path in sorted((ROOT / "runs" / "accept").glob("*.bin"))[: limit or None]:
        try:
            records, _tail, _problems = accept.parse_journal(path.read_bytes())
        except Exception:  # noqa: BLE001
            continue
        kinds = [kind for kind, _ in accept.events(records)]
        if "run/blocked" in kinds:
            answer = "blocked"
        elif "claim/anchored" in kinds:
            answer = "done"
        else:
            answer = "unverified"
        tasks.append(
            {
                "id": f"T-journal-{path.stem}",
                "source": "runs/accept",
                "task": (
                    f"Прогон {path.stem} записан в журнал. Определи по журналу, чем он закончился: "
                    "done, blocked или unverified. Ответь одним словом."
                ),
                "answer": answer,
                "criterion": {
                    "task": f"определить исход прогона {path.stem}",
                    "require_status": "done",
                    "require_commit": True,
                    "max_steps": 14,
                    "max_allowance": 0.05,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": "run/",
                },
            }
        )
    return tasks


def commit_tasks(limit: int) -> list[dict]:
    try:
        log = subprocess.run(
            ["git", "log", "--pretty=%h %s", "-n", str(limit or 30)],
            capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
        )
    except Exception:  # noqa: BLE001
        return []
    if log.returncode != 0:
        return []
    tasks = []
    for line in log.stdout.splitlines():
        if " " not in line:
            continue
        sha, subject = line.split(" ", 1)
        if not subject.strip():
            continue
        tasks.append(
            {
                "id": f"T-commit-{sha}",
                "source": "git log",
                "task": (
                    f"В репозитории есть коммит {sha}. Найди его описание (первую строку сообщения) "
                    "и ответь ровно этой строкой."
                ),
                "answer": subject.strip(),
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
    return tasks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="задачи из истории харнесса")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    groups = {
        "claims": claim_tasks(args.limit),
        "failures": failure_tasks(args.limit),
        "journals": journal_tasks(args.limit),
        "commits": commit_tasks(args.limit),
    }
    tasks = [task for group in groups.values() for task in group]
    if not tasks:
        print("задач не нашлось", file=sys.stderr)
        return 2

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "schema": 1,
                "note": (
                    "Задачи из собственной истории. Ключ извлечён из того же источника, что и задача, "
                    "поэтому его нельзя «подогнать»: тип утверждения берётся из CLAIMS.md, класс отказа "
                    "из файла отказа, исход прогона из журнала, описание коммита из git."
                ),
                "counts": {name: len(group) for name, group in groups.items()},
                "tasks": tasks,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"записано: {OUT.relative_to(ROOT)}; задач {len(tasks)}")
    for name, group in groups.items():
        print(f"  {name}: {len(group)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
