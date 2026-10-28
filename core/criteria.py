"""criteria — реестр критериев: что считаем истинным и чем это устанавливается.

Правило: критерий без способа установления — не критерий (docs/CRITERIA.md).
"""

from __future__ import annotations

import re
from pathlib import Path

STATUSES = {"док", "замер", "суждение", "опровергнуто"}
ID_RE = re.compile(r"^K\d{1,3}$")


def parse(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("| K"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            rows.append({"id": cells[0] if cells else "?", "bad": "меньше пяти полей"})
            continue
        rows.append({"id": cells[0], "criterion": cells[1], "status": cells[2],
                     "how": cells[3], "artifact": cells[4]})
    return rows


def problems(root: Path) -> list[str]:
    path = root / "docs" / "CRITERIA.md"
    if not path.exists():
        return ["docs/CRITERIA.md отсутствует"]
    out = []
    for row in parse(path.read_text(encoding="utf-8")):
        if "bad" in row:
            out.append(f"CRITERIA: {row['id']} — {row['bad']}")
            continue
        if not ID_RE.match(row["id"]):
            out.append(f"CRITERIA: {row['id']} — ожидался K-N")
        if row["status"] not in STATUSES:
            out.append(f"CRITERIA: {row['id']} — неизвестный статус '{row['status']}'")
        if not row["how"]:
            out.append(f"CRITERIA: {row['id']} — нет способа установления")
        if not row["artifact"]:
            out.append(f"CRITERIA: {row['id']} — нет артефакта")
    return out


def summary(root: Path) -> dict:
    path = root / "docs" / "CRITERIA.md"
    rows = parse(path.read_text(encoding="utf-8")) if path.exists() else []
    counts: dict[str, int] = {}
    for row in rows:
        if "bad" in row:
            continue
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "total": len(rows),
        "counts": counts,
        "open_judgments": [r["id"] for r in rows if r.get("status") == "суждение"],
        "refuted": [r["id"] for r in rows if r.get("status") == "опровергнуто"],
        "planned": [r["id"] for r in rows if r.get("status") == "замер"],
    }
