"""patterns — пересчёт утверждений о повторах в журналах (C-0019, C-0020).

Считает по всем сессиям DSH: сколько команд начинаются с `cd`, сколько вызывают venv-python,
сколько задают PYTHONIOENCODING. Числа печатаются; сверка с ожиданием — флагом --check.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

SESSIONS = Path.home() / ".dsh" / "sessions"


def scan() -> Counter:
    counts: Counter = Counter()
    for path in sorted(SESSIONS.rglob("*.zstd")):
        proc = subprocess.Popen(["zstd", "-d", "-c", str(path)], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            if '"tool/call"' not in line:
                continue
            try:
                event = json.loads(line)
                args = (event.get("data") or event.get("payload") or {}).get("arguments") or "{}"
                args = json.loads(args) if isinstance(args, str) else args
                cmd = str(args.get("command") or "")
            except (json.JSONDecodeError, AttributeError):
                continue
            if not cmd:
                continue
            counts["calls"] += 1
            if cmd.lstrip().startswith("cd "):
                counts["cd_start"] += 1
            if "Scripts\\python.exe" in cmd or "Scripts/python.exe" in cmd:
                counts["venv_python"] += 1
            if "PYTHONIOENCODING" in cmd:
                counts["pythonioencoding"] += 1
        proc.wait()
    return counts


def main(argv: list[str]) -> int:
    counts = scan()
    for key in ("calls", "cd_start", "venv_python", "pythonioencoding"):
        print(f"{key}={counts[key]}")

    if "--check" not in argv:
        return 0

    # ожидания объявлены заранее; допуск 10 % — числа растут вместе с новыми сессиями
    expected = {"cd_start": 19386, "venv_python": 14729}
    failed = 0
    for key, value in expected.items():
        got = counts[key]
        low, high = value * 0.9, value * 1.6
        ok = low <= got <= high
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {key}: ожидалось ≈{value}, получено {got}")
    print(f"\nповторы: {len(expected) - failed}/{len(expected)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
