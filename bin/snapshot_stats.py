"""snapshot_stats — снимок статистики журналов, чтобы утверждения не дрейфовали.

Числа считаются по ~/.dsh/sessions (вне репозитория), поэтому в git кладётся снимок: дата,
команда, значения. Утверждения ссылаются на снимок, а не на живой каталог.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "snapshots"


def main() -> int:
    patterns = subprocess.run([sys.executable, "bin/patterns.py"], cwd=str(ROOT),
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
    values = {}
    for line in patterns.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = int(value.strip() or 0)

    dist = subprocess.run([sys.executable, "bin/dist_stats.py"], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    sessions = zero = None
    for line in dist.stdout.splitlines() + (dist.stderr or "").splitlines():
        if line.startswith("сессий="):
            parts = dict(part.split("=") for part in line.split() if "=" in part)
            sessions = int(parts.get("сессий", 0))
            zero = int(parts.get("zero", 0))

    snapshot = {
        "date": date.today().isoformat(),
        "source": "~/.dsh/sessions (вне репозитория)",
        "command": "python bin/patterns.py && python bin/dist_stats.py",
        "values": {**values, "sessions": sessions, "zero": zero},
        "note": "снимок, а не живое значение: утверждения ссылаются сюда",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{snapshot['date']}-stats.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"снимок: {path}")
    print(json.dumps(snapshot["values"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
