"""failures — корпус отказов процесса.

Каждая ошибка становится случаем: что произошло, какой класс, какой принцип должен был поймать,
чем ловится сейчас и как проверить, что не повторится.

Правило: принцип без случая отказа — гипотеза. Случай без принципа — просто неприятность.
"""

from __future__ import annotations

import re
from pathlib import Path

FIELDS = ("id", "date", "what", "class", "principle", "detect", "test", "cost")
REQUIRED = ("id", "date", "what", "class", "principle", "detect", "test")
ID_RE = re.compile(r"^F-\d{4}$")
LINE = re.compile(r"^([a-z_]+):\s*(.*)$")


def parse(path: Path) -> dict:
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE.match(line.strip())
        if m and m.group(1) in FIELDS:
            fields[m.group(1)] = m.group(2).strip()
    fields["_path"] = str(path)
    return fields


def scan(root: Path) -> list[dict]:
    folder = root / "lab" / "failures"
    if not folder.exists():
        return []
    return [parse(p) for p in sorted(folder.glob("*.md")) if p.name.lower() != "readme.md"]


def problems(root: Path) -> list[str]:
    out = []
    for case in scan(root):
        if not ID_RE.match(case.get("id", "")):
            out.append(f"{case['_path']}: ожидался id вида F-0000")
        missing = [f for f in REQUIRED if not case.get(f)]
        if missing:
            out.append(f"{case['_path']}: нет полей: {', '.join(missing)}")
    return out


def summary(root: Path) -> dict:
    cases = scan(root)
    classes: dict[str, int] = {}
    for case in cases:
        cls = case.get("class") or "?"
        classes[cls] = classes.get(cls, 0) + 1
    return {"total": len(cases), "classes": classes, "cases": cases}
