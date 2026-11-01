"""check_briefs — формат внешних брифов и правил владельца.

Две проверки:
  1) каждый research/P*-BRIEF.md самодостаточен: есть разделы «Задача», «Правила ответа»,
     «Что будет сделано» и шапка «как пользоваться» — иначе файл нельзя «кинуть разом» в модель;
  2) каждое активное правило в lab/owner-preferences.json имеет how и check — иначе это пожелание,
     а не правило (комментарий владельца, который никуда не встроился).

    python bin/check_briefs.py
    python bin/check_briefs.py --self-test
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFERENCES = ROOT / "lab" / "owner-preferences.json"
BRIEF_REQUIRED = ["## Задача", "## Правила ответа", "## Что будет сделано", "как пользоваться"]


def brief_problems(paths: list[Path]) -> list[str]:
    problems = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for marker in BRIEF_REQUIRED:
            if marker.lower() not in text:
                problems.append(f"{path.name}: нет раздела «{marker.lstrip('# ')}»")
    return problems


def preference_problems(rules: list[dict]) -> list[str]:
    problems = []
    seen = set()
    for rule in rules:
        ident = rule.get("id", "?")
        if ident in seen:
            problems.append(f"{ident}: повтор id")
        seen.add(ident)
        if not str(rule.get("rule", "")).strip():
            problems.append(f"{ident}: пустое правило")
        if rule.get("status") == "active":
            if not str(rule.get("how", "")).strip():
                problems.append(f"{ident}: не встроено (нет how)")
            if not str(rule.get("check", "")).strip():
                problems.append(f"{ident}: не проверяется (нет check)")
    return problems


def self_test() -> int:
    broken_rule = [{"id": "X-1", "rule": "r", "status": "active", "check": "manual"}]
    broken_rule2 = [{"id": "X-2", "rule": "r", "status": "active", "how": "h"}]
    bad_brief = [ROOT / "lab" / "core-claims.txt"]  # файл без нужных разделов
    found = preference_problems(broken_rule) + preference_problems(broken_rule2) + brief_problems(bad_brief)
    if len(found) < 2 + len(BRIEF_REQUIRED):
        print(f"[FAIL] self-test: ожидали не меньше {2 + len(BRIEF_REQUIRED)} отказов, получили {len(found)}")
        return 1
    print(f"[ok] self-test: {len(found)} отказов на подложенные дефекты")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--self-test" in args:
        return self_test()

    problems = []
    if PREFERENCES.exists():
        rules = json.loads(PREFERENCES.read_text(encoding="utf-8")).get("rules", [])
        problems += preference_problems(rules)
    else:
        problems.append("нет lab/owner-preferences.json")

    briefs = sorted((ROOT / "research").glob("P*-BRIEF.md"))
    if not briefs:
        problems.append("нет ни одного research/P*-BRIEF.md")
    problems += brief_problems(briefs)

    for problem in problems:
        print(f"[FAIL] {problem}")
    if problems:
        return 1
    print(f"[ok] брифов: {len(briefs)}, правил владельца: {len(json.loads(PREFERENCES.read_text(encoding='utf-8'))['rules'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
