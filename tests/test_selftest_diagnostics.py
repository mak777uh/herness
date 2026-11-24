"""E-0077: selftest diagnostics не меняют verdict, но показывают failed output.

Запуск: python tests/test_selftest_diagnostics.py
Windows и POSIX: 6/6 без N/A. Секреты и сеть не используются.
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import hs  # noqa: E402
from bin import test_manifest  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def formatter(result: test_manifest.SuiteResult) -> str:
    fn = getattr(hs, "selftest_suite_message", None)
    if fn is None:
        raise AssertionError("hs.selftest_suite_message отсутствует")
    return fn(result)


def failed(output: str, note: str = "") -> test_manifest.SuiteResult:
    return test_manifest.SuiteResult("synthetic", False, 0, 1, 1, output, note)


def test_failed_diagnostics() -> None:
    text = formatter(failed("first\nDIAGNOSTIC_MARKER\nlast line"))
    check("0/1" in text and "rc=1" in text and "DIAGNOSTIC_MARKER" in text,
          "failed summary сохраняет checks/rc и содержит диагностический маркер")


def test_tail_bound() -> None:
    output = "\n".join(f"line-{index:02d}" for index in range(1, 36))
    text = formatter(failed(output))
    check("line-06" in text and "line-35" in text and "line-05" not in text,
          "tail содержит последние 30 строк и не печатает более старую")


def test_success_payload_suppression() -> None:
    result = test_manifest.SuiteResult("synthetic", True, 1, 1, 0, "PAYLOAD_MARKER\nclean summary")
    text = formatter(result)
    check("clean summary" in text and "PAYLOAD_MARKER" not in text,
          "successful suite сохраняет summary и не печатает payload")


def test_empty_output() -> None:
    try:
        text = formatter(failed(""))
    except Exception as exc:  # noqa: BLE001 — пустой output обязан быть безопасен
        check(False, f"empty output безопасен ({type(exc).__name__}: {exc})")
        return
    check("нет вывода" in text and "rc=1" in text, "empty output безопасен и сохраняет rc")


def test_note_visibility() -> None:
    text = formatter(failed("tail", "NOTE_MARKER"))
    check("NOTE_MARKER" in text, "failed note видна в диагностике")


def test_cmd_selftest_integration() -> None:
    output = "\n".join(
        ["prefix"] + [f"filler-{index:02d}" for index in range(24)]
        + ["INTEGRATION_MARKER", "tail"]
    )
    result = failed(output)
    saved = (test_manifest.load_manifest, test_manifest.validate_manifest, test_manifest.run_manifest)
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        test_manifest.load_manifest = lambda _path: {}
        test_manifest.validate_manifest = lambda _root, _manifest: []
        test_manifest.run_manifest = lambda *_args, **_kwargs: ([result], [])
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = hs.cmd_selftest(None)
    finally:
        test_manifest.load_manifest, test_manifest.validate_manifest, test_manifest.run_manifest = saved
    text = stdout.getvalue() + stderr.getvalue()
    check(rc == 1 and "INTEGRATION_MARKER" in text,
          "cmd_selftest сохраняет rc=1 и печатает failed suite output")


def main() -> int:
    tests = (
        test_failed_diagnostics,
        test_tail_bound,
        test_success_payload_suppression,
        test_empty_output,
        test_note_visibility,
        test_cmd_selftest_integration,
    )
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 — отсутствие formatter тоже RED
            check(False, f"{test.__name__}: {type(exc).__name__}: {exc}")
    failed_count = 0
    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
        failed_count += 0 if flag else 1
    print(f"проверок: {len(RESULTS)}; провалов: {failed_count}")
    return 0 if failed_count == 0 and len(RESULTS) == 6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
