"""E-0087 / W11: обычный gates read-only и root-correct, probes disposable-only.

Это отдельный focused suite. Исторический RED E-0086 не переписывается.
Запуск: python tests/test_gates_w11.py
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import io
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin import gate_probe
from bin import hs
import bin.store  # noqa: F401 — не даём B/seal.py подменить cached package store
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


def init_git(root: Path) -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(["git", "init", "-q"], cwd=str(root), env=env,
                   capture_output=True, text=True, check=True)


def make_gate_root(root: Path) -> None:
    copy_scripts(root, [
        "gate_docs.py", "gate_rust.py", "binary_version.py", "build_reviews_index.py",
        "prereg.py", "lab.py", "gen_capabilities.py", "check_abs_paths.py",
        "selfref.py", "seal.py", "store.py", "verify_journal.py",
    ])
    for name in ("criteria.py", "audit.py", "failures.py"):
        destination = root / "core" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "core" / name, destination)


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
             if name.startswith("gate_") and name != "gate_env" and callable(value)]
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


@contextlib.contextmanager
def hostile_gate_cache():
    """Кэшированные валидаторы другого root намеренно слепые/опасные."""
    controls = {
        "core.criteria": {"problems": lambda _root: []},
        "core.audit": {"problems": lambda _root: []},
        "core.failures": {"problems": lambda _root: []},
        "bin.selfref": {"problems": lambda _root: []},
        "bin.seal": {"verify_all": lambda _root: [], "canonical": lambda text: text},
        "bin.verify_journal": {"verify_run": lambda _root: SimpleNamespace(
            legacy=True, ok=True, broken_at=0, reason="poisoned cache")},
    }
    missing = object()
    saved_modules = {}
    saved_attributes = {}
    for name, attributes in controls.items():
        module = types.ModuleType(name)
        for attribute, value in attributes.items():
            setattr(module, attribute, value)
        saved_modules[name] = sys.modules.get(name, missing)
        sys.modules[name] = module
        parent_name, child = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            saved_attributes[name] = (parent, child, getattr(parent, child, missing))
            setattr(parent, child, module)
    try:
        yield
    finally:
        for name, (parent, child, value) in saved_attributes.items():
            if value is missing:
                delattr(parent, child)
            else:
                setattr(parent, child, value)
        for name, value in saved_modules.items():
            if value is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def run_gates(root: Path, circuit: str = "b") -> int:
    args = SimpleNamespace(root=str(root), circuit=circuit, profile="auto", no_probes=False)
    with contextlib.redirect_stdout(io.StringIO()):
        return hs.cmd_gates(args)


@contextlib.contextmanager
def probe_fixture(root: Path, probes: dict, fast: list[str], sandbox_factory):
    saved = {name: getattr(gate_probe, name) for name in ("ROOT", "PROBES", "FAST", "IN_PLACE")}
    gate_probe.ROOT = root
    (root / "research" / "outputs").mkdir(parents=True, exist_ok=True)
    store = root / "bin" / "store.py"
    store.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "bin" / "store.py", store)
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

        write(a, "docs/CRITERIA.md", "| K1 | x | док | how | artifact |\n")
        write(b, "docs/CRITERIA.md", "| K1 | x | выдуман | how | artifact |\n")
        write(a, "inbox/note.md", "from: a\nto: harness\nkind: finding\nseverity: low\nrepro: cmd\nfinding: x\n")
        write(b, "inbox/note.md", "from: b\nkind: finding\nseverity: low\nrepro: cmd\nfinding: x\n")
        valid_failure = ("id: F-0001\ndate: 25.11.2026\nwhat: x\nclass: x\nprinciple: x\n"
                         "detect: x\ntest: x\ncaught_by: x\n")
        write(a, "lab/failures/F-0001.md", valid_failure)
        write(b, "lab/failures/F-0001.md", "id: F-1\ndate: 25.11.2026\n")
        write(a, "evidence/selfref-baseline.json", json.dumps({"claims": []}))
        write(b, "evidence/selfref-baseline.json", json.dumps({"claims": ["C-0001"]}))

        event = {"seq": 1, "kind": "probe"}
        row = {"event": event, "prev": "genesis"}
        body = json.dumps(row, ensure_ascii=False, sort_keys=True)
        row["hash"] = hashlib.sha256(body.encode()).hexdigest()
        write(a, "runs/run/events.jsonl", json.dumps(row) + "\n")
        row["hash"] = "0" * 64
        write(b, "runs/run/events.jsonl", json.dumps(row) + "\n")

        seal_text = '{"x": 1}\n'
        seal_hash = hashlib.sha256(seal_text.encode()).hexdigest()
        for root, sidecar in ((a, seal_hash), (b, "0" * 64)):
            write(root, "lab/prereg/P.json", seal_text)
            write(root, "lab/prereg/P.json.sha256", sidecar + "\n")

        canonical = "x\n"
        seal_case = [{"name": "x", "input": "x\r\n", "canonical": canonical,
                      "sha256": hashlib.sha256(canonical.encode()).hexdigest()}]
        write(a, "tests/vectors/journal.json", json.dumps({"chain": []}))
        write(b, "tests/vectors/journal.json", json.dumps({"chain": []}))
        write(a, "tests/vectors/seal.json", json.dumps(seal_case))
        bad_case = [dict(seal_case[0], canonical="wrong")]
        write(b, "tests/vectors/seal.json", json.dumps(bad_case))

        with hostile_gate_cache():
            gates = {
                "criteria": hs.gate_criteria,
                "audit": hs.gate_audit,
                "failures": hs.gate_failures,
                "selfref": hs.gate_selfref,
                "journals": hs.gate_journals,
                "seals": hs.gate_seals,
                "vectors": hs.gate_vectors,
            }
            verdicts = {name: (gate(a), gate(b)) for name, gate in gates.items()}
            write(b, "core/criteria.py", "def problems(root):\n    return ['criteria-code-B']\n")
            write(b, "bin/seal.py", "def verify_all(root):\n    return ['seal-code-B']\n")
            criteria_origin = hs.gate_criteria(b)
            seal_origin = hs.gate_seals(b)
        roots_ok = all(left == [] and bool(right) for left, right in verdicts.values())
        origin_ok = criteria_origin == ["criteria-code-B"] and seal_origin == ["seal-code-B"]

        # Timestamp-valid .pyc не должен подменять новые source bytes: прежний код
        # имел тот же размер и mtime, поэтому обычный SourceFileLoader прочитал бы его.
        stale_path = write(b, "bin/stale_gate.py", "def value():\n    return 'old'\n")
        fixed_ns = 1_700_000_000_000_000_000
        os.utime(stale_path, ns=(fixed_ns, fixed_ns))
        py_compile.compile(str(stale_path), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        stale_path.write_bytes(b"def value():\n    return 'new'\n")
        os.utime(stale_path, ns=(fixed_ns, fixed_ns))
        stale_pyc_fresh = hs.load_gate_module(b, "bin/stale_gate.py").value() == "new"
        check(pa == [] and bool(pb) and roots_ok and origin_ok and stale_pyc_fresh,
              f"docs/root validators: docs={pa!r}/{pb!r}, controls={sum(1 for l, r in verdicts.values() if l == [] and bool(r))}/7, "
              f"bad={{{', '.join(f'{name}: {left!r}/{right!r}' for name, (left, right) in verdicts.items() if not (left == [] and bool(right)))}}}, "
              f"origin={criteria_origin!r}/{seal_origin!r}, stale_pyc_fresh={stale_pyc_fresh}")


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
        stale_cap_fresh = False
        for root, prefix in ((a, "a-"), (b, "b-")):
            make_gate_root(root)
            write(root, "core/__init__.py", "")
            tools_path = write(root, "core/tools.py", tool_module(prefix))
            if root == b:
                fixed_ns = 1_700_000_000_000_000_000
                os.utime(tools_path, ns=(fixed_ns, fixed_ns))
                py_compile.compile(str(tools_path), doraise=True,
                                   invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
                tools_path.write_bytes(tools_path.read_bytes().replace(b"'b-", b"'c-"))
                os.utime(tools_path, ns=(fixed_ns, fixed_ns))
            expected = capabilities_for(root)
            if root == b:
                stale_cap_fresh = expected["tools"][0]["id"].startswith("c-")
            write(root, "capabilities.json", json.dumps(expected))
        bad = capabilities_for(b)
        bad["tools"][0]["id"] = "wrong-root"
        write(b, "capabilities.json", json.dumps(bad))
        pa, pb = hs.gate_capabilities(a), hs.gate_capabilities(b)
        check(pa == [] and bool(pb) and stale_cap_fresh,
              f"capabilities dual-root: a={pa!r}, b={pb!r}, stale_pyc_fresh={stale_cap_fresh}")


def test_dual_root_rust() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-rust-") as tmp:
        a, b = Path(tmp) / "a", Path(tmp) / "b"
        for root, source_mtime in ((a, 100), (b, 300)):
            make_gate_root(root)
            source = write(root, "core-rs/src/loopmod.rs", "// source\n")
            journal = write(root, "core-rs/src/journal.rs", 'pub const MAGIC: &[u8; 4] = b"HSJ2";\n')
            artifact = write(root, "core-rs/target/release/libhs_core.rlib", "artifact")
            binary = root / "core-rs/target/release/hs-core"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes(b"xxHSJ2xx")
            os.utime(source, (source_mtime, source_mtime))
            os.utime(journal, (source_mtime, source_mtime))
            os.utime(artifact, (200, 200))
            os.utime(binary, (200, 200))
        pa, pb = hs.gate_rust(a), hs.gate_rust(b)
        check(pa == [] and bool(pb), f"rust dual-root: a={pa!r}, b={pb!r}")


def test_compile_does_not_write_bytecode() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-compile-") as tmp:
        root = Path(tmp)
        copy_scripts(root, ["check_abs_paths.py"])
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
        init_git(root)
        copy_scripts(root, ["verify_claims.py"])
        write(root, "bin/mutate.py", "from pathlib import Path\nPath('derived.txt').write_text('MUTATED')\nprint('MUTATED')\n")
        command = ("python bin/mutate.py" if os.name == "nt"
                   else f'''bash -c '"{sys.executable}" bin/mutate.py' ''')
        write(root, "CLAIMS.md", f"| C-0001 | mutator | test | `{command}` | derived.txt | 25.11.2026 | `MUTATED` |\n")
        write(root, ".gitignore", "ignored.txt\nhome/\nlab/private/\n")
        write(root, "ignored.txt", "IGNORED-SECRET\n")
        write(root, "home/private.txt", "HOME-SECRET\n")
        write(root, "lab/private/secret.txt", "SYNTHETIC-IGNORED-SECRET\n")
        write(root, ".secrets/forced.txt", "FORCED-SECRET\n")
        write(root, ".env", "ENV-SECRET\n")
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        subprocess.run(["git", "add", "-f", ".secrets/forced.txt", ".env", "lab/private/secret.txt"],
                       cwd=str(root), env=env, capture_output=True, check=True)
        if os.name == "nt":
            outside_dir = Path(tmp) / "outside-dir"
            outside_dir.mkdir()
            outside_data = b"OUTSIDE-SECRET\n"
            (outside_dir / "secret.txt").write_bytes(outside_data)
            subprocess.run(["cmd", "/c", "mklink", "/J", str(root / "linkdir"), str(outside_dir)],
                           capture_output=True, text=True, check=True)
            linked = Path("linkdir/secret.txt")
            mode, blob_data = "100644", outside_data
        else:
            outside = Path(tmp) / "outside.txt"
            outside_data = b"OUTSIDE-SECRET\n"
            outside.write_bytes(outside_data)
            os.symlink(outside, root / "link.txt")
            linked = Path("link.txt")
            mode, blob_data = "120000", str(outside).encode("utf-8")
        blob = hashlib.sha1(b"blob " + str(len(blob_data)).encode() + b"\0" + blob_data).hexdigest()
        subprocess.run(["git", "update-index", "--add", "--cacheinfo", f"{mode},{blob},{linked.as_posix()}"],
                       cwd=str(root), env=env, capture_output=True, check=True)
        link_rejected = hs._disposable_source(root, linked) is None
        before = snapshot(root)
        seen = {}
        original_copy = hs.disposable_copy

        def inspecting_copy(check_root):
            clean = original_copy(check_root)
            seen["root"] = clean
            seen["files"] = {path.relative_to(clean).as_posix() for path in clean.rglob("*") if path.is_file()}
            return clean

        hs.disposable_copy = inspecting_copy
        try:
            problems = hs.gate_claims_run(root)
        finally:
            hs.disposable_copy = original_copy
        copied = seen.get("files", set())
        forbidden = {".secrets/forced.txt", ".env", "ignored.txt", "home/private.txt",
                     "lab/private/secret.txt", linked.as_posix()}
        safe = link_rejected and not (copied & forbidden) and {"CLAIMS.md", "bin/mutate.py"} <= copied
        probe_clean = gate_probe.sandbox(root)
        try:
            probe_copied = {path.relative_to(probe_clean).as_posix()
                            for path in probe_clean.rglob("*") if path.is_file()}
        finally:
            gate_probe.remove_disposable(probe_clean)
        probe_safe = not (probe_copied & forbidden) and {"CLAIMS.md", "bin/mutate.py"} <= probe_copied
        original_run = hs.subprocess.run

        def fail_ignored_query(cmd, *args, **kwargs):
            if list(cmd[:3]) == ["git", "ls-files", "-c"] and "-i" in cmd:
                raise OSError("ignored query unavailable")
            return original_run(cmd, *args, **kwargs)

        hs.subprocess.run = fail_ignored_query
        ignored_fail_closed = False
        try:
            try:
                hs.disposable_files(root)
            except hs.MissingData:
                ignored_fail_closed = True
        finally:
            hs.subprocess.run = original_run
        check(problems == [] and safe and probe_safe and ignored_fail_closed
              and not (root / "derived.txt").exists() and snapshot(root) == before,
              f"claims disposable: copied={len(copied)}, forbidden={sorted(copied & forbidden)}, "
              f"probe_forbidden={sorted(probe_copied & forbidden)}, link_rejected={link_rejected}, "
              f"ignored_fail_closed={ignored_fail_closed}, derived={(root / 'derived.txt').exists()}, "
              f"problems={problems!r}")


def test_gate_loop_disables_subprocess_bytecode() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-bytecode-") as tmp:
        root = Path(tmp)
        write(root, "bin/helper.py", "VALUE = 'ok'\n")
        write(root, "bin/core_claims.py", "from helper import VALUE\nprint(VALUE)\n")
        copy_scripts(root, ["seal.py", "store.py"])
        sealed_text = '{"x": 1}\n'
        write(root, "lab/prereg/P.json", sealed_text)
        write(root, "lab/prereg/P.json.sha256", hashlib.sha256(sealed_text.encode()).hexdigest() + "\n")
        for name in ("check_adoptions.py", "check_autonomy.py", "check_policy_parity.py",
                     "gate_requirements.py", "runs_index.py"):
            write(root, f"bin/{name}", "VALUE = 1\n")
        write(root, "runs/accept/a.bin", "x")
        with quiet_gates({"gate_core_claims": hs.gate_core_claims}):
            rc = run_gates(root)
        before_direct = snapshot(root)
        direct_seals = hs.gate_seals(root)
        direct_core = hs.gate_core_claims(root)
        env_calls = []
        original_run = subprocess.run

        def recording_run(_cmd, *args, **kwargs):
            env_calls.append(kwargs.get("env") or {})
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        subprocess.run = recording_run
        try:
            hs.gate_adoptions(root)
            hs.gate_autonomy(root)
            hs.gate_policy_parity(root)
            hs.gate_requirements(root)
            hs.gate_runs_index(root)
        finally:
            subprocess.run = original_run
        after_direct = snapshot(root)
        env_ok = len(env_calls) == 6 and all(item.get("PYTHONDONTWRITEBYTECODE") == "1" for item in env_calls)

        # Настоящий script entrypoint, а не import bin.hs: при частичной Rust-сборке
        # MissingData должен дать штатный rust verdict и summary, без traceback.
        partial_root = None
        cli_stdout = cli_stderr = ""
        try:
            partial_root = hs.disposable_copy(ROOT)
            newest_source = max(path.stat().st_mtime
                                for path in (partial_root / "core-rs/src").glob("*.rs"))
            artifact = partial_root / "core-rs/target/release/libhs_core.rlib"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"synthetic-fresh-rlib")
            os.utime(artifact, (newest_source + 10, newest_source + 10))
            init_git(partial_root)
            cli = subprocess.run(
                [sys.executable, str(partial_root / "bin/hs.py"), "gates",
                 "--root", str(partial_root), "--circuit", "a", "--profile", "full"],
                cwd=str(partial_root), env=hs.gate_env(), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=240,
            )
            cli_stdout, cli_stderr = cli.stdout, cli.stderr
        finally:
            if partial_root is not None:
                gate_probe.remove_disposable(partial_root)
        cli_ok = (
            "Traceback (most recent call last)" not in cli_stderr
            and "bin.hs.MissingData" not in cli_stderr
            and "[FAIL] rust:" in cli_stdout
            and "профиль full: оценено" in cli_stdout
        )
        check(rc == 0 and direct_seals == [] and direct_core == [] and env_ok and cli_ok
              and before_direct == after_direct and not list(root.rglob("__pycache__")),
              f"gate-loop rc={rc}, direct={direct_seals!r}/{direct_core!r}, env={len(env_calls)}/6, "
              f"partial_rust_cli={cli_ok}, bytecode={list(root.rglob('__pycache__'))}, "
              f"cli_stderr_tail={cli_stderr.strip().splitlines()[-1:]}")


def catching_gate(root: Path) -> list[str]:
    return ["caught"] if (root / "defect.txt").exists() else []


def inject_defect(root: Path) -> None:
    (root / "defect.txt").write_text("x", encoding="utf-8")


def test_probe_unknown_selection_fails_before_work() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-unknown-") as tmp:
        root = Path(tmp)
        called = []

        def sandbox_factory(_root):
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

        def sandbox_factory(_root):
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

        def sandbox_factory(_root):
            return Path(tempfile.mkdtemp(prefix="w11-sb-"))

        with probe_fixture(root, {"na": (unavailable, lambda _root: None)}, ["na"], sandbox_factory):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = gate_probe.run(["na"])
        check(rc == 1, f"all-N/A rc={rc}")


def test_probe_never_mutates_source_root() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-inplace-") as tmp:
        root = Path(tmp)
        source = write(root, "state.txt", "original\n")
        before = (hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_mtime_ns)
        sandboxes = []

        def sandbox_factory(_root):
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
        after = (hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_mtime_ns)
        check(rc == 0 and bool(sandboxes) and after == before,
              f"in-place rc={rc}, sandboxes={len(sandboxes)}, source_changed={after != before}")


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
            code = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
                    "from bin import gate_probe\n"
                    "try:\n    with gate_probe.locked(Path(sys.argv[2])):\n        pass\n"
                    "except gate_probe.ProbeBusy:\n    raise SystemExit(3)\n")
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            child = subprocess.run([sys.executable, "-c", code, str(ROOT), str(root)],
                                   capture_output=True, text=True, env=env)
        with gate_probe.locked(root):
            pass
        check(blocked and child.returncode == 3,
              f"second runner blocked={blocked}, child_rc={child.returncode}")


def test_probe_exception_cleanup_and_weak_gate() -> None:
    with tempfile.TemporaryDirectory(prefix="w11-cleanup-") as tmp:
        root = Path(tmp)
        made = []

        def sandbox_factory(_root):
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

        real_root = Path(tmp) / "real"
        real_root.mkdir()
        init_git(real_root)
        write(real_root, "bin/x.py", "VALUE = 1\n")
        write(real_root, ".gitignore", "ignored.txt\n")
        write(real_root, "ignored.txt", "IGNORED-SECRET\n")
        clean = gate_probe.sandbox(real_root)
        try:
            copied = {path.relative_to(clean).as_posix() for path in clean.rglob("*") if path.is_file()}
            safe_sandbox = "bin/x.py" in copied and "ignored.txt" not in copied
        finally:
            gate_probe.remove_disposable(clean)

        before_dirs = set(Path(tempfile.gettempdir()).glob("gate-probe-*"))
        original_copy2 = gate_probe.shutil.copy2

        def fail_copy(*_args, **_kwargs):
            raise OSError("injected copy failure")

        gate_probe.shutil.copy2 = fail_copy
        creation_failed = False
        try:
            gate_probe.sandbox(real_root)
        except OSError:
            creation_failed = True
        finally:
            gate_probe.shutil.copy2 = original_copy2
        partial_clean = set(Path(tempfile.gettempdir()).glob("gate-probe-*")) == before_dirs

        retry_dir = Path(tempfile.mkdtemp(prefix="w11-retry-"))
        write(retry_dir, "locked.txt", "temporary Windows lock\n")
        original_rmtree = gate_probe.shutil.rmtree
        original_sleep = gate_probe.time.sleep
        original_monotonic = gate_probe.time.monotonic
        attempts = []

        def busy_once(target, *args, **kwargs):
            attempts.append(target)
            if len(attempts) == 1:
                busy = PermissionError(errno.EACCES, "sharing violation")
                busy.winerror = 32
                raise busy
            return original_rmtree(target, *args, **kwargs)

        gate_probe.shutil.rmtree = busy_once
        gate_probe.time.sleep = lambda _delay: None
        try:
            gate_probe.remove_disposable(retry_dir)
        finally:
            gate_probe.shutil.rmtree = original_rmtree
            gate_probe.time.sleep = original_sleep
            if retry_dir.exists():
                original_rmtree(retry_dir)
        retried = len(attempts) == 2 and not retry_dir.exists()

        persistent_dir = Path(tempfile.mkdtemp(prefix="w11-persistent-"))
        clock = iter((0.0, 4.0))

        def always_busy(*_args, **_kwargs):
            busy = PermissionError(errno.EACCES, "persistent sharing violation")
            busy.winerror = 32
            raise busy

        gate_probe.shutil.rmtree = always_busy
        gate_probe.time.monotonic = lambda: next(clock)
        gate_probe.time.sleep = lambda _delay: None
        persistent_red = False
        try:
            gate_probe.remove_disposable(persistent_dir)
        except PermissionError:
            persistent_red = persistent_dir.exists()
        finally:
            gate_probe.shutil.rmtree = original_rmtree
            gate_probe.time.monotonic = original_monotonic
            gate_probe.time.sleep = original_sleep
            if persistent_dir.exists():
                original_rmtree(persistent_dir)

        def primary_copy_failure(factory, target):
            original_mkdtemp = gate_probe.tempfile.mkdtemp
            original_copy2 = gate_probe.shutil.copy2

            def fail_primary_copy(*_args, **_kwargs):
                raise RuntimeError("PRIMARY-COPY")

            gate_probe.tempfile.mkdtemp = lambda _prefix=None, **_kwargs: str(target)
            gate_probe.shutil.copy2 = fail_primary_copy
            try:
                factory(real_root)
            finally:
                gate_probe.tempfile.mkdtemp = original_mkdtemp
                gate_probe.shutil.copy2 = original_copy2

        def observe_primary(operation, target, message):
            """Устойчивый cleanup не должен заменять первичную ошибку."""
            clock = iter((0.0, 4.0))
            gate_probe.shutil.rmtree = always_busy
            gate_probe.time.monotonic = lambda: next(clock, 4.0)
            gate_probe.time.sleep = lambda _delay: None
            try:
                operation()
            except BaseException as exc:
                notes = getattr(exc, "__notes__", [])
                return (type(exc) is RuntimeError and str(exc) == message
                        and any("cleanup" in note.lower() for note in notes)
                        and isinstance(exc.__cause__, PermissionError))
            finally:
                gate_probe.shutil.rmtree = original_rmtree
                gate_probe.time.monotonic = original_monotonic
                gate_probe.time.sleep = original_sleep
                if target.exists():
                    original_rmtree(target)
            return False

        sandbox_target = Path(tempfile.mkdtemp(prefix="w11-primary-sandbox-"))
        sandbox_primary = observe_primary(
            lambda: primary_copy_failure(gate_probe.sandbox, sandbox_target), sandbox_target, "PRIMARY-COPY")
        copy_target = Path(tempfile.mkdtemp(prefix="w11-primary-copy-"))
        copy_primary = observe_primary(
            lambda: primary_copy_failure(hs.disposable_copy, copy_target), copy_target, "PRIMARY-COPY")

        selected_root = Path(tmp) / "combined-selected"
        selected_root.mkdir()
        selected_target = Path(tempfile.mkdtemp(prefix="w11-primary-selected-"))

        def selected_sandbox(_root):
            return selected_target

        with probe_fixture(selected_root, {"boom": (lambda _root: [], explode)},
                           ["boom"], selected_sandbox):
            selected_primary = observe_primary(
                lambda: gate_probe.run(["boom"]), selected_target, "injected exception")

        claims_root = Path(tmp) / "combined-claims"
        claims_root.mkdir()
        init_git(claims_root)
        copy_scripts(claims_root, ["verify_claims.py"])
        claims_target = Path(tempfile.mkdtemp(prefix="w11-primary-claims-"))
        original_subprocess_run = hs.subprocess.run
        original_mkdtemp = gate_probe.tempfile.mkdtemp

        def fail_claims_process(cmd, *args, **kwargs):
            if cmd and str(cmd[0]) == sys.executable:
                raise RuntimeError("PRIMARY-CLAIMS")
            return original_subprocess_run(cmd, *args, **kwargs)

        hs.subprocess.run = fail_claims_process
        # Устойчивый cleanup намеренно оставляет только заранее известный fixture-каталог.
        # Без этой подмены тест создавал бы настоящий hs-gates-copy-* и не мог его удалить.
        gate_probe.tempfile.mkdtemp = lambda _prefix=None, **_kwargs: str(claims_target)
        try:
            claims_primary = observe_primary(
                lambda: hs.gate_claims_run(claims_root), claims_target, "PRIMARY-CLAIMS")
        finally:
            gate_probe.tempfile.mkdtemp = original_mkdtemp
            hs.subprocess.run = original_subprocess_run

        before_claims_temps = set(Path(tempfile.gettempdir()).glob("hs-gates-copy-*"))
        # Повторяем реальный cleanup-путь без monkeypatch: случайная утечка tempfile должна
        # превращаться в FAIL этого же 16-го контроля, а не оставаться незамеченной.
        claims_success = Path(tmp) / "combined-claims-success"
        claims_success.mkdir()
        init_git(claims_success)
        copy_scripts(claims_success, ["verify_claims.py"])
        try:
            hs.gate_claims_run(claims_success)
            temp_leak_free = set(Path(tempfile.gettempdir()).glob("hs-gates-copy-*")) == before_claims_temps
        except Exception:
            temp_leak_free = False

        check(raised and cleaned and weak_rc == 1 and safe_sandbox and creation_failed and partial_clean
              and retried and persistent_red and sandbox_primary and copy_primary
              and selected_primary and claims_primary and temp_leak_free,
              f"exception={raised}, cleaned={cleaned}, weak_rc={weak_rc}, safe_sandbox={safe_sandbox}, "
              f"creation_failed={creation_failed}, partial_clean={partial_clean}, "
              f"transient_retry={retried}, persistent_lock_red={persistent_red}, "
              f"primary_sandbox={sandbox_primary}, primary_copy={copy_primary}, "
              f"primary_selected={selected_primary}, primary_claims={claims_primary}, "
              f"temp_leak_free={temp_leak_free}")


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
