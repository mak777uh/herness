"""check_probe_coverage — прибор проверяет прибор.

Аудит (bin/audit.py) считает, сколько гейтов покрыто отрицательным контролем (пробой).
Этот скрипт независимо вычисляет то же самое по ground-truth — отчёту проб
(research/outputs/gate-probes.txt) и списку гейтов (bin/hs.py) — и сверяет с тем, что
СООБЩАЕТ audit-report.txt. Расхождение = прибор лжёт (F-0088: parts[0] обрезал составные
имена проб, а строки-пробы считались как разные гейты).

    python bin/check_probe_coverage.py

Выход 0 — отчёт аудита честен; 1 — расходится с ground-truth.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def gate_names() -> list[str]:
    """Имена гейтов из двух контуров hs.py — ground-truth «сколько всего гейтов»."""
    return re.findall(r'\("([^"]+)", gate_[a-z_]+\)', read(ROOT / "bin" / "hs.py"))


def probe_names() -> list[str]:
    """Полные имена проб, поймавших дефект.

    Имя = все токены кроме трёх последних (до, после, поймал): колонка имени фиксированной
    ширины, поэтому parts[0] обрезает составные имена (F-0088). Берём имя целиком.
    """
    names = []
    for line in read(ROOT / "research" / "outputs" / "gate-probes.txt").splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[-1] == "да":
            names.append(" ".join(parts[:-3]))
    return names


def reported() -> tuple[int | None, list[str]]:
    """Что СООБЩАЕТ audit-report.txt: число «гейтов с контролем» и список «без пробы»."""
    text = read(ROOT / "research" / "outputs" / "audit-report.txt")
    match = re.search(r"гейтов с контролем: (\d+)", text)
    count = int(match.group(1)) if match else None
    missing: list[str] = []
    warn = re.search(r"без пробы: (.+)", text)
    if warn:
        missing = sorted(item.strip() for item in warn.group(1).split(","))
    return count, missing


def main() -> int:
    gates = gate_names()
    probes = probe_names()
    covered = set(gates) & set(probes)
    true_missing = sorted(set(gates) - covered)
    rep_count, rep_missing = reported()

    lines = [
        "# Покрытие проб: прибор проверяет прибор (F-0088, ADR-0057)",
        "",
        f"гейтов: {len(gates)} · проб: {len(probes)} · разных гейтов с пробой: {len(covered)}",
        f"ground-truth без пробы: {', '.join(true_missing) or 'нет'}",
        f"аудит сообщает: гейтов с контролем {rep_count}; без пробы: {', '.join(rep_missing) or 'нет'}",
        "",
    ]

    problems = []
    if rep_count != len(covered):
        problems.append(f"аудит «гейтов с контролем: {rep_count}» != ground-truth {len(covered)}")
    if rep_missing != true_missing:
        problems.append(f"аудит missing {rep_missing} != ground-truth {true_missing}")
    false_missing = sorted(set(rep_missing) & covered)
    if false_missing:
        problems.append(f"ложно «без пробы» (проба есть): {', '.join(false_missing)}")

    if problems:
        lines.append("## FAIL (прибор расходится с ground-truth)")
        lines.extend(f"- {problem}" for problem in problems)
        verdict, code = "ПРИБОР ЛЖЁТ", 1
    else:
        lines.append("## PASS (отчёт аудита честен)")
        lines.append("- расхождений нет")
        verdict, code = "ПРИБОР ЧЕСТЕН", 0

    lines += [
        "",
        f"вердикт: {verdict}",
        "",
        "## Что это не доказывает",
        "",
        "- что гейты надёжны: сверяется честность счёта покрытия, а не реакция на неизвестный дефект;",
        "- что пробы ловят все дефекты: ground-truth — те же пробы на известный подложенный дефект;",
        "- что утверждения истинны: это счёт гейтов и проб, не смысл утверждений.",
    ]
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())