"""Отчёт прогона: из журнала — в читаемый продукт.

Правило P5: отчёт без раздела «что это не доказывает» не создаётся. Это не стиль, а отказ:
вердикт без границы — другое утверждение.
"""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import Claim, ContractError


def read_events(run_dir: Path) -> list[dict]:
    path = Path(run_dir) / "events.jsonl"
    if not path.exists():
        raise ContractError(f"нет журнала прогона: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build(run_dir: Path, task: str, claims: list[Claim] | None = None,
          boundaries: tuple[str, ...] = ()) -> str:
    """Собирает markdown-отчёт. Без границ — отказ."""
    if not boundaries:
        raise ContractError("отчёт: нет раздела «что это не доказывает»")

    events = read_events(run_dir)
    artifacts = [e for e in events if e["type"] == "tool/result"]
    calls = [e for e in events if e["type"] == "tool/call"]
    end = next((e for e in events if e["type"] == "run/end"), {"payload": {}})

    lines = [
        f"# Отчёт прогона: {task}",
        "",
        f"- прогон: `{Path(run_dir).name}`",
        f"- событий: {len(events)}; вызовов инструментов: {len(calls)}",
        f"- статус: {end['payload'].get('status', '?')}",
        "",
        "## Свидетельства",
        "",
    ]

    if not artifacts:
        lines.append("_артефактов нет — прогон не произвёл свидетельств_")
    else:
        lines += ["| # | инструмент | артефакт | байт |", "|---|---|---|---|"]
        for i, event in enumerate(artifacts, 1):
            payload = event["payload"]
            art = payload.get("artifact", {})
            name = next((c["payload"].get("name", "?") for c in calls
                         if c["payload"].get("call_id") == payload.get("call_id")), "?")
            lines.append(f"| {i} | `{name}` | `{art.get('path')}` | {art.get('bytes')} |")

    lines += ["", "## Утверждения", ""]
    if claims:
        lines += ["| id | утверждение | тип | происхождение |", "|---|---|---|---|"]
        for claim in claims:
            claim.validate()
            lines.append(f"| {claim.id} | {claim.text} | {claim.type} | {claim.origin} |")
    else:
        lines.append("_утверждения не заявлены: прогон произвёл свидетельства, но не выводы_")

    lines += ["", "## Что это не доказывает", ""]
    lines += [f"- {item}" for item in boundaries]

    lines += ["", "## Провенанс", "",
              f"- журнал: `{Path(run_dir).name}/events.jsonl`",
              f"- артефакты: `{Path(run_dir).name}/artifacts/`"]
    return "\n".join(lines) + "\n"


def write(run_dir: Path, task: str, claims: list[Claim] | None = None,
          boundaries: tuple[str, ...] = ()) -> Path:
    text = build(run_dir, task, claims, boundaries)
    path = Path(run_dir) / "report.md"
    path.write_text(text, encoding="utf-8")
    return path
