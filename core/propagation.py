"""propagation — перенос инструмента между классами задач.

Идея (ADR-0025): инструмент, доказавший выигрыш в одном классе, пробуется в соседних — но только
по замеру и только через пробный период. Сам по себе он не распространяется.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_classes(path: Path | None = None) -> dict[str, set[str]]:
    data = json.loads((path or ROOT / "classes.json").read_text(encoding="utf-8"))
    return {c["id"]: set(c["actions"]) for c in data["classes"]}


def load_tools(path: Path | None = None) -> list[dict]:
    data = json.loads((path or ROOT / "tools.json").read_text(encoding="utf-8"))
    return data["tools"]


def similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def neighbours(classes: dict[str, set[str]], class_id: str, threshold: float = 0.5) -> list[tuple[str, float]]:
    base = classes.get(class_id, set())
    out = []
    for other, actions in classes.items():
        if other == class_id:
            continue
        score = similarity(base, actions)
        if score >= threshold:
            out.append((other, round(score, 2)))
    return sorted(out, key=lambda kv: -kv[1])


def suggest(tool: dict, classes: dict[str, set[str]], min_advantage: float = 0.2,
            min_similarity: float = 0.5) -> list[dict]:
    """Куда инструменту имеет смысл пойти дальше: соседние классы, где он ещё не пробован."""
    out = []
    for class_id, state in (tool.get("classes") or {}).items():
        if state.get("status") != "active":
            continue
        advantage = state.get("advantage")
        if advantage is None or advantage < min_advantage:
            continue
        for other, score in neighbours(classes, class_id, min_similarity):
            if other in (tool.get("classes") or {}):
                continue
            out.append({
                "tool": tool["name"],
                "from": class_id,
                "to": other,
                "advantage": advantage,
                "similarity": score,
                "status": "candidate",
                "reason": f"выигрыш {advantage:.0%} в {class_id}, близость {score}",
            })
    return out
