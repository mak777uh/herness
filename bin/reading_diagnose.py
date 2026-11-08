"""reading_diagnose — почему задачи чтения проваливаются.

Шаг 1 плана: починить чтение. Правка лимитов (MAX_READ 8→24 КиБ, LAST_RESULT 4000→12000)
не помогла: 3 из 10 против 4 из 10. Значит причина не в лимитах.

Диагноз: смотрим, что именно агент делал в провалившихся прогонах.

    python bin/reading_diagnose.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
OUT = ROOT / "research" / "outputs" / "reading-diagnose.txt"


def main() -> int:
    lines = ["# Почему чтение проваливается", ""]

    # Берём последние прогоны чтения.
    results = ROOT / "runs" / "series50" / "results.json"
    if not results.exists():
        print("нет результатов серии")
        return 2
    data = json.loads(results.read_text(encoding="utf-8"))
    read = [r for r in data if "read" in r["task"]]
    failed = [r for r in read if r["verdict"] != "PASS"]

    lines.append(f"задач чтения: {len(read)}")
    lines.append(f"провалено: {len(failed)}")
    lines.append("")
    lines.append("| задача | вердикт | секунд |")
    lines.append("|---|---|---|")
    for row in read:
        lines.append(f"| {row['task']} | {row['verdict']} | {row['seconds']} |")
    lines.append("")

    # Смотрим журналы провалов: что агент делал.
    lines.append("## Что агент делал в провалах")
    lines.append("")
    for row in failed[:5]:
        lines.append(f"### {row['task']}")
        lines.append("")
        # Ищем журнал прогона.
        journal = find_journal(row["task"])
        if journal is None:
            lines.append("журнал не найден")
            lines.append("")
            continue
        steps = extract_steps(journal)
        lines.append(f"шагов: {len(steps)}")
        lines.append("")
        for step in steps[:8]:
            lines.append(f"- {step}")
        lines.append("")

    lines.append("## Гипотезы")
    lines.append("")
    lines.append("1. **Лимиты не виноваты.** Правка MAX_READ и LAST_RESULT не помогла.")
    lines.append("2. **Агент не находит место.** Возможно, он читает файл с начала и не доходит "
                 "до нужной строки.")
    lines.append("3. **Задача сформулирована неоднозначно.** «Назови число» — какое число?")
    lines.append("4. **Модель считает в уме.** Для задач подсчёта это ожидаемо.")
    lines.append("")
    lines.append("## Что проверить дальше")
    lines.append("")
    lines.append("- Посмотреть, на каком шаге агент останавливается.")
    lines.append("- Проверить, доходит ли он до нужного места в файле.")
    lines.append("- Переформулировать задачи чтения так, чтобы место было однозначным.")

    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


def find_journal(task: str) -> Path | None:
    """Журнал последнего прогона задачи."""
    candidates = sorted(RUNS.glob(f"**/{task}*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        if path.is_file() and path.suffix in (".bin", ".json", ".txt"):
            return path
    return None


def extract_steps(path: Path) -> list[str]:
    """Шаги из журнала: строки TOOL/DONE/BLOCKED."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    steps = []
    for line in text.splitlines():
        match = re.search(r"(TOOL \w+[^\"]*|DONE[^\"]*|BLOCKED[^\"]*)", line)
        if match:
            steps.append(match.group(1)[:100])
    return steps


if __name__ == "__main__":
    sys.exit(main())
