"""repeats — поиск кандидатов в процедуры по журналам.

Петля из ADR-0023: журнал → повтор (≥N) → процедура → тест → автоматический запуск → журнал.
Здесь первый шаг: найти повторы и оценить, сколько шагов они съедают.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

SESSIONS = Path.home() / ".dsh" / "sessions"


def _command(event: dict) -> str:
    payload = event.get("payload") or event.get("data") or {}  # наш журнал: payload; сессии DSH: data
    args = payload.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return ""
    return str(args.get("command") or "").strip()


def from_events(lines) -> tuple[Counter, Counter]:
    """Считает повторы команд и пар «команда → команда» в одном журнале."""
    single: Counter = Counter()
    pairs: Counter = Counter()
    prev = None
    for line in lines:
        if '"tool/call"' not in line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        cmd = _command(event)
        if not cmd:
            continue
        single[cmd] += 1
        if prev is not None:
            pairs[(prev, cmd)] += 1
        prev = cmd
    return single, pairs


def scan_runs(runs_dir: Path) -> tuple[Counter, Counter]:
    single: Counter = Counter()
    pairs: Counter = Counter()
    for journal in sorted(Path(runs_dir).glob("*/events.jsonl")):
        s, p = from_events(journal.read_text(encoding="utf-8").splitlines())
        single.update(s)
        pairs.update(p)
    return single, pairs


def scan_sessions(limit: int = 0) -> tuple[Counter, Counter]:
    files = list(SESSIONS.rglob("*.zstd"))
    # выборка — по размеру: маленькие сессии почти пусты и дают ложный ноль
    files.sort(key=lambda f: f.stat().st_size, reverse=bool(limit))
    if limit:
        files = files[:limit]
    single: Counter = Counter()
    pairs: Counter = Counter()
    for path in files:
        proc = subprocess.Popen(["zstd", "-d", "-c", str(path)], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
        lines = list(proc.stdout)
        proc.wait()
        s, p = from_events(lines)
        single.update(s)
        pairs.update(p)
    return single, pairs


def candidates(single: Counter, pairs: Counter, threshold_single: int = 3,
               threshold_pair: int = 5) -> list[dict]:
    """Кандидаты по порогам ADR-0023: ≥3 одинаковых, ≥5 связок."""
    out = []
    for cmd, count in single.items():
        if count >= threshold_single:
            out.append({"kind": "command", "what": cmd[:160], "count": count})
    for (a, b), count in pairs.items():
        if count >= threshold_pair:
            out.append({"kind": "pair", "what": (a[:70] + "  →  " + b[:70]), "count": count})
    return sorted(out, key=lambda r: -r["count"])


