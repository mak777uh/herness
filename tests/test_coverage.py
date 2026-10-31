"""Тест покрытия: битая строка обязана попасть в знаменатель и ухудшить покрытие."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


def run_coverage(registry: Path) -> tuple[int, str]:
    out = registry.parent / "coverage-out.json"
    completed = subprocess.run(
        [sys.executable, "bin/coverage.py", str(registry), "--out", str(out)], cwd=ROOT,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
    return completed.returncode, completed.stdout


HEADER = "# тест\n\n| id | утверждение | тип | команда | артефакт | дата | ожидание |\n|---|---|---|---|---|---|---|\n"


@case("битая строка входит в знаменатель и портит покрытие", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        registry = Path(tmp) / "CLAIMS.md"
        registry.write_text(
            HEADER
            + "| C-0001 | хорошее утверждение | observation | `echo ok` | README.md | 30.10.2026 | `ok` |\n"
            + "| C-0002 | битая строка без колонок | observation | `echo x` |\n",
            encoding="utf-8")
        code, out = run_coverage(registry)
        assert code == 1, out
        assert "утверждений: 2" in out and "битых строк: 1" in out, out
        assert "покрытие: 0.50" in out, out


@case("полностью закрытый реестр даёт CHECKED_ANCHORED", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        registry = Path(tmp) / "CLAIMS.md"
        registry.write_text(
            HEADER
            + "| C-0001 | хорошее утверждение | observation | `echo ok` | README.md | 30.10.2026 | `ok` |\n",
            encoding="utf-8")
        code, out = run_coverage(registry)
        assert code == 0 and "CHECKED_ANCHORED" in out, out


@case("незакрытая запись режет вердикт", False)
def _():
    with tempfile.TemporaryDirectory() as tmp:
        registry = Path(tmp) / "CLAIMS.md"
        registry.write_text(
            HEADER
            + "| C-0001 | без ожидания | observation | `echo ok` | README.md | 30.10.2026 |  |\n",
            encoding="utf-8")
        code, out = run_coverage(registry)
        assert code == 1 and "REFUSED" in out, out


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
    print(f"\nпокрытие: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
