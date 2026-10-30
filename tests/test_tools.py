"""Тесты инструментов: граница корня и подсчёт.

Находка аудита: проверка пути через префикс строки пропускала соседний каталог с похожим именем.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.tools import GrepTool, ListTool, ReadTool  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


def fixture() -> tuple[Path, Path]:
    base = Path(tempfile.mkdtemp())
    root = base / "harness"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.md").write_text("строка про критерий\n", encoding="utf-8")
    neighbour = base / "harness-secrets"
    neighbour.mkdir()
    (neighbour / "key.pem").write_text("SECRET\n", encoding="utf-8")
    return root, neighbour


@case("чтение внутри корня разрешено", False)
def _():
    root, _neighbour = fixture()
    out = ReadTool(root).run("docs/a.md")
    assert out.ok and "критерий" in out.text, out.text


@case("чтение выше корня запрещено", False)
def _():
    root, _neighbour = fixture()
    assert ReadTool(root).run("../harness-secrets/key.pem").exit_code == 126


@case("сосед с похожим именем не проходит", False)
def _():
    root, _neighbour = fixture()
    out = ReadTool(root).run("../harness-secrets/key.pem")
    assert out.exit_code == 126 and "SECRET" not in out.text, out.text


@case("grep не выходит за корень", False)
def _():
    root, _neighbour = fixture()
    out = GrepTool(root).run("SECRET", glob="*.pem")
    assert "SECRET" not in out.text, out.text


@case("подсчёт по маске даёт число", False)
def _():
    root, _neighbour = fixture()
    out = ListTool(root).run("docs", "*.md", count=True)
    assert "найдено 1" in out.text, out.text


@case("секрет не читается инструментом", False)
def _():
    root, _neighbour = fixture()
    (root / ".secrets").mkdir()
    (root / ".secrets" / "key").write_text("SECRET-VALUE", encoding="utf-8")
    out = ReadTool(root).run(".secrets/key")
    assert out.exit_code == 126 and "SECRET-VALUE" not in out.text, out.text


def main() -> int:
    failed = 0
    for name, should_raise, fn in CASES:
        try:
            fn()
            raised = False
        except AssertionError:
            raised = True
        ok = raised == should_raise
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {name}")
    print(f"\nинструменты: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
