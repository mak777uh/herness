"""check_coverage_verdict — прибор проверяет прибор.

coverage.py (bin/coverage.py) меряет покрытие утверждений и режет вердикт. Этот скрипт
независимо вычисляет ground-truth СТРОГОЙ проверяемости по CLAIMS.md и сверяет с тем, что
СООБЩАЕТ coverage.py. Расхождение = прибор льстит себе (F-0089: anchored 1.00 CHECKED_ANCHORED
скрывает strict 0.58 — 108 слабых ожиданий, 23 артефакта-описания).

Предикаты здесь НАМЕРЕННО независимы от bin/claim_strength.py (как check_probe_coverage
независимо парсит gate-probes.txt): сверка должна ловить расхождение реализаций, а не
повторять одну и ту же логику.

    python bin/check_coverage_verdict.py

Выход 0 — вердикт покрытия честен (strict раскрыт, совпадает с ground-truth, слабое ожидание
понижает вердикт); 1 — прибор льстит (strict не раскрыт / расходится / не различает слабое).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "CLAIMS.md"
HEADER = ("# реестр\n\n| id | утверждение | тип | команда | артефакт | дата | ожидание |\n"
          "|---|---|---|---|---|---|---|\n")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


# --- независимые предикаты (ground-truth) ---

def is_runnable(cmd: str) -> bool:
    return bool(re.search(r"\b(python|pytest|git|bash|pwsh|node)\b", cmd))


def artifact_resolves(artifact: str) -> bool:
    if not artifact or artifact == "—":
        return False
    return bool(list(ROOT.glob(artifact)))


def looks_checkable(expect: str) -> bool:
    if re.search(r"\d", expect):
        return True
    if "/" in expect or ".md" in expect or ".txt" in expect or ".json" in expect:
        return True
    if re.search(r"[A-Z]-\d", expect):
        return True
    return False


def parse_active(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("| C-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        if cells[2] == "withdrawn":
            continue
        rows.append({"id": cells[0], "cmd": cells[3].strip("`"),
                     "art": cells[4], "exp": cells[6].strip("`")})
    return rows


def ground_truth(text: str) -> dict:
    rows = parse_active(text)
    strict = [r for r in rows if is_runnable(r["cmd"]) and artifact_resolves(r["art"])
              and looks_checkable(r["exp"])]
    weak = [r for r in rows if not looks_checkable(r["exp"])]
    desc = [r for r in rows if not artifact_resolves(r["art"])]
    n = len(rows)
    return {"active": n, "strict_closed": len(strict),
            "strict_coverage": round(len(strict) / n, 3) if n else 0.0,
            "weak_expects": len(weak), "descriptive_artifacts": len(desc)}


def run_coverage(claims: Path) -> dict:
    """Что СООБЩАЕТ coverage.py: JSON-вердикт и поля (strict раскрыт или нет)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cov.json"
        proc = subprocess.run([sys.executable, str(ROOT / "bin" / "coverage.py"),
                               str(claims), "--out", str(out)], cwd=str(ROOT),
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    data["_rc"] = proc.returncode
    return data


def main() -> int:
    truth = ground_truth(read(CLAIMS))
    reported = run_coverage(CLAIMS)

    lines = [
        "# Покрытие утверждений: прибор проверяет прибор (F-0089, ADR-0058)",
        "",
        f"ground-truth: активных {truth['active']} · строгих {truth['strict_closed']} "
        f"(strict {truth['strict_coverage']}) · слабых ожиданий {truth['weak_expects']} "
        f"· артефактов-описаний {truth['descriptive_artifacts']}",
        f"coverage.py сообщает: покрытие {reported.get('coverage')} · вердикт {reported.get('verdict')!r} "
        f"· strict {reported.get('strict_coverage', 'НЕ РАСКРЫТ')} "
        f"· слабых {reported.get('weak_expects', '—')} · описаний {reported.get('descriptive_artifacts', '—')}",
        "",
    ]

    problems = []
    # 1. Прибор обязан РАСКРЫТЬ strict-меру и counts (не прятать за anchored 1.00).
    if "strict_coverage" not in reported:
        problems.append("coverage.py не раскрывает strict-меру (anchored выдаётся за проверяемость)")
    else:
        if abs(reported.get("strict_coverage", -1) - truth["strict_coverage"]) > 0.001:
            problems.append(f"strict {reported.get('strict_coverage')} != ground-truth {truth['strict_coverage']}")
        if reported.get("weak_expects") != truth["weak_expects"]:
            problems.append(f"слабых {reported.get('weak_expects')} != ground-truth {truth['weak_expects']}")
        if reported.get("descriptive_artifacts") != truth["descriptive_artifacts"]:
            problems.append(f"описаний {reported.get('descriptive_artifacts')} != ground-truth {truth['descriptive_artifacts']}")
        # 2. Вердикт обязан понизиться, если anchored полон, а strict < 1.0.
        if reported.get("coverage", 0) >= 1.0 and truth["strict_coverage"] < 1.0:
            if reported.get("verdict") != "ANCHORED_WEAK":
                problems.append(f"вердикт {reported.get('verdict')!r} не понижен до ANCHORED_WEAK при strict<1.0")

    # 3. Поведенческий NC: строгая и слабая записи обязаны давать РАЗНЫЕ вердикты.
    with tempfile.TemporaryDirectory() as tmp:
        strong = Path(tmp) / "strong.md"
        strong.write_text(HEADER + '| C-0001 | строгая | observation | `python -c "print(1)"` | README.md | 12.11.2026 | `1` |\n', encoding="utf-8")
        weak = Path(tmp) / "weak.md"
        weak.write_text(HEADER + '| C-0001 | слабая | observation | `python -c "print(1)"` | README.md | 12.11.2026 | `ok` |\n', encoding="utf-8")
        desc = Path(tmp) / "desc.md"
        desc.write_text(HEADER + '| C-0001 | описание | observation | `python -c "print(1)"` | вывод команды | 12.11.2026 | `1` |\n', encoding="utf-8")
        rs, rw, rd = run_coverage(strong), run_coverage(weak), run_coverage(desc)
    lines.append(f"NC строгая запись: вердикт {rs.get('verdict')!r} · strict {rs.get('strict_coverage', 'НЕ РАСКРЫТ')}")
    lines.append(f"NC слабое ожидание: вердикт {rw.get('verdict')!r} · strict {rw.get('strict_coverage', 'НЕ РАСКРЫТ')}")
    lines.append(f"NC артефакт-описание: вердикт {rd.get('verdict')!r} · описаний {rd.get('descriptive_artifacts', '—')}")
    lines.append("")
    if rs.get("verdict") == rw.get("verdict"):
        problems.append(f"прибор не различает слабое ожидание: строгая и слабая дают один вердикт {rs.get('verdict')!r}")
    if "strict_coverage" in rs and rs.get("strict_coverage", 0) < 1.0:
        problems.append("строгая запись (команда+файл+число) не получила strict-зачёт")
    if "strict_coverage" in rw and rw.get("verdict") != "ANCHORED_WEAK":
        problems.append(f"слабое ожидание не понизило вердикт до ANCHORED_WEAK (got {rw.get('verdict')!r})")
    if "descriptive_artifacts" in rd and rd.get("descriptive_artifacts", 0) < 1:
        problems.append("артефакт-описание не попало в descriptive_artifacts")

    if problems:
        lines.append("## FAIL (прибор льстит себе)")
        lines.extend(f"- {p}" for p in problems)
        verdict, code = "ПРИБОР ЛЬСТИТ", 1
    else:
        lines.append("## PASS (вердикт покрытия честен)")
        lines.append("- strict раскрыт и совпадает с ground-truth; слабое ожидание понижает вердикт")
        verdict, code = "ПРИБОР ЧЕСТЕН", 0

    lines += [
        "",
        f"вердикт: {verdict}",
        "",
        "## Что это не доказывает",
        "",
        "- что утверждения истинны: сверяется честность меры покрытия (форма ожидания), не смысл;",
        "- что strict 0.58 = «42% ложны»: часть слабых ожиданий falsifiable, правило формы их переоценивает;",
        "- что прибор ловит произвольную ошибку: он ловит регрессию ЭТОГО дефекта (честность вердикта).",
    ]
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())