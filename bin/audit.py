"""audit — повторяемый аудит репозитория по принципам, а не разовое эссе.

Запуск:
    python bin/audit.py            # отчёт и артефакт, exit 0
    python bin/audit.py --strict   # exit 1, если есть FAIL (для CI и перед публикацией)

Что проверяется (каждый пункт — из принципов AGENTS.md и плана docs/AUDIT-PLAN.md):

  инварианты (FAIL):  дубли утверждений, покрытие < 1.00, гейты не зелёные
  долги (WARN):       артефакты без ссылок, гейты без отрицательного контроля, отсутствие
                      runs/index.json, следы XXX/TODO, отказы без caught_by, вес утверждений
  отчёт всегда:       числа, список долгов, что этот аудит не доказывает

Главное отличие от эссе: список долгов вычисляется, поэтому его нельзя «забыть» — он появляется
каждый запуск, пока не закрыт.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def core_count() -> int:
    """Сколько утверждений в ядре (lab/core-claims.txt); учёт не считается знанием."""
    path = ROOT / "lab" / "core-claims.txt"
    if not path.exists():
        return 0
    return len([line for line in read(path).splitlines() if line.strip() and not line.startswith("#")])


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    strict = "--strict" in args

    claims_text = read(ROOT / "CLAIMS.md")
    claims = re.findall(r"\| (C-\d{4}) \|", claims_text)
    duplicates = [ident for ident, count in Counter(claims).items() if count > 1]
    cited = set(re.findall(r"(research/outputs/[A-Za-z0-9._\-]+|lab/[A-Za-z0-9._/\-]+|docs/[A-Za-z0-9._\-]+\.md)", claims_text))

    outputs = sorted(path.name for path in (ROOT / "research" / "outputs").glob("*"))
    uncited = [name for name in outputs if f"research/outputs/{name}" not in cited]

    failures = sorted(path.stem for path in (ROOT / "lab" / "failures").glob("F-*.md"))
    without_guard = [name for name in failures if "caught_by" not in read(ROOT / "lab" / "failures" / f"{name}.md")]

    gates_text = read(ROOT / "bin" / "hs.py")
    gates = re.findall(r'\("([^"]+)", gate_[a-z_]+\)', gates_text)
    # Контроль гейта — это проба, которая подкладывает дефект и требует находки. Считаем по отчёту
    # проб, а не по старому списку двух скриптов: иначе аудит показывает устаревшую картину (F-0055).
    # Имя пробы — все токены кроме трёх последних (до, после, поймал), а не parts[0]: колонка имени
    # фиксированной ширины, parts[0] обрезает составные имена («ядро утверждений»→«ядро») и гейт
    # ложно числится без пробы (F-0088, ADR-0057). Покрытие — РАЗНЫЕ гейты: суб-проба одного гейта
    # («утверждения-колонки») не увеличивает покрытие.
    probes = []
    probe_report = read(ROOT / "research" / "outputs" / "gate-probes.txt")
    for line in probe_report.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[-1] == "да":
            probes.append(" ".join(parts[:-3]))
    covered = set(gates) & set(probes)

    coverage = {}
    try:
        coverage = json.loads(read(ROOT / "research" / "claims-coverage.json") or "{}")
    except Exception:  # noqa: BLE001
        coverage = {}

    marker_counts = Counter()
    # Файлы, которые по своей природе содержат эти слова: сам аудит, его помощник и план.
    skip = {"audit.py", "audit_facts.py", "AUDIT-PLAN.md", "WHERE-WE-ARE.md"}
    for pattern in ("bin/*.py", "core-rs/src/*.rs", "docs/*.md"):
        for path in ROOT.glob(pattern):
            if path.name in skip:
                continue
            text = read(path)
            for word in ("TODO", "FIXME", "XXX"):
                # Плейсхолдеры в шаблонах (C-XXXX, F-XXXX, H-XXXX) — не незавершённость.
                for match in re.finditer(rf"\b{word}\b", text):
                    tail = text[match.end():match.end() + 2]
                    if word == "XXX" and tail.startswith("X"):
                        continue
                    marker_counts[word] += 1

    ledger = []
    try:
        ledger = json.loads(read(ROOT / "lab" / "adoptions.json") or "[]")
    except Exception:  # noqa: BLE001
        ledger = []

    gates_result = subprocess.run(
        [sys.executable, "bin/hs.py", "gates"],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
    )
    gates_ok = gates_result.returncode == 0

    fails: list[str] = []
    warns: list[str] = []
    if duplicates:
        fails.append(f"дубли утверждений: {duplicates}")
    if coverage.get("coverage", 0) < 1.0:
        fails.append(f"покрытие {coverage.get('coverage')} < 1.00")
    if not gates_ok:
        fails.append("гейты не зелёные")

    if uncited:
        warns.append(f"артефактов без ссылок в утверждениях: {len(uncited)} ({', '.join(uncited[:5])})")
    if len(covered) < len(gates):
        missing = sorted(set(gates) - covered)
        warns.append(f"гейтов с пробой: {len(covered)} из {len(gates)}; без пробы: {', '.join(missing)}")
    weak_expects = coverage.get("weak_expects", 0)
    descriptive_artifacts = coverage.get("descriptive_artifacts", 0)
    if weak_expects or descriptive_artifacts:
        warns.append(f"строгое покрытие < anchored: слабых ожиданий {weak_expects}, "
                     f"артефактов-описаний {descriptive_artifacts} (anchored 1.00 ≠ проверяемо; ADR-0058)")
    if not (ROOT / "runs" / "index.json").exists():
        warns.append("нет runs/index.json: метрики определяют задачу по имени журнала (план P0.2)")
    if without_guard:
        warns.append(f"отказов без caught_by: {len(without_guard)} из {len(failures)} (план P1.1)")
    if sum(marker_counts.values()) > 0:
        warns.append("следы незавершённости: " + ", ".join(f"{word} {count}" for word, count in marker_counts.most_common()))
    briefs = subprocess.run(
        [sys.executable, "bin/check_briefs.py"],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
    )
    if briefs.returncode != 0:
        warns.append("брифы или правила владельца не проходят проверку (bin/check_briefs.py)")
    if ledger and not any(entry.get("prior_art") for entry in ledger):
        warns.append("в складе решений нет поля prior_art (план P2)")

    lines = [
        "# Аудит (вычислен, не написан)",
        "",
        f"утверждений: {len(claims)} (дублей {len(duplicates)}) · ядро: {core_count()}",
        f"покрытие: {coverage.get('coverage')} (якорено) · строгое: {coverage.get('strict_coverage')} · вердикт: {coverage.get('verdict')}",
        f"отказов: {len(failures)} · гейтов: {len(gates)} · проб: {len(probes)} · гейтов с контролем: {len(covered)}",
        f"артефактов: {len(outputs)} · без ссылок: {len(uncited)}",
        f"решений в складе: {len(ledger)}",
        "",
        "## FAIL (инварианты)",
    ]
    lines += [f"- {item}" for item in fails] or ["- нет"]
    lines += ["", "## WARN (долги, вычисляются каждый запуск)"]
    lines += [f"- {item}" for item in warns] or ["- нет"]
    lines += [
        "",
        "## Что этот аудит не доказывает",
        "",
        "- что найденные отказы — все: часть дефектов не проявилась на наших семействах задач;",
        "- что гейты надёжны: контроль проверяет реакцию на известный дефект, а не на неизвестный;",
        "- что утверждения истинны: проверяется наличие команды и артефакта, а не смысл.",
    ]
    text = "\n".join(lines) + "\n"
    out = ROOT / "research" / "outputs" / "audit-report.txt"
    out.write_text(text, encoding="utf-8")
    print(text)
    if strict and fails:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
