"""check_abs_paths — в коде не должно быть путей к чекауту харнесса.

Зачем (F-0092, F-0093). `bin/rust_tests.py` собирал `/mnt/c/111/herness/core-rs` — жёстко
записанный каталог. В любом другом клоне тесты шли **не по тому коду**, а вывод был зелёным.
Класс шире одного файла: 31 замена в 24 скриптах, найденных этим же правилом.

Правило узкое намеренно: ловится не любой абсолютный путь, а тот, что указывает на **чекаут
харнесса** (`…/herness`, `…/harness`). Пути к чужим инструментам (Chrome, node-модули) —
отдельный долг и здесь не судятся: у них другая причина и другое лечение.

Докстринги и комментарии не считаются: в них путь — пример, а не адрес, по которому идут.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# Файлы, у которых абсолютный путь — предмет, а не адрес кода.
ALLOW = {
    "bin/local_cleanup.py": "инструмент уборки диска владельца: список чужих каталогов и есть его предмет",
}

SUSPECT = re.compile(r"(?i)(?:^[a-z]:[\\/]|/mnt/[a-z]/)")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """id() узлов, которые являются докстрингами (их не судим)."""
    marked: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            value = body[0].value
            if isinstance(value.value, str):
                marked.add(id(value))
    return marked


def problems(root: Path) -> list[str]:
    out: list[str] = []
    targets = sorted(list((root / "bin").glob("*.py")) + list((root / "core").rglob("*.py")))
    for path in targets:
        rel = path.relative_to(root).as_posix()
        if rel in ALLOW:
            continue
        try:
            # utf-8-sig: файл с BOM иначе не разберётся и молча выпадет из проверки.
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except SyntaxError:
            # синтаксис — предмет гейта компиляции, здесь не дублируем
            continue
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            text = node.value
            lowered = text.lower()
            if "herness" not in lowered and "harness" not in lowered:
                continue
            if not SUSPECT.search(text):
                continue
            out.append(f"{rel}:{node.lineno}: путь к чекауту в литерале: {text[:70]}")
    return out


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    issues = problems(root)
    for issue in issues:
        print(f"[FAIL] {issue}")
    if not issues:
        print(f"[ok] абсолютных путей к чекауту нет (исключений: {len(ALLOW)})")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
