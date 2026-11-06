"""readme_numbers — числа в README обязаны совпадать с тем, что считает прибор.

Зачем: README — первое, что читают, и первое, что устаревает. Правило: каждое число в разделе
«Где мы сейчас» берётся командой, а не из памяти; расхождение — находка.

    python bin/readme_numbers.py            # сверить
    python bin/readme_numbers.py --fix      # переписать блок чисел
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
BEGIN = "<!-- numbers:begin -->"
END = "<!-- numbers:end -->"


def run(*args: str) -> str:
    result = subprocess.run([sys.executable, *args], cwd=str(ROOT),
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.stdout


def facts() -> dict[str, str]:
    claims = run("bin/audit.py")
    total = re.search(r"утверждений: (\d+)", claims)
    core = re.search(r"ядро: (\d+)", claims)
    coverage = re.search(r"покрытие: ([\d.]+)", claims)
    metrics = run("bin/judge_metrics.py")
    pass1 = re.search(r"pass@1 \(по всем прогонам\): ([\d.]+)", metrics)
    passk = re.search(r"pass\^2[^\n]*?: ([\d.]+)", metrics)
    false_done = re.search(r"false_completion_rate: ([\d.]+)", metrics)
    price = re.search(r"цена принятого: ([\d.]+)", metrics)
    gates = run("bin/hs.py", "gates", "--no-probes")
    gate_count = len(re.findall(r"^\[(?:ok|FAIL)\] ", gates, re.MULTILINE))
    failures = len(list((ROOT / "lab" / "failures").glob("F-*.md")))
    adoptions = json.loads((ROOT / "lab" / "adoptions.json").read_text(encoding="utf-8"))
    probes = run("bin/gate_probe.py")
    caught = re.search(r"поймали: (\d+) из (\d+)", probes)
    return {
        "утверждений": total.group(1) if total else "?",
        "ядро": core.group(1) if core else "?",
        "покрытие": coverage.group(1) if coverage else "?",
        "гейтов": str(gate_count),
        "проб гейтов": f"{caught.group(1)} из {caught.group(2)}" if caught else "?",
        "отказов": str(failures),
        "решений": str(len(adoptions)),
        "pass@1": pass1.group(1) if pass1 else "?",
        "pass^2": passk.group(1) if passk else "?",
        "ложных «готово»": false_done.group(1) if false_done else "?",
        "цена принятого": price.group(1) if price else "?",
    }


def block(values: dict[str, str]) -> str:
    lines = [BEGIN, "| показатель | значение |", "|---|---|"]
    for name, value in values.items():
        lines.append(f"| {name} | {value} |")
    lines.append(END)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="числа README")
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    values = facts()
    text = README.read_text(encoding="utf-8")
    fresh = block(values)
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        end = text.index(END) + len(END)
        current = text[start:end]
    else:
        current = ""
    if args.fix:
        if current:
            text = text[:start] + fresh + text[end:]
        else:
            text = text.rstrip("\n") + "\n\n" + fresh + "\n"
        README.write_text(text, encoding="utf-8")
        print("README обновлён")
        print(fresh)
        return 0
    if current != fresh:
        print("РАСХОЖДЕНИЕ: числа в README не совпадают с прибором")
        print("--- в README:\n" + (current or "(блока нет)"))
        print("--- по прибору:\n" + fresh)
        return 1
    print("[ok] числа README совпадают с прибором")
    return 0


if __name__ == "__main__":
    sys.exit(main())
