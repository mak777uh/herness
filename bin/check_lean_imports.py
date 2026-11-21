"""check_lean_imports — каждый `.lean` обязан быть достижим из объявленного корня.

Зачем (урок из marfagenez, LESSONS §1). У них `laws/Medium.lean` импортировал 13 файлов
из 48: остальные **35 никогда не компилировались**, а отчёт говорил «48 файлов, 179 теорем».
Счёт вёлся по файлам, а сборка видела только импортированные.

У нас та же форма: `proofs/Proofs.lean` импортирует четыре модуля, а три негативных контроля и
`Probe.lean` в агрегат не входят. Сейчас они собираются отдельными командами — но если завтра
появится седьмой файл и его забудут импортировать, он не скомпилируется, и никто не заметит.

Правило: файл либо достижим из корня, либо объявлен корнем с причиной. Молчаливого «просто лежит»
быть не может.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOFS = ROOT / "proofs"
IMPORT = re.compile(r"^import\s+([A-Za-z0-9_.]+)\s*$")

# Корни: с них начинается обход. Всё остальное обязано быть достижимо.
# `builder` — модуль обязан упоминаться в bin/*.py: корень, который никто не собирает, — это
# файл, о котором все забыли (урок marfagenez: 35 из 48 файлов не компилировались).
ROOTS = {
    "Proofs": {"why": "агрегат: собирается целиком (`lake build`)", "builder": True},
    "Proofs.Negative": {"why": "негативный контроль политики: обязан НЕ собраться", "builder": True},
    "Proofs.PartBridgeNegative": {"why": "негативный контроль моста частей", "builder": True},
    "Proofs.CompositionNegative": {"why": "негативный контроль композиции K9: обязан НЕ собраться", "builder": True},
    "Proofs.BridgeNegative": {"why": "негативный контроль моста: собирает bin/bridge_lean.py", "builder": True},
    "Probe": {"why": "scratch-проба, в агрегат не входит по построению", "builder": False},
}


def module_name(path: Path, base: Path = PROOFS) -> str:
    rel = path.relative_to(base).with_suffix("")
    return ".".join(rel.parts)


def module_path(name: str, base: Path = PROOFS) -> Path:
    return base.joinpath(*name.split(".")).with_suffix(".lean")


def imports_of(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        found = IMPORT.match(line.strip())
        if found:
            out.append(found.group(1))
    return out


def builders() -> str:
    """Текст всех bin/*.py: по нему проверяем, что у корня есть сборщик."""
    parts = []
    for path in sorted((ROOT / "bin").glob("*.py")):
        parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def reachable(base: Path = PROOFS, roots: dict = ROOTS) -> tuple[set[str], list[str]]:
    """Множество достижимых модулей и проблемы с самими корнями."""
    problems = []
    seen: set[str] = set()
    stack = []
    code = builders()
    for name, meta in roots.items():
        path = module_path(name, base)
        if not path.exists():
            problems.append(f"корень {name}: файла нет ({path.name})")
            continue
        if meta.get("builder", True) and name not in code and f'"{name}"' not in code:
            problems.append(f"корень {name}: объявлен, но ни один прибор в bin/ его не собирает")
        stack.append(name)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        for dependency in imports_of(module_path(name, base)):
            if module_path(dependency, base).exists():
                stack.append(dependency)
    return seen, problems


def problems(base: Path = PROOFS, roots: dict = ROOTS) -> list[str]:
    if not base.exists():
        return ["нет каталога proofs/"]
    seen, issues = reachable(base, roots)
    files = {module_name(p, base) for p in base.rglob("*.lean")}
    orphans = sorted(files - seen)
    for name in orphans:
        issues.append(f"{name}: не достижим ни из одного корня — не компилируется и не проверяется")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="достижимость Lean-модулей из корней")
    parser.add_argument("--check", action="store_true", help="проверить и вернуть код")
    parser.parse_args(argv if argv is not None else sys.argv[1:])
    issues = problems()
    for issue in issues:
        print(f"[FAIL] {issue}")
    if not issues:
        total = len(list(PROOFS.rglob("*.lean")))
        print(f"[ok] все {total} модулей достижимы из {len(ROOTS)} корней")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
