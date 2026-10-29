"""Проставляет ожидаемые значения у числовых утверждений в CLAIMS.md.

Формат строки: | id | текст | тип | команда | артефакт | дата | ожидание |
Ожидание — регулярное выражение, которому обязан соответствовать вывод команды.
"""

from __future__ import annotations

from pathlib import Path

CLAIMS = Path(__file__).resolve().parents[1] / "CLAIMS.md"

EXPECT = {
    "C-0001": r"0\.2\.1-rc\.3",
    "C-0002": r"5/5 ok",
    "C-0004": r"p50",
    "C-0006": r"20/20",
    "C-0007": r"8,65|8\.65",
    "C-0008": r"lake",
    "C-0009": r"5/5 ok",
    "C-0015": r"zero=\d+",
}


def main() -> int:
    lines = CLAIMS.read_text(encoding="utf-8").splitlines()
    out = []
    changed = 0
    for line in lines:
        if not line.startswith("| C-"):
            out.append(line)
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        cid = cells[0]
        if cid in EXPECT and len(cells) == 6:
            cells.append(f"`{EXPECT[cid]}`")
            out.append("| " + " | ".join(cells) + " |")
            changed += 1
        else:
            out.append(line)
    CLAIMS.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"обновлено строк: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
