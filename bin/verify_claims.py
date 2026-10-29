"""verify — прогон утверждений их же командами.

Идея продукта, применённая к себе: если у утверждения есть команда, её можно выполнить и увидеть,
подтверждается ли оно. Никакого доверия к тексту.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

CLAIMS = Path(__file__).resolve().parents[1] / "CLAIMS.md"
ROW = re.compile(r"^\|\s*(C-\d{4})\s*\|(.+)$")


def parse(path: Path = CLAIMS) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        rows.append({"id": cells[0], "text": cells[1], "type": cells[2],
                     "cmd": cells[3].strip("`"), "artifact": cells[4], "date": cells[5]})
    return rows


def run_command(cmd: str, timeout: int = 300) -> tuple[str, str]:
    """Возвращает (статус, короткий вывод). Статус: ok / fail / not-runnable."""
    if not cmd or not re.search(r"\b(python|pytest|git|bash|pwsh|node)\b", cmd):
        return "not-runnable", "команда не исполняемая (описание)"
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace", cwd=Path(__file__).resolve().parents[1])
    except subprocess.TimeoutExpired:
        return "fail", f"таймаут {timeout}s"
    out = (proc.stdout or "") + (proc.stderr or "")
    tail = " ".join(out.strip().splitlines()[-1:])[:160]
    return ("ok" if proc.returncode == 0 else "fail"), tail or f"rc={proc.returncode}"


def main(argv: list[str]) -> int:
    rows = parse()
    only = argv[0] if argv else None
    failed = 0
    for row in rows:
        if only and row["id"] != only:
            continue
        status, tail = run_command(row["cmd"])
        if status == "fail":
            failed += 1
        mark = {"ok": "ok", "fail": "FAIL", "not-runnable": "—"}[status]
        print(f"[{mark:<4}] {row['id']} {row['text'][:70]}")
        print(f"        {tail}")
    print(f"\nутверждений: {len(rows)}; провалено: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
