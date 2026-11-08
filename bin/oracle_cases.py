"""oracle_cases — 200 контрольных случаев для измерения ошибок самой проверки.

Из ресёрча (OpenAI SWE-bench audit, аудит 496 траекторий): автоматическая проверка
отвергает правильные ответы в 18–59 % случаев. Наш провал S15 — ровно этот случай:
агент ответил «3», в файле «Три теоремы», проверка сказала «unverified».

Здесь — независимый набор: для каждого случая правильность известна ЗАРАНЕЕ,
без участия проверяемого механизма. Прогон меряет только проверку опоры.

    python bin/oracle_cases.py --build     # записать случаи
    python bin/oracle_cases.py --run       # прогнать и посчитать FNR/FPR
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "lab" / "oracle" / "cases.json"
OUT = ROOT / "research" / "outputs" / "oracle-cases.txt"

# Каждый случай: что «прочитал» агент (результат инструмента), что он ответил,
# и правильный ли ответ — по независимому суждению, записанному здесь заранее.
#
# kind — класс случая, нужен для разбивки.
CASES_DATA = [
    # --- прямое совпадение (40) ---
    *[(f"direct-{i}", "direct",
       f"| C-{270+i} | Утверждение номер {i} | proof |",
       f"C-{270+i}", True) for i in range(1, 21)],
    *[(f"direct-file-{i}", "direct",
       f"docs/ADR-00{i:02d}-test.md: строка {i}",
       f"ADR-00{i:02d}", True) for i in range(1, 21)],

    # --- числа словами (30) ---
    ("word-1", "number-word", "## Три теоремы\n\nПервая...", "3", True),
    ("word-2", "number-word", "## Пять разных механизмов", "5", True),
    ("word-3", "number-word", "## Шесть теорем доказано", "6", True),
    ("word-4", "number-word", "## Четыре уровня", "4", True),
    ("word-5", "number-word", "## Два правила", "2", True),
    ("word-6", "number-word", "## Семь шагов плана", "7", True),
    ("word-7", "number-word", "## Восемь гейтов", "8", True),
    ("word-8", "number-word", "## Девять отказов", "9", True),
    ("word-9", "number-word", "## Десять утверждений", "10", True),
    ("word-10", "number-word", "## Один раздел", "1", True),
    ("word-11", "number-word", "## ТРИ ТЕОРЕМЫ (заглавными)", "3", True),
    ("word-12", "number-word", "## Пять механизмов (с большой)", "5", True),
    ("word-13", "number-word", "## Три теоремы", "3 теоремы", True),
    ("word-14", "number-word", "## Пять механизмов", "пять", True),
    ("word-15", "number-word", "## Шесть теорем", "6 штук", True),
    ("word-16", "number-word", "## Три теоремы", "три", True),
    ("word-17", "number-word", "## Пять механизмов", "5 механизмов", True),
    ("word-18", "number-word", "## Двадцать правил", "20", True),
    ("word-19", "number-word", "## Тридцать гейтов", "30", True),
    ("word-20", "number-word", "## Сто записей", "100", True),
    ("word-21", "number-word", "## Четыре уровня", "4 уровня", True),
    ("word-22", "number-word", "## Девять отказов", "девять", True),
    ("word-23", "number-word", "## Семь шагов", "семь", True),
    ("word-24", "number-word", "## Восемь гейтов", "восемь гейтов", True),
    ("word-25", "number-word", "## Десять утверждений", "десять", True),
    ("word-26", "number-word", "## Один раздел", "один", True),
    ("word-27", "number-word", "## Два правила", "два", True),
    ("word-28", "number-word", "## Три теоремы", "3 (три)", True),
    ("word-29", "number-word", "## Пять механизмов", "5 (пять)", True),
    ("word-30", "number-word", "## Шесть теорем", "6 (шесть)", True),

    # --- перефразирование (30) ---
    ("para-1", "paraphrase", "docs/VERIFICATION-SPEC.md:15 — Три теоремы", "3", True),
    ("para-2", "paraphrase", "docs/VERIFICATION-SPEC.md:15", "VERIFICATION-SPEC.md", True),
    ("para-3", "paraphrase", "docs/NEXT-PLAN.md:47 — План: пять шагов", "5", True),
    ("para-4", "paraphrase", "docs/NEXT-PLAN.md", "NEXT-PLAN.md", True),
    ("para-5", "paraphrase", "README.md: гейтов 29", "29", True),
    ("para-6", "paraphrase", "README.md", "README.md", True),
    ("para-7", "paraphrase", "| C-0276 | Доказано | proof |", "C-0276", True),
    ("para-8", "paraphrase", "| C-0276 | Доказано | proof |", "proof", True),
    ("para-9", "paraphrase", "CLAIMS.md:302", "302", True),
    ("para-10", "paraphrase", "CLAIMS.md:302", "CLAIMS.md", True),
    ("para-11", "paraphrase", "docs/PRINCIPLES.md: ## A. Истина", "A", True),
    ("para-12", "paraphrase", "docs/PRINCIPLES.md: ## A. Истина", "PRINCIPLES.md", True),
    ("para-13", "paraphrase", "docs/eliminations.md: E-0001", "E-0001", True),
    ("para-14", "paraphrase", "docs/eliminations.md: E-0001", "eliminations.md", True),
    ("para-15", "paraphrase", "NOT-CLAIMED.md: NC-001", "NC-001", True),
    ("para-16", "paraphrase", "NOT-CLAIMED.md: NC-001", "NOT-CLAIMED.md", True),
    ("para-17", "paraphrase", "docs/VERIFIABILITY.md: пять механизмов", "5", True),
    ("para-18", "paraphrase", "docs/VERIFIABILITY.md", "VERIFIABILITY.md", True),
    ("para-19", "paraphrase", "docs/VISION-0001: пять частей", "5", True),
    ("para-20", "paraphrase", "docs/VISION-0001", "VISION-0001", True),
    ("para-21", "paraphrase", "docs/TRANSITION-0001: три уровня", "3", True),
    ("para-22", "paraphrase", "docs/TRANSITION-0001", "TRANSITION-0001", True),
    ("para-23", "paraphrase", "failures/F-0035.md: застой", "F-0035", True),
    ("para-24", "paraphrase", "failures/F-0035.md: застой", "F-0035.md", True),
    ("para-25", "paraphrase", "docs/P2P-SEARCH-MODULE.md: три уровня", "3", True),
    ("para-26", "paraphrase", "docs/P2P-SEARCH-MODULE.md", "P2P-SEARCH-MODULE.md", True),
    ("para-27", "paraphrase", "docs/RUST-VERIFICATION-RESULT.md: два harness", "2", True),
    ("para-28", "paraphrase", "docs/RUST-VERIFICATION-RESULT.md", "RUST-VERIFICATION-RESULT.md", True),
    ("para-29", "paraphrase", "docs/VERIFICATION-METHODS.md: шесть шагов", "6", True),
    ("para-30", "paraphrase", "docs/VERIFICATION-METHODS.md", "VERIFICATION-METHODS.md", True),

    # --- несколько источников (30): опора в одном из результатов ---
    ("multi-1", "multi", "docs/A.md: 1\n---\ndocs/B.md: C-0276", "C-0276", True),
    ("multi-2", "multi", "docs/A.md: 1\n---\ndocs/B.md: C-0276", "B.md", True),
    ("multi-3", "multi", "README.md: 29\n---\nCLAIMS.md: 280", "29", True),
    ("multi-4", "multi", "README.md: 29\n---\nCLAIMS.md: 280", "280", True),
    ("multi-5", "multi", "docs/X.md: три\n---\ndocs/Y.md: пять", "3", True),
    ("multi-6", "multi", "docs/X.md: три\n---\ndocs/Y.md: пять", "5", True),
    ("multi-7", "multi", "failures/F-1.md: E-1\n---\nfailures/F-2.md: E-2", "F-1", True),
    ("multi-8", "multi", "failures/F-1.md: E-1\n---\nfailures/F-2.md: E-2", "F-2", True),
    ("multi-9", "multi", "docs/A.md: ADR-001\n---\ndocs/B.md: ADR-002", "ADR-001", True),
    ("multi-10", "multi", "docs/A.md: ADR-001\n---\ndocs/B.md: ADR-002", "ADR-002", True),
    ("multi-11", "multi", "docs/A.md: NC-1\n---\ndocs/B.md: NC-2", "NC-1", True),
    ("multi-12", "multi", "docs/A.md: NC-1\n---\ndocs/B.md: NC-2", "NC-2", True),
    ("multi-13", "multi", "docs/A.md: два\n---\ndocs/B.md: четыре", "2", True),
    ("multi-14", "multi", "docs/A.md: два\n---\ndocs/B.md: четыре", "4", True),
    ("multi-15", "multi", "docs/A.md: шесть\n---\ndocs/B.md: восемь", "6", True),
    ("multi-16", "multi", "docs/A.md: шесть\n---\ndocs/B.md: восемь", "8", True),
    ("multi-17", "multi", "docs/A.md: семь\n---\ndocs/B.md: девять", "7", True),
    ("multi-18", "multi", "docs/A.md: семь\n---\ndocs/B.md: девять", "9", True),
    ("multi-19", "multi", "docs/A.md: десять\n---\ndocs/B.md: один", "10", True),
    ("multi-20", "multi", "docs/A.md: десять\n---\ndocs/B.md: один", "1", True),
    ("multi-21", "multi", "docs/A.md: 100\n---\ndocs/B.md: 50", "100", True),
    ("multi-22", "multi", "docs/A.md: 100\n---\ndocs/B.md: 50", "50", True),
    ("multi-23", "multi", "docs/A.md: 20\n---\ndocs/B.md: 30", "20", True),
    ("multi-24", "multi", "docs/A.md: 20\n---\ndocs/B.md: 30", "30", True),
    ("multi-25", "multi", "docs/A.md: 40\n---\ndocs/B.md: 60", "40", True),
    ("multi-26", "multi", "docs/A.md: 40\n---\ndocs/B.md: 60", "60", True),
    ("multi-27", "multi", "docs/A.md: 11\n---\ndocs/B.md: 12", "11", True),
    ("multi-28", "multi", "docs/A.md: 11\n---\ndocs/B.md: 12", "12", True),
    ("multi-29", "multi", "docs/A.md: 13\n---\ndocs/B.md: 14", "13", True),
    ("multi-30", "multi", "docs/A.md: 13\n---\ndocs/B.md: 14", "14", True),

    # --- неполные источники (20): ответа в источнике НЕТ, агент должен был отказать ---
    *[(f"incomplete-{i}", "incomplete",
       f"docs/A.md: строка {i}, ничего полезного", f"C-{9000+i}", False) for i in range(1, 11)],
    *[(f"incomplete-num-{i}", "incomplete",
       f"docs/B.md: без числа, текст {i}", f"{100+i}", False) for i in range(1, 11)],

    # --- граничные случаи (20) ---
    ("edge-1", "edge", "docs/A.md: 0", "0", True),
    ("edge-2", "edge", "docs/A.md: 1", "1", True),
    ("edge-3", "edge", "docs/A.md: 999999", "999999", True),
    ("edge-4", "edge", "docs/A.md: C-0001", "C-0001", True),
    ("edge-5", "edge", "docs/A.md: a", "a", False),
    ("edge-6", "edge", "docs/A.md: ab", "ab", False),
    ("edge-7", "edge", "docs/A.md: abc", "abc", False),
    ("edge-8", "edge", "docs/A.md: /", "/", False),
    ("edge-9", "edge", "docs/A.md: .", ".", False),
    ("edge-10", "edge", "docs/A.md: _", "_", False),
    ("edge-11", "edge", "docs/A.md: -", "-", False),
    ("edge-12", "edge", "docs/A.md: 12.5", "12.5", True),
    ("edge-13", "edge", "docs/A.md: v1.2.3", "v1.2.3", True),
    ("edge-14", "edge", "docs/A.md: 1e10", "1e10", True),
    ("edge-15", "edge", "docs/A.md: 0x1F", "0x1F", True),
    ("edge-16", "edge", "docs/A.md: 1_000", "1_000", True),
    ("edge-17", "edge", "docs/A.md: 100%", "100%", True),
    ("edge-18", "edge", "docs/A.md: 50/50", "50/50", True),
    ("edge-19", "edge", "docs/A.md: a-b_c.d", "a-b_c.d", True),
    ("edge-20", "edge", "docs/A.md: A1B2C3", "A1B2C3", True),

    # --- противоречащие источники (15): в источнике одно, агент говорит другое ---
    *[(f"contra-{i}", "contradict",
       f"docs/A.md: значение {i}", f"{i + 100}", False) for i in range(1, 8)],
    *[(f"contra-w-{i}", "contradict",
       f"docs/A.md: ## Три теоремы", f"{i + 3}", False) for i in range(1, 8)],

    # --- некорректные ссылки (15): агент ссылается на то, чего не было ---
    *[(f"badref-{i}", "badref",
       f"docs/A.md: строка {i}", f"docs/NONEXISTENT-{i}.md", False) for i in range(1, 8)],
    *[(f"badref-num-{i}", "badref",
       f"docs/A.md: строка {i}", f"C-{8000+i}", False) for i in range(1, 8)],
    ("badref-15", "badref", "docs/A.md: строка 15", "docs/A.md:99999", False),
]


def build() -> int:
    CASES.parent.mkdir(parents=True, exist_ok=True)
    data = [{"id": cid, "kind": kind, "result": result, "answer": answer, "correct": correct}
            for cid, kind, result, answer, correct in CASES_DATA]
    CASES.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    kinds = {}
    for entry in data:
        kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
    print(f"случаев: {len(data)}")
    for kind, count in sorted(kinds.items()):
        print(f"  {kind}: {count}")
    print(f"записано: {CASES.relative_to(ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="контрольные случаи для проверки")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.build:
        return build()
    if args.run:
        print("прогон выполняет bin/oracle_run.py")
        return 0
    print("укажи --build или --run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
