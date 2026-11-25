"""E-0087 / W11: обычный gates read-only и root-correct, probes disposable-only.

Это отдельный focused suite. Исторический RED E-0086 не переписывается.
Запуск: python tests/test_gates_w11.py
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin import gate_probe
from bin import hs
import core.tools as _real_core_tools  # noqa: F401 — враждебный module-cache control

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, message: str) -> None:
    RESULTS.append((bool(ok), message))


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def copy_scripts(root: Path, names: list[str]) -> None:
    target = root / "bin"
    target.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(ROOT / "bin" / name, target / name)


def make_gate_root(root: Path) -> None:
    copy_scripts(root, [
        "gate_docs.py", "gate_rust.py", "binary_version.py", "build_reviews_index.py",
        "prereg.py", "lab.py", "gen_capabilities.py", "check_abs_paths.py",
    ])


def snapshot(root: Path) -> dict[str, tuple[str, int]]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            result[path.relative_to(root).as_posix()] = (
                hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns,
            )
    return result


@contextlib.contextmanager
def quiet_gates(overrides=None):
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


def run_gates(root: Path, circuit: str = "b") -> int:
    args = SimpleNamespace(root=str(root), circuit=circuit, profile="auto", no_probes=False)
    with contextlib.redirect_stdout(io.StringIO()):
        return hs.cmd_gates(args)


@contextlib.contextmanager
def probe_fixture(root: Path, probes: dict, fast: list[str], sandbox_factory):
    saved = {name: getattr(gate_probe, name) for name in ("ROOT", "PROBES", "FAST", "IN_PLACE")}
    gate_probe.ROOT = root
    (root / "research" / "outputs").mkdir(parents=True, exist_ok=True)
    gate_probe.PROBES = probes
    gate_probe.FAST = fast
    gate_probe.IN_PLACE = {}
    original_sandbox = gate_probe.sandbox
    gate_probe.sandbox = sandbox_factory
    try:
        yield
    finally:
        gate_probe.sandbox = original_sandbox
        for name, value in saved.items():
            setattr(gate_probe, name, value)


def test_dual_root_docs() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-docs-") as tmp:
        a, b = Path(tmp) / "a", Path(tmp) / "b"
        for root, count in ((a, 1), (b, 2)):
            make_gate_root(root)
            write(root, "CLAIMS.md", "".join(f"| C-{i:04d} | x | test | `true` | README.md | 25.11.2026 | `x` |\n"
                                               for i in range(1, count + 1)))
            write(root, "docs/CONTINUE.md", "`CLAIMS.md` — 1 запис\n")
        pa, pb = hs.gate_docs(a), hs.gate_docs(b)
        check(pa == [] and bool(pb), f"docs dual-root: a={pa!r}, b={pb!r}")


def test_dual_root_lab() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-lab-") as tmp:
        a, b = Path(tmp) / "a", Path(tmp) / "b"
        for root, next_hypotheses in ((a, ["H-X"]), (b, [])):
            make_gate_root(root)
            write(root, "CLAIMS.md", "")
            (root / "lab" / "prereg").mkdir(parents=True)
            write(root, "lab/registry.json", json.dumps({
                "program": {"name": "x", "phase": "x", "status_note": "x",
                            "next_hypotheses": next_hypotheses},
                "experiments": [],
            }))
        pa, pb = hs.gate_lab(a), hs.gate_lab(b)
        check(pa == [] and bool(pb), f"lab dual-root: a={pa!r}, b={pb!r}")


def test_dual_root_prereg() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-prereg-") as tmp:
        a, b = Path(tmp) / "a", Path(tmp) / "b"
        for root in (a, b):
            make_gate_root(root)
        valid = {"id": "P-1", "date": "2026-11-25", "question": "q", "hypothesis": "h",
                 "criterion": "c", "arms": ["a"], "sensitivity": "s"}
        write(a, "lab/prereg/P-1.json", json.dumps(valid))
        write(b, "lab/prereg/P-1.json", "{}")
        pa, pb = hs.gate_prereg(a), hs.gate_prereg(b)
        check(pa == [] and bool(pb), f"prereg dual-root: a={pa!r}, b={pb!r}")


def test_dual_root_reviews() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-reviews-") as tmp:
        a, b = Path(tmp) / "a", Path(tmp) / "b"
        for root in (a, b):
            make_gate_root(root)
        fields = ("id: R-1\ndate: 2026-11-25\nclaim: C-1\nverdict: {verdict}\n"
                  "artifact_checked: research/x.txt\nmethod: m\nwhat_would_kill_it: x\n")
        write(a, "lab/reviews/R-1.md", fields.format(verdict="upheld"))
        write(b, "lab/reviews/R-1.md", fields.format(verdict="maybe"))
        for root in (a, b):
            write(root, "lab/reviews/index.json", json.dumps({"entries": [{"file": "R-1.md"}]}))
        pa, pb = hs.gate_reviews(a), hs.gate_reviews(b)
        check(pa == [] and bool(pb), f"reviews dual-root: a={pa!r}, b={pb!r}")


def tool_module(prefix: str) -> str:
    classes = []
    for name, tool_id in (("ShellTool", "shell"), ("ReadTool", "read"),
                          ("GrepTool", "grep"), ("ListTool", "list")):
        classes.append(f"class {name}:\n    name = {prefix + tool_id!r}\n"
                       "    meta = {'actions': ['act'], 'objects': ['obj'], 'effects': ['read']}\n")
    return "\n".join(classes)


def capabilities_for(root: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(root)
    proc = subprocess.run(
        [sys.executable, "-c", "import json; from bin.gen_capabilities import build; print(json.dumps(build()))"],
        cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return json.loads(proc.stdout)


def test_dual_root_capabilities() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-cap-") as tmp:
        a, b = Path(tmp) / "a", Path(tmp) / "b"
        for root, prefix in ((a, "a-"), (b, "b-")):
            make_gate_root(root)
            write(root, "core/__init__.py", "")
            write(root, "core/tools.py", tool_module(prefix))
            expected = capabilities_for(root)
            write(root, "capabilities.json", json.dumps(expected))
        bad = capabilities_for(b)
        bad["tools"][0]["id"] = "wrong-root"
        write(b, "capabilities.json", json.dumps(bad))
        pa, pb = hs.gate_capabilities(a), hs.gate_capabilities(b)
        check(pa == [] and bool(pb), f"capabilities dual-root: a={pa!r}, b={pb!r}")


def test_dual_root_rust() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-rust-") as tmp:
        a, b = Path(tmp) / "a", Path(tmp) / "b"
        for root, source_mtime in ((a, 100), (b, 300)):
            make_gate_root(root)
            source = write(root, "core-rs/src/loopmod.rs", "// source\n")
            write(root, "core-rs/src/journal.rs", 'pub const MAGIC: &[u8; 4] = b"HSJ2";\n')
            artifact = write(root, "core-rs/target/release/libhs_core.rlib", "artifact")
            binary = root / "core-rs/target/release/hs-core"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes(b"xxHSJ2xx")
            os.utime(source, (source_mtime, source_mtime))
            os.utime(artifact, (200, 200))
            os.utime(binary, (200, 200))
        pa, pb = hs.gate_rust(a), hs.gate_rust(b)
        check(pa == [] and bool(pb), f"rust dual-root: a={pa!r}, b={pb!r}")


def test_compile_does_not_write_bytecode() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-compile-") as tmp:
        root = Path(tmp)
        write(root, "bin/good.py", "VALUE = 1\n")
        before = snapshot(root)
        problems = hs.gate_compile(root)
        after = snapshot(root)
        check(problems == [] and before == after and not list(root.rglob("__pycache__")),
              f"compile wrote or failed: {problems!r}, changed={sorted(set(before) ^ set(after))}")


def test_coverage_tempfile_is_outside_root() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-coverage-") as tmp:
        root = Path(tmp) / "root"
        copy_scripts(root, ["coverage.py", "store.py", "claim_strength.py"])
        write(root, "CLAIMS.md", "")
        artifact = root / "research/claims-coverage.json"
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        subprocess.run([sys.executable, str(root / "bin/coverage.py"), str(root / "CLAIMS.md"),
                        "--out", str(artifact)], cwd=str(root), env=env, check=False,
                       capture_output=True, text=True)
        before = snapshot(root)
        original = subprocess.run
        commands = []

        def recording_run(cmd, *args, **kwargs):
            commands.append([str(item) for item in cmd])
            return original(cmd, *args, **kwargs)

        subprocess.run = recording_run
        try:
            problems = hs.gate_coverage(root)
        finally:
            subprocess.run = original
        out = Path(commands[0][commands[0].index("--out") + 1]) if commands else root / "missing"
        outside = out.resolve() != root.resolve() and root.resolve() not in out.resolve().parents
        check(problems == [] and outside and snapshot(root) == before,
              f"coverage output={out}, outside={outside}, problems={problems!r}")


def test_claims_run_uses_disposable_copy() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-claims-") as tmp:
        root = Path(tmp)
        copy_scripts(root, ["verify_claims.py"])
        write(root, "bin/mutate.py", "from pathlib import Path\nPath('derived.txt').write_text('MUTATED')\nprint('MUTATED')\n")
        write(root, "CLAIMS.md", "| C-0001 | mutator | test | `python bin/mutate.py` | derived.txt | 25.11.2026 | `MUTATED` |\n")
        before = snapshot(root)
        problems = hs.gate_claims_run(root)
        check(problems == [] and not (root / "derived.txt").exists() and snapshot(root) == before,
              f"claims mutated source or failed: derived={(root / 'derived.txt').exists()}, problems={problems!r}")


def test_gate_loop_disables_subprocess_bytecode() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-bytecode-") as tmp:
        root = Path(tmp)
        write(root, "bin/helper.py", "VALUE = 'ok'\n")
        write(root, "bin/core_claims.py", "from helper import VALUE\nprint(VALUE)\n")
        with quiet_gates({"gate_core_claims": hs.gate_core_claims}):
            rc = run_gates(root)
        check(rc == 0 and not list(root.rglob("__pycache__")),
              f"gate-loop rc={rc}, bytecode={list(root.rglob('__pycache__'))}")


def catching_gate(root: Path) -> list[str]:
    return ["caught"] if (root / "defect.txt").exists() else []


def inject_defect(root: Path) -> None:
    (root / "defect.txt").write_text("x", encoding="utf-8")


def test_probe_unknown_selection_fails_before_work() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-unknown-") as tmp:
        root = Path(tmp)
        called = []

        def sandbox_factory():
            called.append(True)
            path = Path(tempfile.mkdtemp(prefix="w11-sb-"))
            return path

        probes = {"known": (catching_gate, inject_defect)}
        with probe_fixture(root, probes, ["known"], sandbox_factory):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = gate_probe.run(["unknown"])
        report = root / "research/outputs/gate-probes.txt"
        check(rc == 2 and not called and not report.exists(),
              f"unknown rc={rc}, sandbox_called={bool(called)}, report={report.exists()}")


def test_probe_auto_full_selection() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-selection-") as tmp:
        root = Path(tmp)
        calls = []

        def sandbox_factory():
            path = Path(tempfile.mkdtemp(prefix="w11-sb-"))
            calls.append(path)
            return path

        probes = {name: (catching_gate, inject_defect) for name in ("fast", "slow", "third")}
        with probe_fixture(root, probes, ["fast"], sandbox_factory):
            with contextlib.redirect_stdout(io.StringIO()):
                auto_rc = gate_probe.run([], profile="auto")
                auto_count = len(calls)
                calls.clear()
                full_rc = gate_probe.run([], profile="full")
                full_count = len(calls)
        check(auto_rc == 0 and full_rc == 0 and auto_count == 1 and full_count == 3,
              f"selection auto={auto_count}, full={full_count}, rc={auto_rc}/{full_rc}")


def test_probe_all_na_is_red() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-na-") as tmp:
        root = Path(tmp)

        def unavailable(_root):
            raise hs.MissingData("нет данных")

        def sandbox_factory():
            return Path(tempfile.mkdtemp(prefix="w11-sb-"))

        with probe_fixture(root, {"na": (unavailable, lambda _root: None)}, ["na"], sandbox_factory):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = gate_probe.run(["na"])
        check(rc == 1, f"all-N/A rc={rc}")


def test_probe_never_mutates_source_root() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-inplace-") as tmp:
        root = Path(tmp)
        source = write(root, "state.txt", "original\n")
        before = snapshot(root)
        sandboxes = []

        def sandbox_factory():
            path = Path(tempfile.mkdtemp(prefix="w11-sb-"))
            (path / "state.txt").write_text("original\n", encoding="utf-8")
            sandboxes.append(path)
            return path

        def gate(check_root):
            return ["caught"] if (check_root / "state.txt").read_text() != "original\n" else []

        def inject(check_root):
            (check_root / "state.txt").write_text("changed\n", encoding="utf-8")

        saved = gate_probe.IN_PLACE
        gate_probe.IN_PLACE = {"canary": "state.txt"}
        try:
            with probe_fixture(root, {"canary": (gate, inject)}, ["canary"], sandbox_factory):
                # probe_fixture очищает IN_PLACE; возвращаем враждебное значение после входа.
                gate_probe.IN_PLACE = {"canary": "state.txt"}
                with contextlib.redirect_stdout(io.StringIO()):
                    rc = gate_probe.run(["canary"])
        finally:
            gate_probe.IN_PLACE = saved
        check(rc == 0 and bool(sandboxes) and snapshot(root) == before,
              f"in-place rc={rc}, sandboxes={len(sandboxes)}, source_changed={snapshot(root) != before}")


def test_probe_lock_blocks_second_runner() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-lock-") as tmp:
        root = Path(tmp)
        with gate_probe.locked(root):
            blocked = False
            try:
                with gate_probe.locked(root):
                    pass
            except gate_probe.ProbeBusy:
                blocked = True
        with gate_probe.locked(root):
            pass
        check(blocked, "second runner was not blocked")


def test_probe_exception_cleanup_and_weak_gate() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-cleanup-") as tmp:
        root = Path(tmp)
        made = []

        def sandbox_factory():
            path = Path(tempfile.mkdtemp(prefix="w11-sb-"))
            made.append(path)
            return path

        def explode(_check_root):
            raise RuntimeError("injected exception")

        with probe_fixture(root, {"boom": (lambda _root: [], explode)}, ["boom"], sandbox_factory):
            raised = False
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    gate_probe.run(["boom"])
            except RuntimeError:
                raised = True
        cleaned = bool(made) and not made[0].exists()

        def weak_gate(_check_root):
            return []

        with probe_fixture(root, {"weak": (weak_gate, inject_defect)}, ["weak"], sandbox_factory):
            with contextlib.redirect_stdout(io.StringIO()):
                weak_rc = gate_probe.run(["weak"])
        check(raised and cleaned and weak_rc == 1,
              f"exception={raised}, cleaned={cleaned}, weak_rc={weak_rc}")


def main() -> int:
    tests = [
        test_dual_root_docs,
        test_dual_root_lab,
        test_dual_root_prereg,
        test_dual_root_reviews,
        test_dual_root_capabilities,
        test_dual_root_rust,
        test_compile_does_not_write_bytecode,
        test_coverage_tempfile_is_outside_root,
        test_claims_run_uses_disposable_copy,
        test_gate_loop_disables_subprocess_bytecode,
        test_probe_unknown_selection_fails_before_work,
        test_probe_auto_full_selection,
        test_probe_all_na_is_red,
        test_probe_never_mutates_source_root,
        test_probe_lock_blocks_second_runner,
        test_probe_exception_cleanup_and_weak_gate,
    ]
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            check(False, f"{test.__name__}: {type(exc).__name__}: {exc}")
    failed = sum(1 for ok, _ in RESULTS if not ok)
    for ok, message in RESULTS:
        print(f"[{'ok' if ok else 'FAIL'}] {message}")
    print(f"\n{len(RESULTS)} checks, {failed} failures")
    return 0 if failed == 0 and len(RESULTS) == 16 else 1


if __name__ == "__main__":
    sys.exit(main())
