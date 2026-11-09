"""series50_report — посчитать результат серии 50 по записанному отчёту.

Зачем отдельно: утверждение C-0295 не должно перезапускать серию (25 минут).
Здесь читается research/outputs/series50.txt и считается «PASS из 50».

    python bin/series50_report.py
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORT = ROOT / "research" / "outputs" / "series50.txt"


def main() -> int:
    if not REPORT.exists():
        print(f"нет отчёта серии: {REPORT} — это UNKNOWN, не PASS")
        return 2
    rows = [line for line in REPORT.read_text(encoding="utf-8").splitlines()
            if re.match(r"^\| S\d+", line)]
    if not rows:
        print("в отчёте нет строк задач — это UNKNOWN")
        return 2
    passed = sum(1 for line in rows if "| PASS |" in line)
    failed = [line.split("|")[1].strip() for line in rows if "| FAIL |" in line]
    print(f"задач: {len(rows)}")
    print(f"PASS: {passed}")
    print(f"FAIL: {len(failed)}")
    if failed:
        print(f"провалы: {', '.join(failed)}")
    print(f"{passed} из {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
