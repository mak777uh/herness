"""audit_harness — внешний взгляд на репозиторий: есть ли у него подсистемы харнесса.

Зачем отдельно от гейтов: гейты проверяют наши утверждения (правдивы ли они), а этот аудит —
наличие механизмов (есть ли чем работать агенту). Это разные вопросы, и смешивать их значит
либо ослаблять гейты, либо выдавать наличие за правдивость.

Пять подсистем по курсу learn-harness-engineering: инструкции, состояние, проверка, рамки,
жизненный цикл. Ничего не «оценивает»: каждая строка — факт из дерева файлов.

    python bin/audit_harness.py            # текущий репозиторий
    python bin/audit_harness.py <каталог>
"""

from __future__ import annotations

import sys
from pathlib import Path

CRITICAL = ("инструкции", "проверка")


def check(root: Path) -> list[tuple[str, bool, str, bool]]:
    """(подсистема, есть ли, чем подтверждено, критична ли)."""
    def any_file(*names: str) -> str:
        for name in names:
            if (root / name).exists():
                return name
        return ""

    def any_glob(*patterns: str) -> str:
        for pattern in patterns:
            found = [path for path in sorted(root.glob(pattern)) if "__pycache__" not in path.as_posix()]
            if found:
                return found[0].as_posix()
        return ""

    rows = [
        ("инструкции", bool(any_file("AGENTS.md", "CLAUDE.md", "README.md")),
         any_file("AGENTS.md", "CLAUDE.md", "README.md") or "нет AGENTS.md/README.md", True),
        ("состояние", bool(any_file("CLAIMS.md") or any_glob("runs/*", "lab/*")),
         any_file("CLAIMS.md") or any_glob("runs/*", "lab/*") or "нет журнала/реестра", False),
        ("проверка", bool(any_glob("tests/*", "bin/hs.py", ".github/workflows/*")),
         any_glob("tests/*", "bin/hs.py", ".github/workflows/*") or "нет тестов и гейтов", True),
        ("рамки", bool(any_glob("accept/*", "feature_list.json", "scope.json")),
         any_glob("accept/*", "feature_list.json", "scope.json") or "нет объявленных критериев", False),
        ("жизненный цикл", bool(any_glob("*init*", "core-rs/*.ps1", "scripts/*")),
         any_glob("*init*", "core-rs/*.ps1", "scripts/*") or "нет инициализации/запуска", False),
    ]
    return rows


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    root = Path(argv[0]) if argv else Path(__file__).resolve().parents[1]
    if not root.is_dir():
        print(f"не каталог: {root}", file=sys.stderr)
        return 2
    rows = check(root)
    print(f"аудит харнесса: {root}")
    missing_critical = 0
    for name, present, evidence, critical in rows:
        mark = "ok" if present else ("НЕТ" if critical else "нет")
        print(f"  [{mark:3}] {name:16} {evidence}")
        if not present and critical:
            missing_critical += 1
    print(f"\nподсистем: {len(rows)}; критичных нет: {missing_critical}")
    return 1 if missing_critical else 0


if __name__ == "__main__":
    sys.exit(main())

