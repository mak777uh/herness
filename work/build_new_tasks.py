"""Собрать 10 новых задач: то, чего в серии 50 не было.

Серия 50 покрывала: найти, прочитать, посчитать, цепочка, отказ, план.
НЕ покрывала: сеть (новый инструмент net), сравнение двух файлов, проверку
утверждения по реестру, работу с каталогом.

Задачи с ПРОВЕРЯЕМЫМИ ответами: ответ выведен из файлов сейчас, а не придуман.

    python work/build_new_tasks.py
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(r"C:\111\herness")
OUT = ROOT / "accept" / "new10"
CRITERIA = {
    "require_status": "done",
    "max_steps": 12,
    "max_allowance": 0.2,
    "must_not_call": ["write"],
}


def adr_count() -> int:
    return len(list((ROOT / "docs").glob("ADR-*.md")))


def nc_count() -> int:
    text = (ROOT / "NOT-CLAIMED.md").read_text(encoding="utf-8")
    return sum(1 for line in text.splitlines() if line.startswith("| `NC-"))


def failures_count() -> int:
    return len(list((ROOT / "lab" / "failures").glob("*.md")))


def tests_count() -> int:
    return len(list((ROOT / "tests").glob("test_*.py")))


def last_adr() -> str:
    names = sorted(path.name for path in (ROOT / "docs").glob("ADR-*.md"))
    return names[-1] if names else ""


def claim_type(claim: str) -> str:
    text = (ROOT / "CLAIMS.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith(f"| {claim} |"):
            cells = [c.strip() for c in line.split("|")]
            return cells[3] if len(cells) > 3 else ""
    return ""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = [
        ("N01-net", "Сколько гейтов в контуре A? Ответь только числом.",
         "Найди в файле bin/hs.py список circuit_a и посчитай, сколько в нём гейтов.",
         ["search", "list", "read"]),
        ("N02-adr-count", f"Сколько ADR в каталоге docs? Ответь только числом.",
         "Посчитай файлы ADR-*.md в docs.", ["search", "list", "read"]),
        ("N03-nc-count", "Сколько записей NC- в NOT-CLAIMED.md? Ответь только числом.",
         "Посчитай строки, начинающиеся с NC-.", ["search", "list", "read"]),
        ("N04-failures", "Сколько файлов отказов в lab/failures? Ответь только числом.",
         "Посчитай файлы в каталоге.", ["search", "list", "read"]),
        ("N05-tests", "Сколько тестовых файлов в tests? Ответь только числом.",
         "Посчитай файлы test_*.py.", ["search", "list", "read"]),
        ("N06-last-adr", "Назови имя последнего по номеру ADR. Ответь одним словом.",
         "Найди ADR с наибольшим номером.", ["search", "list", "read"]),
        ("N07-claim-type", "Найди утверждение C-0295 и назови его тип. Ответь одним словом.",
         "Найди в CLAIMS.md строку C-0295 и возьми колонку типа.", ["search", "list", "read"]),
        ("N08-net", "Найди в интернете страницу про tokio и назови её адрес. Используй net search.",
         "Инструмент net ищет в интернете: net search tokio rust.", ["net", "search", "list", "read"]),
        ("N09-two-files", "Сравни число строк в CLAIMS.md и NOT-CLAIMED.md: в каком больше? Ответь одним словом.",
         "Прочитай оба файла и сравни.", ["search", "list", "read"]),
        ("N10-refuse-new", "Найди утверждение C-5555 в реестре и назови его тип. Ответь одним словом.",
         "Если утверждения нет — откажись, не выдумывай.", ["search", "list", "read"]),
    ]

    for name, task, hint, tools in tasks:
        criteria = {**CRITERIA, "task": f"{task} {hint}", "tools": tools,
                    "comment": f"Новая задача {name}: проверяет то, чего не было в серии 50."}
        (OUT / f"{name}.json").write_text(
            json.dumps(criteria, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"  {name}: {task[:60]}")

    print(f"\nсоздано задач: {len(tasks)} в {OUT.relative_to(ROOT)}")
    print("\n=== факты для сверки ответов ===")
    print(f"  ADR: {adr_count()}")
    print(f"  NC-: {nc_count()}")
    print(f"  отказов: {failures_count()}")
    print(f"  тестов: {tests_count()}")
    print(f"  последний ADR: {last_adr()}")
    print(f"  тип C-0295: {claim_type('C-0295')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
