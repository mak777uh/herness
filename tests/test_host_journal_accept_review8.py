"""W07B-REVIEW8: strict duplicate loader oracle.

Запуск: python tests/test_host_journal_accept_review8.py
Windows и POSIX: 7/7 без N/A. Production и sealed Review7 corpus не изменяются.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from bin import accept  # noqa: E402
from test_host_journal_accept_review7 import cli  # noqa: E402

ZERO_FIRST = '{"require_status":"done","max_steps":0,"max_steps":4}'
ZERO_LAST = '{"require_status":"done","max_steps":4,"max_steps":0}'
CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def assert_loader_refused(raw: str, diagnostic: str = "повторяющийся JSON ключ") -> tuple[str, str]:
    """Arm B: только loader refusal, не обычный semantic FAIL по принятому критерию."""
    code, stdout, stderr = cli(raw)
    output = stdout + stderr
    assert code == 2, (code, output)
    assert diagnostic in stderr, output
    assert "итог: PASS" not in output, output
    assert "Traceback" not in output, output
    return stdout, stderr


def first_key_wins(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        result.setdefault(key, value)
    return result


def last_key_wins(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        result[key] = value
    return result


def asymmetric(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key == "max_steps" and result.get(key) == 4 and value == 0:
            raise accept.CriterionError("критерий содержит повторяющийся JSON ключ")
        result.setdefault(key, value)
    return result


def assert_exact_mutation(raw: str, resolver) -> None:
    with patch.object(accept, "_criterion_pairs", resolver):
        code, stdout, stderr = cli(raw)
        output = stdout + stderr
        assert code == 1, (code, output)
        assert "итог: FAIL" in stdout, output
        assert "повторяющийся JSON ключ" not in output, output
        assert "Traceback" not in output, output
        try:
            assert_loader_refused(raw)
        except AssertionError:
            return
    raise AssertionError("strict oracle приняла ordinary semantic FAIL")


@case("duplicate-zero-first-direct")
def _():
    assert_loader_refused(ZERO_FIRST)


@case("duplicate-zero-last-direct")
def _():
    assert_loader_refused(ZERO_LAST)


@case("first-key-wins-exact-semantic-fail")
def _():
    assert_exact_mutation(ZERO_FIRST, first_key_wins)


@case("last-key-wins-exact-semantic-fail")
def _():
    assert_exact_mutation(ZERO_LAST, last_key_wins)


@case("asymmetric-resolver-exact-semantic-fail")
def _():
    assert_exact_mutation(ZERO_FIRST, asymmetric)


@case("unicode-loader-refusal-preserved")
def _():
    stdout, stderr = assert_loader_refused(
        r'{"require_status":"done","task":"VISIBLE-\ud800"}',
        "недопустимую Unicode",
    )
    output = stdout + stderr
    assert "Traceback" not in output, output
    assert "VISIBLE-" not in output, output


@case("valid-unicode-positive-preserved")
def _():
    code, stdout, stderr = cli(
        '{"require_status":"done","task":"найти опору \\ud83d\\ude00"}'
    )
    output = stdout + stderr
    assert code == 0, output
    assert "итог: PASS" in stdout, output
    assert "Traceback" not in output, output


def main() -> int:
    assert len(CASES) == 7, len(CASES)
    passed = failed = na = 0
    for name, fn in CASES:
        try:
            result = fn()
            if result == "N/A":
                na += 1
                print(f"[N/A] {name}")
            else:
                passed += 1
                print(f"[ok] {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[FAIL] {name} — {type(exc).__name__}: {exc}")
    print(f"\nhost journal accept review8: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    return 0 if failed == 0 and na == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
