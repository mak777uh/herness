"""Стандартный unittest-entry point проверяет manifest, а не запускает suites рекурсивно.

Наборы репозитория имеют разные runners. Их запускает ``bin/test_manifest.py``;
этот файл остаётся небольшим unittest-smoke для внешнего ``unittest discover``.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin.test_manifest import load_manifest, validate_manifest  # noqa: E402


class ManifestRuns(unittest.TestCase):
    def test_suites_are_discovered(self) -> None:
        suites = sorted((ROOT / "tests").glob("test_*.py"))
        self.assertTrue(suites, "в tests/ нет наборов — раннер собирать нечего")

    def test_manifest_covers_every_suite(self) -> None:
        manifest = load_manifest(ROOT / "tests" / "test-manifest.json")
        problems = validate_manifest(ROOT, manifest)
        self.assertFalse(problems, "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
