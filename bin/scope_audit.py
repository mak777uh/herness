"""scope_audit — уходит ли модель из названного каталога.

Задачи говорят, где лежит ответ («в runs/dump», «в каталоге failures»). Здесь считается, сколько
вызовов ушло за пределы названного каталога. Это измерение отвлечения, а не догадка о нём.

    python bin/scope_audit.py     # research/outputs/scope-audit.txt
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, ".")
from bin import accept  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DIRS = ["runs/dump", "failures", "docs", "history", "CLAIMS.md"]


def named_dir(task: str) -> str | None:
    for name in DIRS:
        if name in task:
            return name
    return None


def analyse(path: Path) -> dict | None:
    records, _tail, _problems = accept.parse_journal(path.read_bytes())
    events = list(accept.events(records))
    task = ""
    for kind, rest in events:
        if kind == "run/start":
            task = rest
            break
    scope = named_dir(task)
    if scope is None:
        return None
    calls = [rest for kind, rest in events if kind == "tool/call"]
    outside = []
    outside_search = []
    for call in calls:
        parts = call.split()
        if len(parts) < 2:
            continue
        tool = parts[0]
        target = " ".join(parts[1:])
        if scope in target:
            continue
        outside.append(call[:48])
        # Отдельно считаем поиск вне каталога: это уже не «осмотреться», а уход от задачи.
        if tool == "search":
            outside_search.append(call[:48])
    return {
        "name": path.stem,
        "scope": scope,
        "calls": len(calls),
        "outside": outside,
        "outside_search": outside_search,
    }


def main() -> int:
    rows = []
    total_calls = total_outside = 0
    with_outside = 0
    for path in sorted((ROOT / "runs" / "accept").glob("*.bin")):
        result = analyse(path)
        if result is None:
            continue
        rows.append(result)
        total_calls += result["calls"]
        total_outside += len(result["outside"])
        if result["outside"]:
            with_outside += 1

    outside_searches = sum(len(result["outside_search"]) for result in rows)
    runs_with_search = sum(1 for result in rows if result["outside_search"])
    lines = [
        "# Уход из названного каталога (отвлечение)",
        "",
        f"прогонов с названным каталогом: {len(rows)}",
        f"вызовов всего: {total_calls}; вне названного каталога: {total_outside} "
        f"({total_outside / total_calls if total_calls else 0:.0%})",
        f"из них поиск вне каталога: {outside_searches} в {runs_with_search} прогонах",
        f"прогонов хотя бы с одним выходом за пределы: {with_outside}",
        "",
        "# Большая часть выходов — один list /mnt в начале прогона (осмотреться). Отдельный счёт",
        "# поиска вне каталога показывает уже уход от задачи, а не ориентировку.",
        "",
        f"{'прогон':36} {'каталог':10} вызовов вне поиска-вне",
    ]
    for result in sorted(rows, key=lambda item: -len(item["outside"])):
        if not result["outside"]:
            continue
        lines.append(
            f"{result['name'][:36]:36} {result['scope']:10} {result['calls']:>3} {len(result['outside']):>4}"
            f" {len(result['outside_search']):>5}  {', '.join(result['outside'][:2])}"
        )
    text = "\n".join(lines) + "\n"
    (ROOT / "research" / "outputs" / "scope-audit.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
