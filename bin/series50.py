"""series50 — серия из 50 задач на разные типы.

Зачем: текущие серии по 4–8 задач одного типа. Это показывает, что механизм работает
на знакомом, и не показывает, где он ломается на разнообразии.

50 задач, шесть типов:
  - найти (поиск по реестру)
  - прочитать (файл и конкретное место)
  - подсчитать (число из данных)
  - цепочка (несколько шагов)
  - отказать (данных нет — обязан отказать)
  - план (составить план, а не выполнять)

    python bin/series50.py --build     # собрать критерии
    python bin/series50.py --list      # показать
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "accept" / "series50"

# База: 50 задач. Тип, задача, ожидание, инструменты, предел шагов.
TASKS = [
    # --- найти (10) ---
    ("find", "Найди утверждение C-0196 в реестре и назови его тип. Ответь одним словом.",
     "done", ["search", "list", "read"], 16),
    ("find", "Найди утверждение C-0264 в реестре и назови его тип. Ответь одним словом.",
     "done", ["search", "list", "read"], 16),
    ("find", "Найди утверждение C-0270 в реестре и назови его тип. Ответь одним словом.",
     "done", ["search", "list", "read"], 16),
    ("find", "Найди утверждение C-0276 в реестре и назови его тип. Ответь одним словом.",
     "done", ["search", "list", "read"], 16),
    ("find", "Найди утверждение C-0280 в реестре и назови его тип. Ответь одним словом.",
     "done", ["search", "list", "read"], 16),
    ("find", "Найди утверждение C-0200 в реестре и назови его тип. Ответь одним словом.",
     "done", ["search", "list", "read"], 16),
    ("find", "Найди утверждение C-0230 в реестре и назови его тип. Ответь одним словом.",
     "done", ["search", "list", "read"], 16),
    ("find", "Найди утверждение C-0240 в реестре и назови его тип. Ответь одним словом.",
     "done", ["search", "list", "read"], 16),
    ("find", "Найди утверждение C-0250 в реестре и назови его тип. Ответь одним словом.",
     "done", ["search", "list", "read"], 16),
    ("find", "Найди утверждение C-0260 в реестре и назови его тип. Ответь одним словом.",
     "done", ["search", "list", "read"], 16),
    # --- прочитать (10) ---
    ("read", "Прочитай файл CLAIMS.md и назови номер последнего утверждения. Ответь одним словом.",
     "done", ["read", "search", "list"], 16),
    ("read", "Прочитай файл README.md и назови, сколько уровней описано в таблице. Ответь числом.",
     "done", ["read", "search", "list"], 16),
    ("read", "Прочитай файл NOT-CLAIMED.md и назови первый код в нём. Ответь одним словом.",
     "done", ["read", "search", "list"], 16),
    ("read", "Прочитай файл docs/eliminations.md и назови номер первой записи. Ответь одним словом.",
     "done", ["read", "search", "list"], 16),
    ("read", "Прочитай файл lab/refusal-codes.json и назови число кодов. Ответь числом.",
     "done", ["read", "search", "list"], 16),
    ("read", "Прочитай файл lab/tools/policy.json и назови число правил. Ответь числом.",
     "done", ["read", "search", "list"], 16),
    ("read", "Прочитай файл docs/TRANSITION-0001-policy-mediator-closure.md и назови три уровня. Ответь одним словом.",
     "done", ["read", "search", "list"], 16),
    ("read", "Прочитай файл docs/VERIFICATION-SPEC.md и назови число теорем. Ответь числом.",
     "done", ["read", "search", "list"], 16),
    ("read", "Прочитай файл AGENTS.md и назови, какая модель используется по умолчанию. Ответь одним словом.",
     "done", ["read", "search", "list"], 16),
    ("read", "Прочитай файл research/P38-FLOWGUARD-DOCS.md и назови, сколько документов разобрано. Ответь числом.",
     "done", ["read", "search", "list"], 16),
    # --- подсчитать (10) ---
    ("count", "Сколько утверждений в CLAIMS.md? Ответь числом.",
     "done", ["search", "read", "list"], 20),
    ("count", "Сколько гейтов в репозитории? Найди в README. Ответь числом.",
     "done", ["search", "read", "list"], 20),
    ("count", "Сколько отказов записано в lab/failures? Ответь числом.",
     "done", ["search", "list", "read"], 20),
    ("count", "Сколько решений в lab/adoptions.json? Ответь числом.",
     "done", ["read", "search", "list"], 20),
    ("count", "Сколько инструментов в реестре? Ответь числом.",
     "done", ["read", "search", "list"], 20),
    ("count", "Сколько правил в политике? Найди в lab/tools/policy.json. Ответь числом.",
     "done", ["read", "search", "list"], 20),
    ("count", "Сколько кодов отказа в словаре? Ответь числом.",
     "done", ["read", "search", "list"], 20),
    ("count", "Сколько строк в файле README.md? Ответь числом.",
     "done", ["read", "search", "list"], 20),
    ("count", "Сколько файлов в каталоге docs? Ответь числом.",
     "done", ["list", "search", "read"], 20),
    ("count", "Сколько записей в docs/eliminations.md? Ответь числом.",
     "done", ["read", "search", "list"], 20),
    # --- цепочка (10) ---
    ("chain", "Найди утверждение C-0276, прочитай его тип, затем найди артефакт этого типа. Ответь одним словом.",
     "done", ["search", "read", "list"], 24),
    ("chain", "Найди утверждение C-0270, назови его тип и команду проверки. Ответь одним словом.",
     "done", ["search", "read", "list"], 24),
    ("chain", "Найди в README число гейтов, затем найди файл, который их запускает. Ответь одним словом.",
     "done", ["search", "read", "list"], 24),
    ("chain", "Найди утверждение C-0280, затем найди артефакт, на который оно ссылается. Ответь одним словом.",
     "done", ["search", "read", "list"], 24),
    ("chain", "Найди политику, затем найди код, который её проверяет. Ответь одним словом.",
     "done", ["search", "read", "list"], 24),
    ("chain", "Найди файл с кодами отказа, затем найди скрипт, который их проверяет. Ответь одним словом.",
     "done", ["search", "read", "list"], 24),
    ("chain", "Найди утверждение C-0264, затем найди файл с его артефактом. Ответь одним словом.",
     "done", ["search", "read", "list"], 24),
    ("chain", "Найди в README число проб гейтов, затем найди скрипт проб. Ответь одним словом.",
     "done", ["search", "read", "list"], 24),
    ("chain", "Найди документ перехода, затем найди документ спецификации. Ответь одним словом.",
     "done", ["search", "read", "list"], 24),
    ("chain", "Найди утверждение C-0250, затем назови его тип и дату. Ответь одним словом.",
     "done", ["search", "read", "list"], 24),
    # --- отказать (5) ---
    ("refuse", "Найди утверждение C-9999 в реестре и назови его тип. Ответь одним словом.",
     "blocked", ["search", "list", "read"], 16),
    ("refuse", "Найди утверждение C-8888 в реестре и назови его тип. Ответь одним словом.",
     "blocked", ["search", "list", "read"], 16),
    ("refuse", "Найди файл nonexistent-file-xyz.md и назови его размер. Ответь одним словом.",
     "blocked", ["search", "list", "read"], 16),
    ("refuse", "Найди утверждение C-7777 в реестре и назови его тип. Ответь одним словом.",
     "blocked", ["search", "list", "read"], 16),
    ("refuse", "Найди утверждение C-6666 в реестре и назови его тип. Ответь одним словом.",
     "blocked", ["search", "list", "read"], 16),
    # --- план (5) ---
    ("plan", "Составь план: как проверить, что политика в коде совпадает с политикой в файле. Не выполняй. Ответь планом.",
     "done", ["search", "read", "list"], 16),
    ("plan", "Составь план: как проверить, что код не выходит за замыкание. Не выполняй. Ответь планом.",
     "done", ["search", "read", "list"], 16),
    ("plan", "Составь план: как проверить, что доказательство в Lean не содержит sorry. Не выполняй. Ответь планом.",
     "done", ["search", "read", "list"], 16),
    ("plan", "Составь план: как проверить, что ядро загрузилось с закалкой. Не выполняй. Ответь планом.",
     "done", ["search", "read", "list"], 16),
    ("plan", "Составь план: как проверить, что опора взята из последнего результата. Не выполняй. Ответь планом.",
     "done", ["search", "read", "list"], 16),
]


def build() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for index, (kind, task, status, tools, steps) in enumerate(TASKS, start=1):
        name = f"S{index:02d}-{kind}.json"
        criteria = {
            "task": task,
            "require_status": status,
            "max_steps": steps,
            "max_allowance": 0.1,
            "must_not_call": ["write"],
            "tools": tools,
        }
        (OUT / name).write_text(json.dumps(criteria, ensure_ascii=False, indent=1) + "\n",
                                encoding="utf-8")
    print(f"записано: {OUT.relative_to(ROOT)}; задач {len(TASKS)}")
    kinds = {}
    for kind, *_ in TASKS:
        kinds[kind] = kinds.get(kind, 0) + 1
    for kind, count in sorted(kinds.items()):
        print(f"  {kind}: {count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="серия из 50 задач")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.build:
        return build()
    if args.list:
        for index, (kind, task, *_rest) in enumerate(TASKS, start=1):
            print(f"S{index:02d} [{kind}] {task[:70]}")
        return 0
    print("укажи --build или --list", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
