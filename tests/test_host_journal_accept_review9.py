"""W07B-REVIEW9: exact metakontrol strict duplicate loader oracle.

Запуск: python tests/test_host_journal_accept_review9.py
Windows и POSIX: 12/12 без N/A. Production и sealed Review8 corpus не изменяются.
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
DUPLICATE = "повторяющийся JSON ключ"
CASES: list[tuple[str, callable]] = []


class OracleRefusalMissing(AssertionError):
    """Strict oracle не распознал обязательный loader refusal."""


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn

    return wrap


def assert_loader_refused(raw: str, diagnostic: str = DUPLICATE) -> tuple[str, str]:
    """Arm B: каждая точная проверка даёт отдельную распознаваемую причину отказа."""
    code, stdout, stderr = cli(raw)
    output = stdout + stderr
    if code != 2:
        raise OracleRefusalMissing("strict loader oracle: expected rc=2")
    if diagnostic not in stderr:
        raise OracleRefusalMissing("strict loader oracle: diagnostic missing")
    if "итог: PASS" in output:
        raise OracleRefusalMissing("strict loader oracle: PASS is not loader refusal")
    if "Traceback" in output:
        raise OracleRefusalMissing("strict loader oracle: traceback is not loader refusal")
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
        assert DUPLICATE not in output, output
        assert "Traceback" not in output, output
        try:
            assert_loader_refused(raw)
        except OracleRefusalMissing:
            return
    raise AssertionError("strict oracle приняла ordinary semantic FAIL")


def assert_oracle_rejects(outcome: tuple[int, str, str], reason: str) -> None:
    """Одно synthetic outcome нарушает ровно одно свойство refusal evidence."""
    try:
        with patch.object(sys.modules[__name__], "cli", return_value=outcome):
            assert_loader_refused("{}")
    except OracleRefusalMissing as exc:
        assert reason in str(exc), exc
        return
    raise AssertionError("strict helper принял невалидное refusal evidence")


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


@case("asymmetric-reverse-loader-refusal")
def _():
    with patch.object(accept, "_criterion_pairs", asymmetric):
        assert_loader_refused(ZERO_LAST)
    with patch.object(accept, "_criterion_pairs", first_key_wins):
        try:
            assert_loader_refused(ZERO_LAST)
        except OracleRefusalMissing:
            return
    raise AssertionError("asymmetric reverse guard принял first-key-wins mutation")


@case("oracle-rejects-wrong-exit-code")
def _():
    assert_oracle_rejects((1, "итог: FAIL\n", DUPLICATE + "\n"), "rc=2")


@case("oracle-rejects-missing-diagnostic")
def _():
    assert_oracle_rejects((2, "", "другая ошибка\n"), "diagnostic")


@case("oracle-rejects-pass-output")
def _():
    assert_oracle_rejects((2, "итог: PASS\n", DUPLICATE + "\n"), "PASS")


@case("oracle-rejects-traceback-output")
def _():
    assert_oracle_rejects((2, "", DUPLICATE + "\nTraceback\n"), "traceback")


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
    assert len(CASES) == 12, len(CASES)
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
    print(f"\nhost journal accept review9: {passed}/{len(CASES)} ok; N/A {na}; провалов: {failed}")
    return 0 if failed == 0 and na == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
