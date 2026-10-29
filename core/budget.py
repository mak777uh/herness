"""budget — тормоз прогона.

Из журналов: одна сессия дошла до 7026 вызовов инструментов. Прогон без потолка — это не работа,
а цикл. Здесь считаются шаги, время и объём, и прогон останавливается до следующего шага, если
потолок уже превышен.

Правило: останавливаться ДО выполнения шага, а не после — иначе цена уже заплачена.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def usage(run_dir: Path) -> dict:
    """Что уже потрачено в прогоне: шаги, секунды, байты."""
    events = run_dir / "events.jsonl"
    steps = 0
    first = last = None
    if events.exists():
        for line in events.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            stamp = event.get("ts") or event.get("timestamp")
            if stamp:
                moment = _parse(stamp)
                if moment:
                    first = first or moment
                    last = moment
            if event.get("type") == "tool/call":
                steps += 1

    artifacts = run_dir / "artifacts"
    size = sum(f.stat().st_size for f in artifacts.glob("*")) if artifacts.exists() else 0
    seconds = (last - first).total_seconds() if first and last else 0.0
    return {"steps": steps, "seconds": round(seconds, 1), "bytes": size}


def _parse(stamp: str) -> datetime | None:
    text = str(stamp).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def exceeded(run_dir: Path, max_steps: int = 0, max_seconds: float = 0,
             max_bytes: int = 0) -> tuple[bool, str]:
    """Проверяет потолки. Возвращает (превышен, причина)."""
    current = usage(run_dir)
    if max_steps and current["steps"] >= max_steps:
        return True, f"шагов {current['steps']} при потолке {max_steps}"
    if max_seconds and current["seconds"] >= max_seconds:
        return True, f"секунд {current['seconds']} при потолке {max_seconds}"
    if max_bytes and current["bytes"] >= max_bytes:
        return True, f"байт {current['bytes']} при потолке {max_bytes}"
    return False, ""
