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


def run_command(cmd: str, timeout: int = 120, retries: int = 0) -> tuple[str, str, str]:
    """Возвращает (статус, полный вывод, краткая строка).

    `retries` нужны живым проверкам: у сетевой команды «нет ответа» — это не свидетельство против
    утверждения, а состояние сети. Повтор делается только для провала; успех не перепроверяется,
    иначе проверка начнёт стоить вдвое дороже там, где всё в порядке.
    """
    if not cmd or not re.search(r"\b(python|pytest|git|bash|pwsh|node)\b", cmd):
        return "not-runnable", "", "команда не исполняемая (описание)"
    if "hs.py gates" in cmd or "verify_claims" in cmd:
        # самовызов: утверждение не может проверяться той же проверкой, которая его читает
        return "fail", "", "команда вызывает саму проверку (рекурсия)"
    attempt = 0
    while True:
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout,
                                  encoding="utf-8", errors="replace", cwd=ROOT)
        except subprocess.TimeoutExpired:
            proc = None
        if proc is not None and proc.returncode == 0:
            full = (proc.stdout or "") + (proc.stderr or "")
            tail = " ".join(full.strip().splitlines()[-1:])[:160]
            return "ok", full, tail or "rc=0"
        if attempt >= retries:
            if proc is None:
                return "fail", "", "таймаут " + str(timeout) + "s"
            full = (proc.stdout or "") + (proc.stderr or "")
            tail = " ".join(full.strip().splitlines()[-1:])[:160]
            return "fail", full, tail or ("rc=" + str(proc.returncode))
        attempt += 1


SLOW = ("live", "ping", "probe_api", "live_cases", "replay_archive", "measure_steps",
        "dist_stats", "patterns.py", "snapshot_stats", "hs.py tools", "hs.py browser", "selftest", "hs.py run")


def main(argv: list[str]) -> int:
    rows = parse()
    args = [a for a in argv if not a.startswith("--")]
    fast = "--fast" in argv
    if fast:
        rows = [r for r in rows if not any(word in r["cmd"] for word in SLOW)]
    only = args[0] if args else None
    failed = 0
    for row in rows:
        if only and row["id"] != only:
            continue
        # Живые проверки ходят в сеть: один повтор на провал — чтобы «сеть моргнула» не выглядело
        # как «утверждение неверно». Успех не перепроверяется.
        tries = 1 if any(word in row["cmd"] for word in SLOW) else 0
        status, full, tail = run_command(row["cmd"], retries=tries)
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
    mark = " (быстрый режим: без сетевых и живых команд)" if fast else ""
    print("\nутверждений: " + str(len(rows)) + "; провалено: " + str(failed) + mark)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
