"""Тесты проверки границ: соблюдённая и нарушенная граница, извлечение метрики из JSON."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin.assert_bound import extract_json  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


def run_bound(args: list[str]) -> int:
    completed = subprocess.run([sys.executable, "bin/assert_bound.py", *args], cwd=ROOT,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
    return completed.returncode


@case("число достаётся из JSON по пути", False)
def _():
    assert extract_json('{"steps": 4, "other": 1}', "steps") == 4.0


@case("вложенный путь достаётся", False)
def _():
    assert extract_json('{"run": {"steps": 7}}', "run.steps") == 7.0


@case("время укладывается в щедрую границу", False)
def _():
    code = run_bound(["--metric", "time", "--max", "60", "--runs", "1", "--",
                      sys.executable, "-c", "print(1)"])
    assert code == 0, code


@case("нарушенная граница даёт код 1", False)
def _():
    code = run_bound(["--metric", "time", "--max", "0.001", "--runs", "1", "--",
                      sys.executable, "-c", "import time; time.sleep(0.2)"])
    assert code == 1, code


@case("метрика json проверяется по пределу", False)
def _():
    code = run_bound(["--metric", "json", "--path", "steps", "--max", "2", "--runs", "1", "--",
                      sys.executable, "-c", "print('{\"steps\": 3}')"])
    assert code == 1, code


@case("провал команды считается нарушением", False)
def _():
    code = run_bound(["--metric", "time", "--max", "60", "--runs", "1", "--",
                      sys.executable, "-c", "raise SystemExit(3)"])
    assert code == 1, code


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
    print(f"\nграницы: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
