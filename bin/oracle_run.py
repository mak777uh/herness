"""oracle_run — прогнать 200 случаев через проверку опоры и посчитать FNR/FPR.

Меряем ТОЛЬКО проверку (`claim_anchor`), а не агента: правильность ответа
записана заранее в `lab/oracle/cases.json` и не зависит от проверки.

    python bin/oracle_run.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "lab" / "oracle" / "cases.json"
OUT = ROOT / "research" / "outputs" / "oracle-cases.txt"


def main() -> int:
    if not CASES.exists():
        print("нет случаев: python bin/oracle_cases.py --build", file=sys.stderr)
        return 2
    data = json.loads(CASES.read_text(encoding="utf-8"))

    # Проверка опоры реализована в Rust и в комнате. Здесь — её точная модель на Python:
    # те же правила, что в claim_anchor (токены, числа словами, вхождение).
    sys.path.insert(0, str(ROOT))
    from bin.oracle_anchor import anchor

    lines = ["# Проверка опоры: измерение ошибок", ""]
    lines.append("Правильность ответа записана заранее и не зависит от проверки.")
    lines.append("")

    tp = fp = tn = fn = 0
    undecided = 0
    by_kind: dict[str, dict[str, int]] = {}

    for case in data:
        verdict = anchor(case["answer"], [case["result"]])
        accepted = verdict is not None
        correct = case["correct"]
        stats = by_kind.setdefault(case["kind"], {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
        if accepted and correct:
            tp += 1
            stats["tp"] += 1
        elif accepted and not correct:
            fp += 1
            stats["fp"] += 1
        elif not accepted and not correct:
            tn += 1
            stats["tn"] += 1
        else:
            fn += 1
            stats["fn"] += 1
            if len(lines) < 400:
                lines.append(f"  ЛОЖНЫЙ ОТКАЗ {case['id']} ({case['kind']}): "
                             f"ответ «{case['answer']}», источник «{case['result'][:50]}»")

    total = tp + fp + tn + fn
    lines.append("")
    lines.append("## Итог")
    lines.append("")
    lines.append(f"случаев: {total}")
    lines.append(f"  TP (правильный принят): {tp}")
    lines.append(f"  TN (неправильный отвергнут): {tn}")
    lines.append(f"  FP (неправильный принят): {fp}")
    lines.append(f"  FN (правильный отвергнут): {fn}")
    lines.append("")
    fnr = fn / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    lines.append(f"**FNR (доля правильных, отвергнутых): {fnr:.1%}**")
    lines.append(f"**FPR (доля неправильных, принятых): {fpr:.1%}**")
    lines.append("")
    lines.append("## По классам")
    lines.append("")
    lines.append("| класс | TP | TN | FP | FN | FNR |")
    lines.append("|---|---|---|---|---|---|")
    for kind, stats in sorted(by_kind.items()):
        k_fnr = stats["fn"] / (stats["tp"] + stats["fn"]) if (stats["tp"] + stats["fn"]) else 0.0
        lines.append(f"| {kind} | {stats['tp']} | {stats['tn']} | {stats['fp']} | {stats['fn']} | {k_fnr:.0%} |")
    lines.append("")
    lines.append("## Что это значит")
    lines.append("")
    if fnr > 0.1:
        lines.append("FNR выше 10 %: проверка отвергает правильные ответы. Это измеренная")
        lines.append("проблема, о которой предупреждает ресёрч (18–59 % в чужих замерах).")
    else:
        lines.append("FNR ниже 10 %: проверка в основном принимает правильные ответы.")
    if fpr > 0.1:
        lines.append("FPR выше 10 %: проверка принимает неправильные ответы.")
    else:
        lines.append("FPR ниже 10 %: проверка в основном отвергает неправильные ответы.")

    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
