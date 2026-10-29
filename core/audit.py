"""audit — заметки аудита: себя, соседа, харнесса.

Правило (ADR-0017): заметка без воспроизводящего случая — не находка, а мнение.
Мнения считаются, но в совет не идут.
"""

from __future__ import annotations

import re
from pathlib import Path

FIELDS = ("from", "to", "about", "severity", "repro", "finding", "would_change")
REQUIRED = ("from", "to", "finding")
SEVERITIES = ("low", "medium", "high")
LINE = re.compile(r"^([a-z_]+):\s*(.*)$")


def parse(path: Path) -> dict:
    fields: dict[str, str] = {}
    body = []
    in_header = True
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if in_header:
            m = LINE.match(line.strip())
            if m and m.group(1) in FIELDS:
                fields[m.group(1)] = m.group(2).strip()
                continue
            if not line.strip():
                continue
            in_header = False
        body.append(line)
    fields["_path"] = str(path)
    fields["_body"] = "\n".join(body).strip()
    return fields


def classify(note: dict) -> str:
    if any(not note.get(f) for f in REQUIRED):
        return "invalid"
    repro = (note.get("repro") or "").strip().lower()
    if not repro or repro in {"нет", "-", "no", "none"}:
        return "opinion"
    return "finding"


def scan(root: Path) -> list[dict]:
    inbox = root / "inbox"
    if not inbox.exists():
        return []
    notes = []
    for path in sorted(inbox.rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        note = parse(path)
        note["_status"] = classify(note)
        note["_target"] = note.get("to", "?")
        notes.append(note)
    return notes


def summary(root: Path) -> dict:
    notes = scan(root)
    groups: dict[tuple[str, str], int] = {}
    for n in notes:
        if n["_status"] != "finding":
            continue
        key = (n["_target"], (n.get("finding") or "").strip().lower()[:120])
        groups[key] = groups.get(key, 0) + 1
    return {
        "total": len(notes),
        "findings": [n for n in notes if n["_status"] == "finding"],
        "opinions": [n for n in notes if n["_status"] == "opinion"],
        "invalid": [n for n in notes if n["_status"] == "invalid"],
        "repeats": sorted(groups.items(), key=lambda kv: -kv[1]),
    }


def problems(root: Path) -> list[str]:
    out = []
    for note in scan(root):
        if note["_status"] == "invalid":
            missing = [f for f in REQUIRED if not note.get(f)]
            out.append(f"{note['_path']}: нет обязательных полей: {', '.join(missing)}")
        severity = (note.get("severity") or "").strip().lower()
        if severity and severity not in SEVERITIES:
            out.append(f"{note['_path']}: неизвестная важность '{severity}'")
    return out
