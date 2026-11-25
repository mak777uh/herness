"""E-0086: обычный gates не запускает mutation probes; явный runner сохранён.

Запуск: python tests/test_gates_readonly.py
Windows и POSIX: 9/9 без N/A. Секреты и сеть не используются.
"""

from __future__ import annotations

import contextlib
import io
import itertools
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import gate_probe  # noqa: E402
from bin import hs  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


@contextlib.contextmanager
def patched(obj, **values):
    saved = {name: getattr(obj, name) for name in values}
    try:
        for name, value in values.items():
            setattr(obj, name, value)
        yield
    finally:
        for name, value in saved.items():
            setattr(obj, name, value)


@contextlib.contextmanager
def quiet_gates(overrides=None):
    """Не исполнять настоящие gates: проверяется только их orchestration."""
    names = [name for name, value in vars(hs).items()
             if name.startswith("gate_") and callable(value)]
    saved = {name: getattr(hs, name) for name in names}
    try:
        for name in names:
            setattr(hs, name, lambda _root: [])
        for name, value in (overrides or {}).items():
            setattr(hs, name, value)
        yield
    finally:
        for name, value in saved.items():
            setattr(hs, name, value)


def run_gates(root: Path, *, no_probes: bool = False, profile: str = "auto"):
    args = SimpleNamespace(root=str(root), circuit="all", profile=profile, no_probes=no_probes)
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = hs.cmd_gates(args)
    return rc, stdout.getvalue()


def sentinel(*_args, **_kwargs):
    raise AssertionError("IMPLICIT_PROBE_CALLED")


def fixture(root: Path) -> dict[str, Path]:
    files = {
        "lab/prereg/sealed.json": b"sealed\r\n",
        "lab/registry.json": b"registry\r\n",
        "core-rs/src/loopmod.rs": b"source\r\n",
        "docs/CONTINUE.md": b"docs\r\n",
    }
    paths = {}
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        paths[name] = path
    return paths


def test_default_never_calls_probe_runner() -> None:
    with tempfile.TemporaryDirectory() as tmp, quiet_gates(), patched(gate_probe, run=sentinel):
        rc, text = run_gates(Path(tmp))
    check(rc == 0 and "пробы" not in text,
          "обычный gates не вызывает sentinel probe-runner и не печатает probe summary")


def test_legacy_flag_remains_accepted() -> None:
    with tempfile.TemporaryDirectory() as tmp, quiet_gates(), patched(gate_probe, run=sentinel):
        rc, text = run_gates(Path(tmp), no_probes=True)
    check(rc == 0 and "пробы" not in text,
          "legacy --no-probes принимается и также не вызывает probe-runner")


def test_default_does_not_write_probe_report() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def fake_run(*_args, **_kwargs):
            report = root / "research" / "outputs" / "gate-probes-fast.txt"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("поймали: 1 из 1\n", encoding="utf-8")
            print("поймали: 1 из 1")
            return 0

        with quiet_gates(), patched(gate_probe, ROOT=root, run=fake_run):
            rc, _text = run_gates(root)
        report = root / "research" / "outputs" / "gate-probes-fast.txt"
        check(rc == 0 and not report.exists(),
              "обычный gates не пишет gate-probes-fast.txt через probe-runner")


def test_default_preserves_fixture_bytes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = fixture(root)
        before = {name: path.read_bytes() for name, path in paths.items()}

        def mutating_run(*_args, **_kwargs):
            for path in paths.values():
                path.write_bytes(b"MUTATED\n")
            return 0

        with quiet_gates(), patched(gate_probe, ROOT=root, run=mutating_run):
            rc, _text = run_gates(root)
        after = {name: path.read_bytes() for name, path in paths.items()}
        check(rc == 0 and before == after,
              "обычный gates сохраняет exact bytes lab/prereg, registry, Rust source и docs")


def test_default_preserves_fixture_mtime() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = fixture(root)
        fixed = 1_700_000_000_000_000_000
        for path in paths.values():
            os.utime(path, ns=(fixed, fixed))
        before = {name: path.stat().st_mtime_ns for name, path in paths.items()}

        def mutating_run(*_args, **_kwargs):
            for path in paths.values():
                os.utime(path, ns=(fixed + 1_000_000_000, fixed + 1_000_000_000))
            return 0

        with quiet_gates(), patched(gate_probe, ROOT=root, run=mutating_run):
            rc, _text = run_gates(root)
        after = {name: path.stat().st_mtime_ns for name, path in paths.items()}
        check(rc == 0 and before == after,
              "обычный gates сохраняет mtime всех IN_PLACE fixture файлов")


def test_gate_failure_verdict_is_preserved() -> None:
    with tempfile.TemporaryDirectory() as tmp, quiet_gates(
        {"gate_secrets": lambda _root: ["SYNTHETIC_GATE_PROBLEM"]}
    ), patched(gate_probe, run=sentinel):
        rc, text = run_gates(Path(tmp))
    check(rc == 1 and "SYNTHETIC_GATE_PROBLEM" in text and "пробы" not in text,
          "настоящий gate FAIL остаётся rc=1 без добавления probe verdict")


def test_auto_full_na_semantics_are_preserved() -> None:
    def missing(_root):
        raise hs.MissingData("SYNTHETIC_MISSING_DATA")

    with tempfile.TemporaryDirectory() as tmp, quiet_gates(
        {"gate_journals": missing}
    ), patched(gate_probe, run=sentinel):
        auto_rc, auto_text = run_gates(Path(tmp), profile="auto")
        full_rc, full_text = run_gates(Path(tmp), profile="full")
    check(auto_rc == 0 and "[N/A] журналы" in auto_text
          and full_rc == 1 and "[FAIL] журналы" in full_text
          and "пробы" not in auto_text + full_text,
          "auto N/A остаётся rc=0, full N/A становится FAIL rc=1 без probes")


def test_explicit_runner_still_catches_defect() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "research" / "outputs").mkdir(parents=True)
        counter = itertools.count()

        def sandbox():
            path = root / f"copy-{next(counter)}"
            path.mkdir()
            return path

        def gate(copy):
            state = copy / "state.txt"
            return ["seeded defect"] if state.exists() and state.read_text() == "bad" else []

        def inject(copy):
            (copy / "state.txt").write_text("bad", encoding="utf-8")

        stdout = io.StringIO()
        with patched(gate_probe, ROOT=root, PROBES={"canary": (gate, inject)},
                     IN_PLACE=set(), sandbox=sandbox), contextlib.redirect_stdout(stdout):
            rc = gate_probe.run(["canary"], profile="full")
        report = (root / "research" / "outputs" / "gate-probes.txt").read_text(encoding="utf-8")
        check(rc == 0 and "canary" in report and "да" in report,
              "явный probe-runner по-прежнему ловит seeded defect и пишет отдельный отчёт")


def test_explicit_runner_still_rejects_weak_gate() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "research" / "outputs").mkdir(parents=True)
        counter = itertools.count()

        def sandbox():
            path = root / f"copy-{next(counter)}"
            path.mkdir()
            return path

        def weak_gate(_copy):
            return []

        def inject(copy):
            (copy / "state.txt").write_text("bad", encoding="utf-8")

        stdout = io.StringIO()
        with patched(gate_probe, ROOT=root, PROBES={"canary": (weak_gate, inject)},
                     IN_PLACE=set(), sandbox=sandbox), contextlib.redirect_stdout(stdout):
            rc = gate_probe.run(["canary"], profile="full")
        report = (root / "research" / "outputs" / "gate-probes.txt").read_text(encoding="utf-8")
        check(rc == 1 and "НЕТ" in report,
              "явный probe-runner возвращает rc=1, когда gate не замечает дефект")


def main() -> int:
    tests = (
        test_default_never_calls_probe_runner,
        test_legacy_flag_remains_accepted,
        test_default_does_not_write_probe_report,
        test_default_preserves_fixture_bytes,
        test_default_preserves_fixture_mtime,
        test_gate_failure_verdict_is_preserved,
        test_auto_full_na_semantics_are_preserved,
        test_explicit_runner_still_catches_defect,
        test_explicit_runner_still_rejects_weak_gate,
    )
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 — исключение тоже RED
            check(False, f"{test.__name__}: {type(exc).__name__}: {exc}")
    failed_count = sum(1 for flag, _message in RESULTS if not flag)
    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    print(f"проверок: {len(RESULTS)}; провалов: {failed_count}")
    return 0 if failed_count == 0 and len(RESULTS) == 9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
