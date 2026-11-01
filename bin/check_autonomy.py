"""check_autonomy — гейт правил автономии.

Проверяет две вещи:
  1) структура lab/autonomy-rules.json (обязательные поля, защищённые пути, формат журнала решений);
  2) режим --staged: если в индексе git оказался защищённый путь, в docs/decision-log.md должна быть
     запись про него. Иначе — отказ, чтобы публикацию или «физику мира» нельзя было протащить
     коммитом по привычке.

    python bin/check_autonomy.py                     # структура
    python bin/check_autonomy.py --staged            # индекс git против журнала решений
    python bin/check_autonomy.py --paths CITATION.cff  # проверка конкретных путей (для теста)

Отрицательный контроль обязателен: гейт без проверенного отказа не считается работающим.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "lab" / "autonomy-rules.json"

REQUIRED = ["allowed_without_asking", "needs_owner", "forbidden", "protected_paths", "decision_log"]


def load() -> dict:
    return json.loads(RULES.read_text(encoding="utf-8"))


def structure_problems(rules: dict) -> list[str]:
    problems = []
    for field in REQUIRED:
        if field not in rules:
            problems.append(f"нет поля {field}")
        elif isinstance(rules.get(field), list) and not rules[field]:
            problems.append(f"поле {field} пустое")
    if not isinstance(rules.get("protected_paths"), list):
        problems.append("protected_paths должен быть списком")
    log = rules.get("decision_log")
    if log and not (ROOT / log).exists():
        problems.append(f"журнал решений не найден: {log}")
    return problems


def is_protected(path: str, protected: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    for entry in protected:
        if entry.endswith("/"):
            if normalized.startswith(entry):
                return True
        elif normalized == entry:
            return True
    return False


def logged(path: str, log_path: Path) -> bool:
    """Запись считается только если путь совпадает с ПОЛЕМ строки, а не встречается где-то в тексте.

    Иначе упоминание пути в шапке журнала («публикация: .github/, CITATION.cff») уже «разрешало»
    бы коммит — то есть гейт открывался бы собственным описанием.
    """
    if not log_path.exists():
        return False
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if "|" not in line or line.lstrip().startswith("#"):
            continue
        fields = [field.strip() for field in line.split("|")]
        if path in fields:
            return True
    return False


def staged_paths() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="правила автономии")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--paths", nargs="*", default=None)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    rules = load()
    problems = structure_problems(rules)
    if problems:
        for problem in problems:
            print(f"[FAIL] структура: {problem}")
        return 1
    print("[ok] структура правил автономии")

    paths = args.paths if args.paths is not None else (staged_paths() if args.staged else [])
    if args.paths is None and not args.staged:
        return 0

    log_path = ROOT / rules["decision_log"]
    offenders = [p for p in paths if is_protected(p, rules["protected_paths"]) and not logged(p, log_path)]
    if offenders:
        for path in offenders:
            print(f"[FAIL] защищённый путь без записи в {rules['decision_log']}: {path}")
        print("Добавь строку «дата | путь | причина | кто решил» или убери файл из индекса.")
        return 1
    print(f"[ok] защищённых путей без записи: 0 (проверено {len(paths)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
