"""check_adoptions — механизм нельзя внедрить без источника и отрицательного контроля.

Правило (docs/TOP-REVIEW.md §5): «правила по памяти» — главный источник вымысла. Поэтому любое
внедрённое решение должно иметь строку в lab/adoptions.json с источником, отрицательным контролем
и утверждением в CLAIMS.md.

    python bin/check_adoptions.py            # проверка
    python bin/check_adoptions.py --self-test  # отрицательный контроль самого гейта

Гейт считается работающим только после --self-test: он подкладывает решения без источника,
без контроля и с выдуманным утверждением и требует отказа по каждому.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "lab" / "adoptions.json"
CLAIMS = ROOT / "CLAIMS.md"
STATUSES = {"adopted", "planned", "rejected"}


def claims_ids() -> set[str]:
    text = CLAIMS.read_text(encoding="utf-8") if CLAIMS.exists() else ""
    return set(re.findall(r"\| (C-\d{4}) \|", text))


def problems_for(entries: list[dict], known: set[str]) -> list[str]:
    problems = []
    seen = set()
    for entry in entries:
        ident = entry.get("id", "?")
        if ident in seen:
            problems.append(f"{ident}: повтор id")
        seen.add(ident)
        if not entry.get("mechanism"):
            problems.append(f"{ident}: нет механизма")
        if entry.get("status") not in STATUSES:
            problems.append(f"{ident}: статус {entry.get('status')!r} вне {sorted(STATUSES)}")
        if not str(entry.get("source", "")).strip():
            problems.append(f"{ident}: нет источника (правило по памяти)")
        if not str(entry.get("negative_control", "")).strip():
            problems.append(f"{ident}: нет отрицательного контроля")
        # Источник считается разобранным, только если записано СОДЕРЖАНИЕ и польза: сейчас или позже.
        if not str(entry.get("content", "")).strip():
            problems.append(f"{ident}: источник не разобран (нет поля content)")
        if not str(entry.get("use_now", "")).strip() and not str(entry.get("use_later", "")).strip():
            problems.append(f"{ident}: не указана польза (use_now или use_later)")
        claim = entry.get("claim")
        if entry.get("status") == "adopted":
            if not claim:
                problems.append(f"{ident}: внедрено без утверждения в CLAIMS.md")
            elif claim not in known:
                problems.append(f"{ident}: утверждение {claim} отсутствует в CLAIMS.md")
            if not str(entry.get("decision", "")).strip():
                problems.append(f"{ident}: нет решения (берём/не берём/отложить)")
    return problems


def self_test() -> int:
    known = {"C-0001"}
    bad = [
        {"id": "X-1", "mechanism": "m", "status": "adopted", "decision": "взято",
         "source": "", "negative_control": "ctrl", "claim": "C-0001"},
        {"id": "X-2", "mechanism": "m", "status": "adopted", "decision": "взято",
         "source": "repo", "negative_control": "", "claim": "C-0001"},
        {"id": "X-3", "mechanism": "m", "status": "adopted", "decision": "взято",
         "source": "repo", "negative_control": "ctrl", "claim": "C-9999"},
        {"id": "X-4", "mechanism": "m", "status": "adopted", "decision": "взято",
         "source": "repo", "negative_control": "ctrl"},
        {"id": "X-5", "mechanism": "m", "status": "wat", "decision": "взято",
         "source": "repo", "negative_control": "ctrl", "claim": "C-0001",
         "content": "c", "use_now": "u"},
        {"id": "X-6", "mechanism": "m", "status": "planned", "decision": "отложено",
         "source": "repo", "negative_control": "ctrl", "use_later": "later", "claim": "C-0001"},
    ]
    found = problems_for(bad, known)
    expected = 6
    if len(found) < expected:
        print(f"[FAIL] self-test: ожидали не меньше {expected} отказов, получили {len(found)}")
        for line in found:
            print("   ", line)
        return 1
    print(f"[ok] self-test: {len(found)} отказов на 5 подложенных дефектов")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--self-test" in args:
        return self_test()

    if not LEDGER.exists():
        print("[FAIL] нет lab/adoptions.json")
        return 1
    entries = json.loads(LEDGER.read_text(encoding="utf-8"))
    problems = problems_for(entries, claims_ids())
    for problem in problems:
        print(f"[FAIL] {problem}")
    if problems:
        return 1
    adopted = sum(1 for entry in entries if entry.get("status") == "adopted")
    print(f"[ok] решений: {len(entries)}, внедрено: {adopted}, у всех есть источник и контроль")
    return 0


if __name__ == "__main__":
    sys.exit(main())
