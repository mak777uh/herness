"""gate_docs — числа в документации обязаны совпадать с файлами.

Зачем (F-DOC-1, 09.11.2026). В `docs/CONTINUE.md` стояло «NOT-CLAIMED.md —
29 записей» и «CLAIMS.md — 281 запись», а в файлах было 14 и 293. Число 29
никогда не существовало: в первом же коммите с этим файлом записей было 14.
Я повторял это число владельцу как факт.

Гейт «README» проверяет, что число в README имеет владельца в CLAIMS.md, но
не сверяет его с ФАЙЛОМ. Здесь сверка идёт с файлом: сколько записей реально
лежит в реестре.

    python bin/gate_docs.py
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Что где заявлено и как посчитать фактическое.
CHECKS = [
    ("docs/CONTINUE.md", r"`CLAIMS\.md` — (\d+) запис", "CLAIMS.md", r"^\| C-\d{4}"),
    ("docs/CONTINUE.md", r"`NOT-CLAIMED\.md` — (\d+) запис", "NOT-CLAIMED.md", r"^\| `NC-\d+`"),
    ("docs/CONTINUE.md", r"`REQUIREMENTS\.md` — (\d+) запис", "REQUIREMENTS.md", r"^## R-\d{4}"),
    ("docs/CONTINUE.md", r"`docs/ADR-\*\.md`[^|]*— (\d+) решени", None, None),
]


def count_rows(path: pathlib.Path, pattern: str) -> int:
    if not path.exists():
        return -1
    return len(re.findall(pattern, path.read_text(encoding="utf-8", errors="replace"), re.M))


def main() -> int:
    problems: list[str] = []
    checked = 0
    for doc, claim_pattern, target, row_pattern in CHECKS:
        path = ROOT / doc
        if not path.exists():
            problems.append(f"нет документа {doc}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(claim_pattern, text)
        if not match:
            continue
        claimed = int(match.group(1))
        if target is None:
            # ADR считаем по файлам.
            actual = len(list((ROOT / "docs").glob("ADR-*.md")))
        else:
            actual = count_rows(ROOT / target, row_pattern)
        checked += 1
        if actual != claimed:
            problems.append(
                f"{doc}: заявлено {claimed}, фактически {actual} ({target or 'docs/ADR-*.md'})")

    if problems:
        print(f"[FAIL] документы: {len(problems)} проблем (проверено {checked})")
        for problem in problems:
            print(f"   - {problem}")
        return 1
    print(f"[ok] документы: 0 проблем (сверено чисел: {checked})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
