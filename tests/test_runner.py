"""Тесты собираются раннером: unittest discover должен находить хотя бы один.

Наборы в этом репозитории — скрипты со своей main(). Раннер `unittest discover` их не видит, и внешний
аудит справедливо назвал это дырой: «тестов нет» для стандартного инструмента. Здесь каждый набор
запускается как подпроцесс, и его код возврата становится результатом теста.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = sorted(path.name for path in (ROOT / "tests").glob("test_*.py") if path.name != "test_runner.py")


class SuiteRuns(unittest.TestCase):
    def test_suites_are_discovered(self) -> None:
        self.assertTrue(SUITES, "в tests/ нет наборов — раннер собирать нечего")

    def test_each_suite_exits_zero(self) -> None:
        for suite in SUITES:
            with self.subTest(suite=suite):
                proc = subprocess.run([sys.executable, "tests/" + suite], cwd=str(ROOT),
                                      capture_output=True, text=True, timeout=900,
                                      encoding="utf-8", errors="replace")
                tail = (proc.stdout or "").strip().splitlines()[-1:] or [""]
                self.assertEqual(proc.returncode, 0, f"{suite}: {tail}")


if __name__ == "__main__":
    unittest.main()
