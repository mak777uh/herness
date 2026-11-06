"""readme_numbers — числа в README обязаны совпадать с тем, что уже посчитано.

Важно: этот скрипт НЕ запускает проверки. Он читает готовые артефакты, которые пишут сами
проверки:
    research/outputs/acceptance-metrics.txt   ← bin/judge_metrics.py
    research/outputs/audit-report.txt         ← bin/audit.py
    research/outputs/gate-probes.txt          ← bin/gate_probe.py
    runs/index.json                           ← bin/runs_index.py

Почему так: первая версия запускала judge_metrics, hs.py gates и gate_probe внутри себя. Полный
прогон проб — это 30 инъекций и минуты работы, и сверка README превращалась в зависание (F-0069).

    python bin/readme_numbers.py            # сверить
    python bin/readme_numbers.py --fix      # переписать блок чисел
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
OUT = ROOT / "research" / "outputs"
BEGIN = "<!-- numbers:begin -->"
END = "<!-- numbers:end -->"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def facts() -> dict[str, str]:
    audit = read(OUT / "audit-report.txt")
    metrics = read(OUT / "acceptance-metrics.txt")
    probes = read(OUT / "gate-probes.txt")
    index = read(ROOT / "runs" / "index.json")
    adoptions = read(ROOT / "lab" / "adoptions.json")

    def grab(pattern: str, text: str) -> str:
        found = re.search(pattern, text)
        return found.group(1) if found else "?"

    runs = "?"
    if index:
        try:
            runs = str(len(json.loads(index).get("runs", {})))
        except json.JSONDecodeError:
            runs = "?"
    decisions = "?"
    if adoptions:
        try:
            decisions = str(len(json.loads(adoptions)))
        except json.JSONDecodeError:
            decisions = "?"
    gates = grab(r"гейтов: (\d+)", audit)
    return {
        "утверждений": grab(r"утверждений: (\d+)", audit),
        "ядро": grab(r"ядро: (\d+)", audit),
        "покрытие": grab(r"покрытие: ([\d.]+)", audit),
        "гейтов": gates,
        "проб гейтов": grab(r"поймали: (\d+ из \d+)", probes),
        "журналов в индексе": runs,
        "отказов": str(len(list((ROOT / "lab" / "failures").glob("F-*.md")))),
        "решений": decisions,
        "pass@1": grab(r"pass@1 \(по всем прогонам\): ([\d.]+)", metrics),
        "pass^2": grab(r"pass\^2[^\n]*?: ([\d.]+)", metrics),
        "ложных «готово»": grab(r"false_completion_rate: ([\d.]+)", metrics),
        "цена принятого": grab(r"цена принятого: ([\d.]+)", metrics),
    }


def block(values: dict[str, str]) -> str:
    lines = [BEGIN, "| показатель | значение |", "|---|---|"]
    for name, value in values.items():
        lines.append(f"| {name} | {value} |")
    lines.append(END)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="числа README из готовых артефактов")
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    fresh = block(facts())
    text = README.read_text(encoding="utf-8")
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        end = text.index(END) + len(END)
        current = text[start:end]
    else:
        start = end = -1
        current = ""
    if args.fix:
        text = (text[:start] + fresh + text[end:]) if current else text.rstrip("\n") + "\n\n" + fresh + "\n"
        README.write_text(text, encoding="utf-8")
        print("README обновлён")
        print(fresh)
        return 0
    if current != fresh:
        print("РАСХОЖДЕНИЕ: числа в README не совпадают с артефактами")
        print("--- в README:\n" + (current or "(блока нет)"))
        print("--- по артефактам:\n" + fresh)
        return 1
    print("[ok] числа README совпадают с артефактами")
    return 0


if __name__ == "__main__":
    sys.exit(main())
