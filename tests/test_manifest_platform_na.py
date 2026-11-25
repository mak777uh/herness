"""E-0082: 18 controls явного platform N/A в test manifest.

До реализации этот suite обязан быть RED. После реализации: 18/18 на Windows
и POSIX. Несовместимый suite не запускается, N/A не становится PASS, а child
не может объявить orchestration N/A через stdout или return code.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import hs  # noqa: E402
from bin import test_manifest as tm  # noqa: E402

RESULTS: list[tuple[bool, str]] = []
OTHER_PLATFORM = "linux" if sys.platform == "win32" else "win32"


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def entry(path: str = "tests/test_child.py", **extra) -> dict:
    value = {"id": Path(path).name, "path": path, "runner": "custom-main", "minimum_checks": 1}
    value.update(extra)
    return value


def manifest(*python_entries: dict) -> dict:
    return {
        "schema_version": "test-manifest-v1",
        "python": list(python_entries) or [entry()],
        "rust": [
            {"id": "rust:lib", "runner": "cargo-test", "args": ["--lib"], "minimum_tests": 1},
            {"id": "rust:tests", "runner": "cargo-test", "args": ["--tests"], "minimum_tests": 1},
        ],
    }


def write_main(root: Path, name: str, *statements: str) -> Path:
    path = root / "tests" / name
    source = "from pathlib import Path\n\ndef main():\n"
    source += "".join(f"    {statement}\n" for statement in statements)
    source += "\nif __name__ == '__main__':\n    main()\n"
    path.write_text(source, encoding="utf-8")
    return path


def write_manifest(root: Path, value: dict) -> Path:
    path = root / "tests" / "test-manifest.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def make_root(tmp: str) -> Path:
    root = Path(tmp)
    (root / "tests").mkdir()
    return root


def sentinel_statement(sentinel: Path) -> str:
    return f"Path({str(sentinel).replace(chr(92), '/')!r}).write_text('ran', encoding='utf-8')"


def one_result(root: Path, *, timeout: int = 10) -> tm.SuiteResult:
    return tm.run_python_suite(root, entry(), timeout=timeout)


def test_backward_compatible_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        write_main(root, "test_child.py", "print('[ok] child')")
        check(not tm.validate_manifest(root, manifest()),
              "manifest без platforms остаётся обратно совместимым")


def test_valid_platforms_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        write_main(root, "test_child.py", "print('[ok] child')")
        value = manifest(entry(platforms=["win32", "linux"]))
        check(not tm.validate_manifest(root, value),
              "точный непустой platforms без дубликатов принимается")


def test_malformed_platforms_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        write_main(root, "test_child.py", "print('[ok] child')")
        declarations = ([], ["win32", "win32"], ["plan9"], "win32", ["win32", 7])
        rejected = all(any("platforms" in problem for problem in
                           tm.validate_manifest(root, manifest(entry(platforms=value))))
                       for value in declarations)
        check(rejected, "пустой/дубликат/неизвестный/не-список/не-строковый platforms отвергаются")


def test_incompatible_not_executed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        sentinel = root / "sentinel.txt"
        write_main(root, "test_child.py", sentinel_statement(sentinel), "print('[ok] child')")
        value = manifest(entry(platforms=["win32"]))
        results, problems = tm.run_manifest(root, value, python=True, rust=False,
                                            platform="linux", timeout=10)
        check(not problems and len(results) == 1 and not sentinel.exists(),
              "несовместимый suite пропускается до subprocess без sentinel")


def test_skip_result_shape() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        sentinel = root / "sentinel.txt"
        write_main(root, "test_child.py", sentinel_statement(sentinel), "print('[ok] child')")
        value = manifest(entry(platforms=["win32"]))
        results, problems = tm.run_manifest(root, value, python=True, rust=False,
                                            platform="linux", timeout=10)
        result = results[0] if not problems and len(results) == 1 else None
        check(result is not None and result.na and not result.ok and result.checks == 0
              and result.returncode == -1 and not sentinel.exists(),
              "skip result: na=true, ok=false, checks=0, rc=-1")


def test_compatible_executes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        sentinel = root / "sentinel.txt"
        value = manifest(entry(platforms=["win32"]))
        observed = []
        for extra in ((), ("print('[N/A] case skipped')",)):
            sentinel.unlink(missing_ok=True)
            write_main(root, "test_child.py", sentinel_statement(sentinel),
                       "print('[ok] child')", *extra)
            results, problems = tm.run_manifest(root, value, python=True, rust=False,
                                                platform="win32", timeout=10)
            observed.append(not problems and len(results) == 1 and results[0].ok
                            and not results[0].na and results[0].checks == 1 and sentinel.exists())
        check(all(observed),
              "совместимый suite исполняется; case-level [N/A] не заменяет suite PASS")


def test_applicable_rc1_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        write_main(root, "test_child.py", "print('[ok] before failure')", "raise SystemExit(1)")
        result = one_result(root)
        check(not result.ok and not result.na and result.returncode == 1,
              "применимый child с rc=1 остаётся FAIL, na=false")


def test_applicable_rc2_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        write_main(root, "test_child.py", "print('N/A: child refusal')", "raise SystemExit(2)")
        result = one_result(root)
        check(not result.ok and not result.na and result.returncode == 2,
              "применимый child с N/A и rc=2 остаётся FAIL, na=false")


def test_child_na_rc0_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        rejected = []
        for text in ("N/A: self declared", "N/A self declared", "[N/A]"):
            write_main(root, "test_child.py", "print('[ok] forged pass')", f"print({text!r})")
            result = one_result(root)
            rejected.append(not result.ok and not result.na and result.returncode == 0)
        check(all(rejected),
              "child не объявляет N/A через stdout даже с rc=0 и [ok]")


def test_child_na_without_checks_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        write_main(root, "test_child.py", "print('N/A: no execution')")
        result = one_result(root)
        check(not result.ok and not result.na and result.checks == 0,
              "child N/A без checks и rc=0 не становится orchestration N/A")


def test_applicable_zero_checks_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        write_main(root, "test_child.py", "pass")
        result = one_result(root)
        check(not result.ok and not result.na and result.returncode == 0 and result.checks == 0,
              "применимый rc=0 без checks остаётся FAIL")


def test_mixed_counts() -> None:
    passed = tm.SuiteResult("passed", True, 1, 1, 0, "[ok] passed")
    skipped = tm.SuiteResult("skipped", False, 0, 1, -1, "", "platform", na=True)
    executed, failed, na = tm.result_counts([passed, skipped])
    check((executed, failed, na) == (1, 0, 1),
          "mixed aggregate отдельно считает executed=1, failed=0, N/A=1")


def run_manifest_cli(root: Path, manifest_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "bin" / "test_manifest.py"), "--root", str(root),
         "--manifest", str(manifest_path), "--run", "--python-only", "--timeout", "10"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )


def test_mixed_cli() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        write_main(root, "test_pass.py", "print('[ok] passed')")
        write_main(root, "test_skip.py", "print('[ok] skip ran')")
        value = manifest(entry("tests/test_pass.py"),
                         entry("tests/test_skip.py", platforms=[OTHER_PLATFORM]))
        path = write_manifest(root, value)
        proc = run_manifest_cli(root, path)
        text = proc.stdout + proc.stderr
        check(proc.returncode == 0 and "[N/A] test_skip.py" in text
              and "[ok] test_skip.py" not in text and "выполнено: 1" in text and "N/A: 1" in text,
              "mixed CLI: rc=0, отдельный [N/A], skipped suite не [ok]")


def test_all_na_cli() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(tmp)
        write_main(root, "test_skip.py", "print('[ok] skip ran')")
        value = manifest(entry("tests/test_skip.py", platforms=[OTHER_PLATFORM]))
        path = write_manifest(root, value)
        proc = run_manifest_cli(root, path)
        text = proc.stdout + proc.stderr
        check(proc.returncode == 1 and "[N/A] test_skip.py" in text
              and "выполнено: 0" in text and "[ok] test_skip.py" not in text,
              "all-N/A CLI: rc=1, N/A видим и не является PASS")


def test_na_formatter_suppresses_payload() -> None:
    result = tm.SuiteResult("skipped", False, 0, 1, -1, "PRIVATE_PAYLOAD", "platform", na=True)
    text = hs.selftest_suite_message(result)
    check("N/A" in text and "PRIVATE_PAYLOAD" not in text,
          "selftest formatter показывает N/A без child payload")


def run_selftest_with(results: list[tm.SuiteResult]) -> tuple[int, str]:
    saved = (tm.load_manifest, tm.validate_manifest, tm.run_manifest)
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        tm.load_manifest = lambda _path: {}
        tm.validate_manifest = lambda _root, _manifest: []
        tm.run_manifest = lambda *_args, **_kwargs: (results, [])
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = hs.cmd_selftest(None)
    finally:
        tm.load_manifest, tm.validate_manifest, tm.run_manifest = saved
    return rc, stdout.getvalue() + stderr.getvalue()


def test_selftest_mixed() -> None:
    passed = tm.SuiteResult("test_pass.py", True, 1, 1, 0, "[ok] passed")
    skipped = tm.SuiteResult("test_skip.py", False, 0, 1, -1, "", "platform", na=True)
    rc, text = run_selftest_with([passed, skipped])
    check(rc == 0 and "[N/A] test_skip.py" in text and "[ok] test_skip.py" not in text,
          "hs selftest mixed: rc=0 и [N/A], skipped suite не [ok]")


def test_selftest_all_na() -> None:
    skipped = tm.SuiteResult("test_skip.py", False, 0, 1, -1, "", "platform", na=True)
    rc, text = run_selftest_with([skipped])
    check(rc == 1 and "[N/A] test_skip.py" in text and "[ok] test_skip.py" not in text,
          "hs selftest all-N/A: rc=1, N/A не PASS")


def test_real_windows_entry_declared() -> None:
    value = tm.load_manifest(ROOT / "tests" / "test-manifest.json")
    windows = [item for item in value["python"] if item["id"] == "test_bridge_win_isolation.py"]
    check(len(windows) == 1 and windows[0].get("platforms") == ["win32"],
          "реальный Windows-only suite явно объявляет platforms=[win32]")


def main() -> int:
    RESULTS.clear()
    tests = (
        test_backward_compatible_manifest,
        test_valid_platforms_manifest,
        test_malformed_platforms_rejected,
        test_incompatible_not_executed,
        test_skip_result_shape,
        test_compatible_executes,
        test_applicable_rc1_fails,
        test_applicable_rc2_fails,
        test_child_na_rc0_fails,
        test_child_na_without_checks_fails,
        test_applicable_zero_checks_fails,
        test_mixed_counts,
        test_mixed_cli,
        test_all_na_cli,
        test_na_formatter_suppresses_payload,
        test_selftest_mixed,
        test_selftest_all_na,
        test_real_windows_entry_declared,
    )
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 — отсутствующая семантика тоже RED
            check(False, f"{test.__name__}: {type(exc).__name__}: {exc}")
    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"проверок: {len(RESULTS)}; провалов: {failed}")
    return 0 if failed == 0 and len(RESULTS) == 18 else 1


if __name__ == "__main__":
    raise SystemExit(main())
