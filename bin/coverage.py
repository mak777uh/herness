"""Покрытие утверждений: closed / всех, где кривые строки идут в знаменатель.

Взято у lexspec (§8): coverage = |closed atoms| / |all atoms|, и знаменатель — **все** записи, включая
битые. Причина: «число покрытия, которое растёт от того, что запись сломалась, — это число, которым
стоит врать».
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "CLAIMS.md"  # переопределяется первым аргументом
COLUMNS = 7


def main(argv=None) -> int:
    global CLAIMS
    argv = argv if argv is not None else sys.argv[1:]
    if argv:
        CLAIMS = Path(argv[0])
    rows = []
    malformed = 0
    for line in CLAIMS.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| C-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != COLUMNS:
            malformed += 1
            rows.append({"id": cells[0], "closed": False, "why": f"колонок {len(cells)}, нужно {COLUMNS}"})
            continue
        cells = [cell.strip().strip("`").strip() for cell in cells]
        claim_id, statement, kind, command, artifact, _, expect = cells
        problems = []

        if kind == "withdrawn":
            # отозванное утверждение не проверяется, но должно ссылаться на замену
            if "см." not in (statement + artifact).lower():
                problems.append("отозвано без ссылки на замену")
            rows.append({"id": claim_id, "closed": not problems, "kind": kind,
                         "why": "; ".join(problems) or "withdrawn"})
            continue

        if not command:
            problems.append("нет команды")
        if not artifact or artifact == "—":
            problems.append("нет артефакта")
        if not expect:
            problems.append("нет ожидания")
        if artifact and "/" in artifact and not list(ROOT.glob(artifact)):
            problems.append("артефакт не найден")
        rows.append({"id": claim_id, "closed": not problems, "why": "; ".join(problems) or "closed",
                     "kind": kind})
    total = len(rows)
    closed = sum(1 for row in rows if row["closed"])
    coverage = closed / total if total else 0.0

    print(f"утверждений: {total}, закрытых: {closed}, покрытие: {coverage:.2f}")
    print(f"битых строк: {malformed} (входят в знаменатель)")
    print("всего строк реестра — это все утверждения, включая те, у которых нет команды; "
          "проверка команд считает только исполняемые (verify_claims)")

    if coverage >= 1.0:
        verdict = "CHECKED_ANCHORED"
    elif coverage >= 0.8:
        verdict = "CHECKED"
    else:
        verdict = "REFUSED"
    print(f"вердикт по покрытию: {verdict} (порог 0.8 — справочный, вердикт режут незакрытые записи)")

    open_rows = [row for row in rows if not row["closed"]]
    if open_rows:
        print("\nне закрыты:")
        for row in open_rows[:12]:
            print(f"  {row['id']}: {row['why']}")

    out = ROOT / "research" / "claims-coverage.json"
    out.write_text(json.dumps({"total": total, "closed": closed, "malformed": malformed,
                               "coverage": round(coverage, 3), "verdict": verdict,
                               "open": open_rows}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\nзаписано: {out}")
    # сильный вердикт требует всех закрытых записей; порог 0.8 не решает
    return 0 if coverage >= 1.0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

