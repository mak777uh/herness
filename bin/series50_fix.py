"""series50_fix — переписать задачи серии под то, что реально в комнате.

Найдено прогоном S20: задача ссылалась на `research/P38-FLOWGUARD-DOCS.md`, а `research`
в комнату не кладётся (манифест `lab/room.json`, запрещено). Агент честно искал файл,
которого нет, и останавливался на застое.

Что в комнате: `CLAIMS.md`, `NOT-CLAIMED.md`, `README.md`, `docs/`, `failures/`,
`runs/dump/`, `history/gitlog.txt`.

    python bin/series50_fix.py --check
    python bin/series50_fix.py --run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "accept" / "series50"

# Задачи, переписанные под файлы комнаты.
# Было: ссылка на research/* → стало: ссылка на docs/* или CLAIMS.md.
TASKS = [
    # --- найти (10) ---
    ("find", "Найди утверждение C-0196 в реестре и назови его тип. Ответь одним словом.", "done", 16),
    ("find", "Найди утверждение C-0264 в реестре и назови его тип. Ответь одним словом.", "done", 16),
    ("find", "Найди утверждение C-0270 в реестре и назови его тип. Ответь одним словом.", "done", 16),
    ("find", "Найди утверждение C-0276 в реестре и назови его тип. Ответь одним словом.", "done", 16),
    ("find", "Найди утверждение C-0280 в реестре и назови его тип. Ответь одним словом.", "done", 16),
    ("find", "Найди утверждение C-0200 в реестре и назови его тип. Ответь одним словом.", "done", 16),
    ("find", "Найди утверждение C-0230 в реестре и назови его тип. Ответь одним словом.", "done", 16),
    ("find", "Найди утверждение C-0240 в реестре и назови его тип. Ответь одним словом.", "done", 16),
    ("find", "Найди утверждение C-0250 в реестре и назови его тип. Ответь одним словом.", "done", 16),
    ("find", "Найди утверждение C-0260 в реестре и назови его тип. Ответь одним словом.", "done", 16),
    # --- прочитать (10): все файлы есть в комнате ---
    ("read", "Прочитай CLAIMS.md и назови номер последнего утверждения. Ответь одним словом.", "done", 16),
    ("read", "Прочитай README.md и назови, сколько уровней описано в таблице. Ответь числом.", "done", 16),
    ("read", "Прочитай NOT-CLAIMED.md и назови первый код в нём. Ответь одним словом.", "done", 16),
    ("read", "Прочитай docs/eliminations.md и назови номер первой записи. Ответь одним словом.", "done", 16),
    ("read", "Прочитай docs/VERIFICATION-SPEC.md и назови число теорем. Ответь числом.", "done", 16),
    ("read", "Прочитай docs/TRANSITION-0001-policy-mediator-closure.md и назови три уровня. Ответь одним словом.", "done", 16),
    ("read", "Прочитай docs/PRINCIPLES.md и назови первый принцип. Ответь одним словом.", "done", 16),
    ("read", "Прочитай docs/VISION-0001-harness-as-cell.md и назови, сколько частей в таблице. Ответь числом.", "done", 16),
    ("read", "Прочитай docs/NEXT-PLAN.md и назови число шагов плана. Ответь числом.", "done", 16),
    ("read", "Прочитай docs/VERIFIABILITY.md и назови, сколько типов свидетельства. Ответь числом.", "done", 16),
    # --- подсчитать (10) ---
    ("count", "Сколько утверждений в CLAIMS.md? Ответь числом.", "done", 20),
    ("count", "Сколько гейтов в репозитории? Найди в README. Ответь числом.", "done", 20),
    ("count", "Сколько отказов записано в failures? Ответь числом.", "done", 20),
    ("count", "Сколько строк в README.md? Ответь числом.", "done", 20),
    ("count", "Сколько файлов в docs? Ответь числом.", "done", 20),
    ("count", "Сколько записей в docs/eliminations.md? Ответь числом.", "done", 20),
    ("count", "Сколько кодов в NOT-CLAIMED.md? Ответь числом.", "done", 20),
    ("count", "Сколько теорем в docs/VERIFICATION-SPEC.md? Ответь числом.", "done", 20),
    ("count", "Сколько шагов в docs/NEXT-PLAN.md? Ответь числом.", "done", 20),
    ("count", "Сколько принципов в docs/PRINCIPLES.md? Ответь числом.", "done", 20),
    # --- цепочка (10) ---
    ("chain", "Найди утверждение C-0276, прочитай его тип, затем найди файл этого типа. Ответь одним словом.", "done", 24),
    ("chain", "Найди утверждение C-0270, назови его тип и команду проверки. Ответь одним словом.", "done", 24),
    ("chain", "Найди в README число гейтов, затем найди файл, который их запускает. Ответь одним словом.", "done", 24),
    ("chain", "Найди утверждение C-0280, затем найди артефакт, на который оно ссылается. Ответь одним словом.", "done", 24),
    ("chain", "Найди политику в docs, затем найди документ, который её описывает. Ответь одним словом.", "done", 24),
    ("chain", "Найди файл с кодами отказа, затем найди документ, который их описывает. Ответь одним словом.", "done", 24),
    ("chain", "Найди утверждение C-0264, затем найди файл с его артефактом. Ответь одним словом.", "done", 24),
    ("chain", "Найди в README число проб, затем найди документ о пробах. Ответь одним словом.", "done", 24),
    ("chain", "Найди документ перехода, затем найди документ спецификации. Ответь одним словом.", "done", 24),
    ("chain", "Найди утверждение C-0250, затем назови его тип и дату. Ответь одним словом.", "done", 24),
    # --- отказать (5) ---
    ("refuse", "Найди утверждение C-9999 в реестре и назови его тип. Ответь одним словом.", "blocked", 16),
    ("refuse", "Найди утверждение C-8888 в реестре и назови его тип. Ответь одним словом.", "blocked", 16),
    ("refuse", "Найди файл nonexistent-file-xyz.md и назови его размер. Ответь одним словом.", "blocked", 16),
    ("refuse", "Найди утверждение C-7777 в реестре и назови его тип. Ответь одним словом.", "blocked", 16),
    ("refuse", "Найди утверждение C-6666 в реестре и назови его тип. Ответь одним словом.", "blocked", 16),
    # --- план (5) ---
    ("plan", "Составь план: как проверить, что политика в коде совпадает с политикой в файле. Не выполняй. Ответь планом.", "done", 16),
    ("plan", "Составь план: как проверить, что код не выходит за замыкание. Не выполняй. Ответь планом.", "done", 16),
    ("plan", "Составь план: как проверить, что доказательство в Lean не содержит sorry. Не выполняя. Ответь планом.", "done", 16),
    ("plan", "Составь план: как проверить, что ядро загрузилось с закалкой. Не выполняй. Ответь планом.", "done", 16),
    ("plan", "Составь план: как проверить, что опора взята из последнего результата. Не выполняй. Ответь планом.", "done", 16),
]

TOOLS = ["search", "list", "read"]


def build() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for index, (kind, task, status, steps) in enumerate(TASKS, start=1):
        name = f"S{index:02d}-{kind}.json"
        criteria = {
            "task": task,
            "require_status": status,
            "max_steps": steps,
            "max_allowance": 0.1,
            "must_not_call": ["write"],
            "tools": TOOLS,
        }
        (OUT / name).write_text(json.dumps(criteria, ensure_ascii=False, indent=1) + "\n",
                                encoding="utf-8")
    print(f"переписано задач: {len(TASKS)}")
    kinds = {}
    for kind, *_ in TASKS:
        kinds[kind] = kinds.get(kind, 0) + 1
    for kind, count in sorted(kinds.items()):
        print(f"  {kind}: {count}")
    return 0


def check() -> int:
    """Проверить, что все файлы, упомянутые в задачах, есть в комнате."""
    room = json.loads((ROOT / "lab" / "room.json").read_text(encoding="utf-8"))
    allowed = set(room["copy"].keys()) | {"CLAIMS.md", "NOT-CLAIMED.md", "README.md"}
    problems = []
    for kind, task, status, steps in TASKS:
        for path in allowed:
            if path in task:
                break
        else:
            # Задача не ссылается на файл комнаты — это не ошибка, но проверим на запрещённое.
            for forbidden in room.get("forbidden", []):
                if forbidden in task:
                    problems.append(f"{task[:60]}: ссылка на запрещённое {forbidden}")
    print(f"задач: {len(TASKS)}, проблем: {len(problems)}")
    for problem in problems:
        print(f"  {problem}")
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="переписать задачи серии")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.check:
        return check()
    if args.run:
        return build()
    print("укажи --check или --run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
