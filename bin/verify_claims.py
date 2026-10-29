"""verify — прогон утверждений их же командами и сверка с ожидаемым значением.

Правило (F-0012): код возврата 0 не значит «значение верно». Если у утверждения указано ожидание,
вывод команды обязан ему соответствовать.

Формат строки в CLAIMS.md:
| id | текст | тип | команда | артефакт | дата | ожидание |
Последняя колонка необязательна; это регулярное выражение.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "CLAIMS.md"
ROW = re.compile(r"^\|\s*(C-\d{4})\s*\|")


def parse(path: Path = CLAIMS) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not ROW.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        rows.append({
            "id": cells[0], "text": cells[1], "type": cells[2],
            "cmd": cells[3].strip("`"), "artifact": cells[4], "date": cells[5],
            "expect": cells[6].strip("`") if len(cells) > 6 else "",
        })
    return rows


def run_command(cmd: str, timeout: int = 300) -> tuple[str, str, str]:
    """Возвращает (статус, полный вывод, краткая строка)."""
    if not cmd or not re.search(r"\b(python|pytest|git|bash|pwsh|node)\b", cmd):
        return "not-runnable", "", "команда не исполняемая (описание)"
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace", cwd=ROOT)
    except subprocess.TimeoutExpired:
        return "fail", "", "таймаут " + str(timeout) + "s"
    full = (proc.stdout or "") + (proc.stderr or "")
    tail = " ".join(full.strip().splitlines()[-1:])[:160]
    return ("ok" if proc.returncode == 0 else "fail"), full, tail or ("rc=" + str(proc.returncode))


def main(argv: list[str]) -> int:
    rows = parse()
    only = argv[0] if argv else None
    failed = 0
    for row in rows:
        if only and row["id"] != only:
            continue
        status, full, tail = run_command(row["cmd"])
        if status == "not-runnable" and row["expect"]:
            # реестр не должен допускать «измерено, но сверить нечем»
            status = "fail"
            tail = "команда неисполняемая, а ожидание задано: " + repr(row["expect"])
        if status == "ok" and row["expect"] and not re.search(row["expect"], full):
            status = "fail"
            tail = "нет совпадения с ожиданием " + repr(row["expect"]) + "; " + tail
        if status == "fail":
            failed += 1
        mark = {"ok": "ok", "fail": "FAIL", "not-runnable": "—"}[status]
        print("[" + mark.ljust(4) + "] " + row["id"] + " " + row["text"][:70])
        print("        " + tail)
    print("\nутверждений: " + str(len(rows)) + "; провалено: " + str(failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
