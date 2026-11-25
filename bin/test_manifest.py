"""Единый manifest тестов: ни один suite не исчезает и не становится zero-test green.

Python-наборы явно разделены на ``custom-main``, ``pytest`` и ``unittest``.
Необязательное ``platforms`` позволяет orchestrator пропустить несовместимый
suite до subprocess и явно напечатать N/A; child сам объявить N/A не может.
Rust-наборы запускаются через ``cargo-test``; каждый бинарь получает отдельный
``cargo-smoke``. Проверка считается исполненной только когда runner напечатал
ненулевой счётчик. Missing/duplicate/unregistered suite и неизвестный runner —
FAIL до запуска. N/A не считается PASS, а all-N/A агрегат остаётся красным.

    python bin/test_manifest.py --check
    python bin/test_manifest.py --run --python-only
    python bin/test_manifest.py --run --rust-only
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__:
    from . import rust_tests
else:
    import rust_tests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "tests" / "test-manifest.json"
SCHEMA_VERSION = "test-manifest-v1"
PYTHON_RUNNERS = {"custom-main", "pytest", "unittest"}
RUST_RUNNERS = {"cargo-test", "cargo-smoke"}
KNOWN_PLATFORMS = {"win32", "linux", "darwin"}
MARKER = re.compile(r"(?m)^\s*\[ok\]\s*")
# Suite-level отказ: «N/A...» либо точная строка «[N/A]». Строки вида
# «[N/A] <case>» — частичные case-level skips legacy suites, не отказ suite.
CHILD_NA = re.compile(r"(?m)^[ \t]*(?:N/A(?::|[ \t]|$).*|\[N/A\])[ \t]*$")
PYTEST_PASSED = re.compile(r"(?m)^(?:=+)?\s*(\d+) passed(?:\s|$)")
UNITTEST_RAN = re.compile(r"(?m)^Ran (\d+) tests?(?:\s|$)")
CARGO_RESULT = re.compile(r"test result: ok\. (\d+) passed;")


@dataclass(frozen=True)
class SuiteResult:
    id: str
    ok: bool
    checks: int
    minimum: int
    returncode: int
    output: str
    note: str = ""
    na: bool = False

    def summary(self) -> str:
        if self.na:
            return f"N/A: suite не выполнялся ({self.note or 'platform'})"
        tail = (self.output.strip().splitlines() or ["нет вывода"])[-1]
        return f"{self.checks}/{self.minimum} checks, rc={self.returncode}: {tail[:180]}"


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _inside(root: Path, relative: str) -> bool:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _source_runner_problems(path: Path, runner: str) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{path.name}: не читается Python source: {exc}"]

    top_functions = {node.name for node in tree.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if runner == "custom-main":
        problems = []
        if "main" not in top_functions:
            problems.append(f"{path.name}: runner=custom-main требует top-level main()")
        if not re.search(r"if\s+__name__\s*==\s*[\"']__main__[\"']", source):
            problems.append(f"{path.name}: runner=custom-main требует __main__ guard")
        return problems
    if runner == "pytest":
        tests = [node.name for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name.startswith("test_")]
        if not tests:
            return [f"{path.name}: runner=pytest не нашёл top-level test_*"]
    if runner == "unittest":
        imports = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
        if "unittest" not in imports:
            return [f"{path.name}: runner=unittest требует import unittest"]
    return []


def validate_manifest(root: Path, manifest: Any) -> list[str]:
    """Проверить manifest и точное покрытие discovered suites без запуска тестов."""
    problems: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest: ожидался JSON-объект"]
    if manifest.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version: ожидался {SCHEMA_VERSION!r}")

    python = manifest.get("python")
    rust = manifest.get("rust")
    if not isinstance(python, list) or not python:
        problems.append("python: нужен непустой массив")
        python = []
    if not isinstance(rust, list) or not rust:
        problems.append("rust: нужен непустой массив")
        rust = []

    ids: set[str] = set()
    python_paths: list[str] = []
    for index, entry in enumerate(python):
        label = f"python[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{label}: ожидался объект")
            continue
        if "platforms" in entry:
            platforms = entry["platforms"]
            if not _string_list(platforms) or not platforms:
                problems.append(f"{label}.platforms: нужен непустой массив строк")
            elif len(set(platforms)) != len(platforms):
                problems.append(f"{label}.platforms: дубликаты недопустимы")
            else:
                unknown = sorted(set(platforms) - KNOWN_PLATFORMS)
                if unknown:
                    problems.append(f"{label}.platforms: неизвестные {unknown}")
        suite_id = entry.get("id")
        if not isinstance(suite_id, str) or not suite_id:
            problems.append(f"{label}.id: нужна непустая строка")
        elif suite_id in ids:
            problems.append(f"{label}.id: дубликат {suite_id!r}")
        else:
            ids.add(suite_id)

        runner = entry.get("runner")
        if runner not in PYTHON_RUNNERS:
            problems.append(f"{label}.runner: неизвестный {runner!r}")
            continue
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative:
            problems.append(f"{label}.path: нужна строка")
            continue
        if Path(relative).is_absolute() or not _inside(root, relative):
            problems.append(f"{label}.path: выход за root: {relative!r}")
            continue
        python_paths.append(relative)
        path = root / relative
        if not path.is_file():
            problems.append(f"{label}.path: нет файла {relative}")
            continue
        if runner == "custom-main":
            if not _positive_int(entry.get("minimum_checks")):
                problems.append(f"{label}.minimum_checks: нужно целое больше нуля")
        else:
            if not _positive_int(entry.get("minimum_collected")):
                problems.append(f"{label}.minimum_collected: нужно целое больше нуля")
            if not _positive_int(entry.get("minimum_executed")):
                problems.append(f"{label}.minimum_executed: нужно целое больше нуля")
            elif (_positive_int(entry.get("minimum_collected"))
                  and entry["minimum_executed"] > entry["minimum_collected"]):
                problems.append(f"{label}: minimum_executed больше minimum_collected")
        problems.extend(f"{label}: {problem}" for problem in _source_runner_problems(path, runner))

    duplicates = sorted({path for path in python_paths if python_paths.count(path) > 1})
    for path in duplicates:
        problems.append(f"python.path: дубликат {path}")
    discovered = sorted(path.relative_to(root).as_posix() for path in (root / "tests").glob("test_*.py"))
    registered = set(python_paths)
    for path in sorted(registered - set(discovered)):
        problems.append(f"python: зарегистрирован отсутствующий suite {path}")
    for path in sorted(set(discovered) - registered):
        problems.append(f"python: suite не зарегистрирован {path}")

    cargo_test_args: list[list[str]] = []
    smoke_binaries: set[str] = set()
    for index, entry in enumerate(rust):
        label = f"rust[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{label}: ожидался объект")
            continue
        suite_id = entry.get("id")
        if not isinstance(suite_id, str) or not suite_id:
            problems.append(f"{label}.id: нужна непустая строка")
        elif suite_id in ids:
            problems.append(f"{label}.id: дубликат {suite_id!r}")
        else:
            ids.add(suite_id)
        runner = entry.get("runner")
        if runner not in RUST_RUNNERS:
            problems.append(f"{label}.runner: неизвестный {runner!r}")
            continue
        args = entry.get("args")
        if not _string_list(args):
            problems.append(f"{label}.args: нужен массив строк")
            continue
        if runner == "cargo-test":
            if not _positive_int(entry.get("minimum_tests")):
                problems.append(f"{label}.minimum_tests: нужно целое больше нуля")
            cargo_test_args.append(args)
        else:
            binary = entry.get("binary")
            if not isinstance(binary, str) or not binary:
                problems.append(f"{label}.binary: нужна непустая строка")
            else:
                smoke_binaries.add(binary)
            if not _positive_int(entry.get("minimum_checks")):
                problems.append(f"{label}.minimum_checks: нужно целое больше нуля")
            if not isinstance(entry.get("expected_rc"), int) or isinstance(entry.get("expected_rc"), bool):
                problems.append(f"{label}.expected_rc: нужно целое")
            if not _string_list(entry.get("stdout_contains")):
                problems.append(f"{label}.stdout_contains: нужен массив строк")
            elif not entry["stdout_contains"] or any(not needle for needle in entry["stdout_contains"]):
                problems.append(f"{label}.stdout_contains: нужны непустые строки")
            if "stdin" in entry and not isinstance(entry["stdin"], str):
                problems.append(f"{label}.stdin: нужна строка")

    if not any("--lib" in args for args in cargo_test_args):
        problems.append("rust: нет cargo-test с --lib")
    if not any("--tests" in args for args in cargo_test_args):
        problems.append("rust: нет cargo-test с --tests")
    binaries = sorted(path.stem for path in (root / "core-rs" / "src" / "bin").glob("*.rs"))
    for binary in sorted(set(binaries) - smoke_binaries):
        problems.append(f"rust: для бинаря {binary} нет cargo-smoke")
    for binary in sorted(smoke_binaries - set(binaries)):
        problems.append(f"rust: cargo-smoke для отсутствующего бинаря {binary}")
    return problems


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest: ожидался JSON-объект")
    return data


def _run(command: list[str], *, root: Path, timeout: int, stdin: str | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(command, cwd=root, input=stdin, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        return 124, stdout + stderr + f"\n[FAIL] timeout после {timeout} с"
    except OSError as exc:
        return 127, f"[FAIL] не удалось запустить {command[0]}: {exc}"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _run_rust_wsl(root: Path, entry: dict, timeout: int) -> tuple[int, str]:
    """Linux-контур на Windows: тот же checkout, offline и без stale release rlib.

    Cargo на DrvFs (`/mnt/c`) может не замечать mtime и оставить прежний
    `libhs_core.rlib`. Поэтому перед каждым Rust entry используется очистка из
    `rust_tests.py`; отсутствие WSL — отказ, а не молчаливый native fallback.
    """
    if entry["runner"] == "cargo-test":
        cargo = ["cargo", "test", "--release", *entry["args"]]
    else:
        cargo = ["cargo", "run", "--release", "--quiet", "--bin", entry["binary"],
                 "--", *entry["args"]]
    core_wsl = shlex.quote(rust_tests.wsl_path(root / "core-rs"))
    script = (f"test -d {core_wsl} || {{ echo 'нет каталога core-rs' >&2; exit 3; }}; "
              f"cd {core_wsl} && {rust_tests.CLEAN} && "
              f"CARGO_NET_OFFLINE=true rustup run stable {shlex.join(cargo)}")
    return _run(["wsl", "-d", "Ubuntu", "--exec", "bash", "-lc", script],
                root=root, timeout=timeout, stdin=entry.get("stdin"))


def run_python_suite(root: Path, entry: dict, timeout: int) -> SuiteResult:
    runner = entry["runner"]
    path = root / entry["path"]
    if runner == "pytest":
        command = [sys.executable, "-m", "pytest", "-q", entry["path"]]
    else:
        command = [sys.executable, entry["path"]]
    returncode, output = _run(command, root=root, timeout=timeout)
    if runner == "custom-main":
        # Ожидаемый отказ может быть напечатан как [FAIL] внутри negative control.
        # Считаем успешные checks; итоговый rc остаётся обязательным вердиктом suite.
        checks = len(MARKER.findall(output))
        minimum = entry["minimum_checks"]
        note = ""
        ok = returncode == 0 and checks >= minimum
    elif runner == "pytest":
        matches = PYTEST_PASSED.findall(output)
        checks = sum(int(value) for value in matches)
        minimum = entry["minimum_executed"]
        note = "pytest не напечатал число passed" if not matches else ""
        ok = returncode == 0 and checks >= minimum
    else:
        matches = UNITTEST_RAN.findall(output)
        checks = sum(int(value) for value in matches)
        minimum = entry["minimum_executed"]
        note = "unittest не напечатал Ran N tests" if not matches else ""
        ok = returncode == 0 and checks >= minimum
    if CHILD_NA.search(output):
        # N/A принадлежит orchestrator и только manifest declaration. Применимый
        # child не может превратить свой rc/stdout в orchestration skip.
        ok = False
        note = "suite объявил N/A на применимой платформе"
    elif returncode == 0 and checks < minimum:
        note = note or "zero/insufficient executed checks"
    return SuiteResult(entry["id"], ok, checks, minimum, returncode, output, note)


def run_rust_suite(root: Path, entry: dict, timeout: int) -> SuiteResult:
    if entry["runner"] == "cargo-test":
        if os.name == "nt":
            returncode, output = _run_rust_wsl(root, entry, timeout)
        else:
            command = ["cargo", "test", "--release", *entry["args"]]
            returncode, output = _run(command, root=root / "core-rs", timeout=timeout)
        checks = sum(int(value) for value in CARGO_RESULT.findall(output))
        minimum = entry["minimum_tests"]
        note = "cargo не напечатал ненулевой test result" if checks == 0 else ""
        ok = returncode == 0 and checks >= minimum
    else:
        if os.name == "nt":
            returncode, output = _run_rust_wsl(root, entry, timeout)
        else:
            command = ["cargo", "run", "--release", "--quiet", "--bin", entry["binary"],
                       "--", *entry["args"]]
            returncode, output = _run(command, root=root / "core-rs", timeout=timeout,
                                      stdin=entry.get("stdin"))
        missing = [needle for needle in entry["stdout_contains"] if needle not in output]
        checks = 0 if missing else 1
        minimum = entry["minimum_checks"]
        note = f"stdout не содержит {missing}" if missing else ""
        ok = returncode == entry["expected_rc"] and not missing
    return SuiteResult(entry["id"], ok, checks, minimum, returncode, output, note)


def _selected(entries: list[dict], only: list[str] | None) -> tuple[list[dict], list[str]]:
    if not only:
        return entries, []
    known = {entry["id"] for entry in entries}
    unknown = sorted(set(only) - known)
    if unknown:
        return [], [f"неизвестный selection: {', '.join(unknown)}"]
    return [entry for entry in entries if entry["id"] in set(only)], []


def _minimum(entry: dict) -> int:
    if entry["runner"] == "custom-main":
        return entry["minimum_checks"]
    if entry["runner"] in {"pytest", "unittest"}:
        return entry["minimum_executed"]
    if entry["runner"] == "cargo-test":
        return entry["minimum_tests"]
    return entry["minimum_checks"]


def _platform_applies(entry: dict, platform: str) -> bool:
    declared = entry.get("platforms")
    return declared is None or platform in declared


def result_counts(results: list[SuiteResult]) -> tuple[int, int, int]:
    """Вернуть (выполнено, провалов, N/A); N/A не входит ни в PASS, ни в FAIL."""
    executed = sum(1 for result in results if not result.na)
    failed = sum(1 for result in results if not result.na and not result.ok)
    na = sum(1 for result in results if result.na)
    return executed, failed, na


def run_manifest(root: Path, manifest: dict, *, python: bool = True, rust: bool = True,
                 only: list[str] | None = None, timeout: int = 900,
                 platform: str | None = None) -> tuple[list[SuiteResult], list[str]]:
    problems = validate_manifest(root, manifest)
    if problems:
        return [], problems
    entries = (manifest["python"] if python else []) + (manifest["rust"] if rust else [])
    selected, problems = _selected(entries, only)
    if problems:
        return [], problems
    current_platform = sys.platform if platform is None else platform
    results: list[SuiteResult] = []
    for entry in selected:
        if entry["runner"] in PYTHON_RUNNERS and not _platform_applies(entry, current_platform):
            results.append(SuiteResult(
                entry["id"], False, 0, _minimum(entry), -1, "",
                f"platforms={entry.get('platforms')}, host={current_platform}", na=True,
            ))
        elif entry["runner"] in PYTHON_RUNNERS:
            results.append(run_python_suite(root, entry, timeout))
        else:
            results.append(run_rust_suite(root, entry, timeout))
    return results, []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="manifest тестов: покрытие и ненулевые счётчики")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="только проверить manifest")
    mode.add_argument("--run", action="store_true", help="запустить выбранные suites")
    mode.add_argument("--list", action="store_true", help="напечатать id suites")
    surface = parser.add_mutually_exclusive_group()
    surface.add_argument("--python-only", action="store_true")
    surface.add_argument("--rust-only", action="store_true")
    parser.add_argument("--only", action="append", default=[], metavar="ID")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.timeout <= 0:
        print("[FAIL] --timeout должен быть больше нуля")
        return 2

    root = args.root.resolve()
    manifest_path = args.manifest or root / "tests" / "test-manifest.json"
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"[FAIL] manifest {manifest_path}: {exc}")
        return 2
    problems = validate_manifest(root, manifest)
    if problems:
        for problem in problems:
            print(f"[FAIL] {problem}")
        return 1

    entries = manifest["python"] + manifest["rust"]
    if args.list:
        for entry in entries:
            print(f"{entry['id']}\t{entry['runner']}")
        return 0
    if args.check:
        print(f"[ok] manifest: {len(manifest['python'])} Python + {len(manifest['rust'])} Rust entries")
        return 0

    python = not args.rust_only
    rust = not args.python_only
    results, problems = run_manifest(root, manifest, python=python, rust=rust,
                                     only=args.only, timeout=args.timeout)
    if problems:
        for problem in problems:
            print(f"[FAIL] {problem}")
        return 2
    for result in results:
        label = "N/A" if result.na else ("ok" if result.ok else "FAIL")
        print(f"[{label}] {result.id}: {result.summary()}")
        if result.na:
            continue
        if not result.ok:
            if result.note:
                print(f"   - {result.note}")
            tail = result.output.strip().splitlines()[-30:]
            for line in tail:
                print(f"   | {line}")
    executed, failed, na = result_counts(results)
    checks = sum(result.checks for result in results)
    print(f" suites: {len(results)}; выполнено: {executed}; N/A: {na}; "
          f"checks: {checks}; провалов: {failed}")
    return 0 if executed > 0 and failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
