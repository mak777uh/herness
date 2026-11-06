"""check_insights — у каждого пункта списка инсайтов есть что, зачем, как проверять и статус.

    python bin/check_insights.py [--self-test]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "research" / "INSIGHTS.md"
REQUIRED = ("**Что.**", "**Зачем.**", "**Как проверять.**", "**Статус.**")
STATUSES = ("предложено", "принято", "в работе", "готово", "отклонено")


def check(text: str) -> list[str]:
    problems = []
    blocks = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    items = [block for block in blocks if re.match(r"F-\d\d\.", block)]
    if not items:
        problems.append("пунктов вида «## F-NN.» нет")
    for block in items:
        title = block.splitlines()[0].strip()
        for marker in REQUIRED:
            if marker not in block:
                problems.append(f"{title}: нет поля {marker}")
        status = re.search(r"\*\*Статус\.\*\*\s*`([^`]+)`", block)
        if not status:
            problems.append(f"{title}: статус не в обратных кавычках")
        elif status.group(1) not in STATUSES:
            problems.append(f"{title}: неизвестный статус «{status.group(1)}»")
    return problems


def self_test() -> int:
    good = (
        "## F-01. Пример\n\n**Что.** x\n**Зачем.** y\n**Как проверять.** z\n**Статус.** `предложено`\n"
    )
    bad = "## F-02. Без проверки\n\n**Что.** x\n**Статус.** `придумано`\n"
    failures = 0
    if check(good):
        print("self-test: годный пункт отвергнут — дефект проверки")
        failures += 1
    found = check(bad)
    if len(found) < 3:
        print("self-test: негодный пункт прошёл — проверка всеядна")
        failures += 1
    print(f"self-test: {'ок' if not failures else 'ПРОВАЛ'}")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="проверка списка инсайтов")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.self_test:
        return self_test()
    problems = check(PATH.read_text(encoding="utf-8"))
    if problems:
        print("ПРОБЛЕМЫ:")
        for problem in problems:
            print("  -", problem)
        return 1
    count = len(re.findall(r"^## F-\d\d\.", PATH.read_text(encoding="utf-8"), flags=re.MULTILINE))
    print(f"[ok] инсайтов: {count}, у всех есть что/зачем/проверка/статус")
    return 0


if __name__ == "__main__":
    sys.exit(main())
