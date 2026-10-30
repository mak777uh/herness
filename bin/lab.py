"""Стенд: где мы, что закрыто, что дальше. Проверяет связность реестра.

Правило закрытия (из научного цикла Morphogenesis): результат закрыт, только если есть отчёт с исходом,
строка в реестре и утверждение в CLAIMS. Всё остальное — незакрытый результат.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "lab" / "registry.json"


def load() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def validate(data: dict) -> list[str]:
    problems: list[str] = []
    program = data.get("program", {})
    for field in ("name", "phase", "status_note"):
        if not program.get(field):
            problems.append(f"program.{field} пуст")
    if not program.get("next_hypotheses"):
        problems.append("program.next_hypotheses пуст: не сказано, что дальше")

    preregs = {path.stem for path in (ROOT / "lab" / "prereg").glob("*.json")}
    referenced = set()
    for experiment in data.get("experiments", []):
        exp_id = experiment.get("id", "?")
        prereg = experiment.get("prereg")
        if prereg:
            referenced.add(Path(prereg).stem)
            if not (ROOT / prereg).exists():
                problems.append(f"{exp_id}: файла пре-регистрации нет ({prereg})")
        elif experiment.get("status") not in ("retro", "case"):
            problems.append(f"{exp_id}: нет пре-регистрации, а статус {experiment.get('status')}")
        conclusion = experiment.get("conclusion")
        if experiment.get("status") in ("closed", "retro", "case"):
            if not conclusion:
                problems.append(f"{exp_id}: закрыт без вывода (conclusion)")
            elif not (ROOT / conclusion).exists():
                problems.append(f"{exp_id}: файла вывода нет ({conclusion})")
        claim = experiment.get("claim")
        if claim:
            claims = (ROOT / "CLAIMS.md").read_text(encoding="utf-8")
            if f"| {claim} |" not in claims:
                problems.append(f"{exp_id}: утверждения {claim} нет в CLAIMS.md")

    unlinked = sorted(preregs - referenced)
    for name in unlinked:
        problems.append(f"пре-регистрация {name} не привязана к эксперименту")
    return problems


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "status"
    data = load()

    if command == "validate":
        problems = validate(data)
        for problem in problems:
            print(f"[FAIL] {problem}")
        if not problems:
            print(f"реестр связен: экспериментов {len(data.get('experiments', []))}, "
                  f"следующих гипотез {len(data['program']['next_hypotheses'])}")
        return 0 if not problems else 1

    program = data["program"]
    print(f"программа: {program['name']} | фаза: {program['phase']}")
    print(f"состояние: {program['status_note'][:300]}")
    print("\nэксперименты:")
    for experiment in data.get("experiments", []):
        conclusion = experiment.get("conclusion") or "—"
        exists = "есть" if experiment.get("conclusion") and (ROOT / experiment["conclusion"]).exists() else "нет"
        print(f"  {experiment['id']:<7} {experiment.get('status', '?'):<7} {experiment.get('title', '')[:60]}")
        print(f"          вывод: {conclusion} ({exists})")
    print("\nследующие гипотезы:")
    for hypothesis in program["next_hypotheses"]:
        print("  -", hypothesis)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
