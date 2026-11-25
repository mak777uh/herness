"""E-0087 review2: clean disposable Windows selftest for the exact candidate overlay."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
BASELINE = "17f529ae160a1a66b4ec42559c263f9e42a7f1fd"
OVERLAY = [
    "bin/build_reviews_index.py",
    "bin/binary_version.py",
    "bin/gate_docs.py",
    "bin/gate_probe.py",
    "bin/gate_rust.py",
    "bin/gen_capabilities.py",
    "bin/hs.py",
    "bin/lab.py",
    "bin/prereg.py",
    "tests/test_gates_w11.py",
    "tests/test_gates_readonly.py",
    "research/outputs/gate-probes-fast.txt",
    "research/outputs/gate-probes.txt",
    "research/outputs/GATES-READONLY-ROOTSAFE-R1-CORRECTION-INTEGRATION.txt",
    "research/outputs/GATES-READONLY-ROOTSAFE-R1-INTEGRATION.txt",
]
ARTIFACT_PATTERNS = [
    "core-rs/target/release/libhs_core*.rlib",
    "core-rs/target/release/deps/hs_core-*",
    "core-rs/target/release/hs-core",
    "core-rs/target/release/hs-core.exe",
    "core-rs/target/x86_64-unknown-linux-musl/release/libhs_core*.rlib",
    "core-rs/target/x86_64-unknown-linux-musl/release/deps/hs_core-*",
    "core-rs/target/x86_64-unknown-linux-musl/release/hs-core",
    "core-rs/target/x86_64-unknown-linux-musl/release/hs-core.exe",
]


def run(args: list[str], cwd: Path, env: dict[str, str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(cwd), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kwargs)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remove_tree(path: Path) -> None:
    def make_writable(function, filename, _exc_info):
        os.chmod(filename, stat.S_IWRITE | stat.S_IREAD)
        function(filename)

    deadline = time.monotonic() + 10.0
    delay = 0.05
    while True:
        try:
            shutil.rmtree(path, onerror=make_writable)
            return
        except FileNotFoundError:
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.25)


def main() -> int:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    before = {name: digest(SOURCE / name) for name in OVERLAY}
    clone = Path(tempfile.mkdtemp(prefix="e0087-review2-clean-")) / "repo"
    clone.parent.mkdir(parents=True, exist_ok=True)
    try:
        created = run(["git", "clone", "--no-hardlinks", str(SOURCE), str(clone)], SOURCE, env,
                      check=True, timeout=180)
        run(["git", "checkout", "-q", BASELINE], clone, env, check=True, timeout=60)
        for name in OVERLAY:
            source = SOURCE / name
            target = clone / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        artifacts: list[Path] = []
        seen: set[Path] = set()
        for pattern in ARTIFACT_PATTERNS:
            for source in SOURCE.glob(pattern):
                if source in seen or not source.is_file() or source.is_symlink():
                    continue
                seen.add(source)
                relative = source.relative_to(SOURCE)
                target = clone / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                artifacts.append(relative)
        freshest = max(path.stat().st_mtime_ns for path in (SOURCE / "core-rs/src").rglob("*")
                       if path.is_file())
        for relative in artifacts:
            artifact = clone / relative
            normalized = freshest + 1_000_000
            os.utime(artifact, ns=(normalized, normalized))

        run(["git", "add", "--", *OVERLAY], clone, env, check=True, timeout=60)
        run(["git", "-c", "user.name=E-0087 disposable", "-c", "user.email=e0087@example.invalid",
             "commit", "-q", "-m", "disposable E-0087 review2 candidate"], clone, env,
            check=True, timeout=60)
        status_before = run(["git", "status", "--porcelain=v1"], clone, env, check=True).stdout
        head = run(["git", "rev-parse", "HEAD"], clone, env, check=True).stdout.strip()

        print("E-0087 review2 — CLEAN DISPOSABLE WINDOWS SELFTEST")
        print("Baseline HEAD:", BASELINE)
        print("Disposable HEAD:", head)
        print("Clone: local git clone --no-hardlinks; candidate overlay; temporary commit only in clone")
        print("Command: PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 python bin/hs.py selftest")
        print(f"overlay files ({len(OVERLAY)}): {OVERLAY}")
        print(f"Rust artifacts copied ({len(artifacts)}): {[p.as_posix() for p in artifacts]}")
        print("Rust artifact mtime normalized only in disposable clone to freshest source + 1ms")
        print(f"status_before={status_before!r}")

        proc = run([sys.executable, "bin/hs.py", "selftest"], clone, env, check=False, timeout=1800)
        print(proc.stdout, end="")
        if proc.stderr:
            print("--- selftest stderr ---")
            print(proc.stderr, end="")
        status_after = run(["git", "status", "--porcelain=v1"], clone, env, check=True).stdout
        after = {name: digest(SOURCE / name) for name in OVERLAY}
        source_unchanged = before == after
        print(f"status_after={status_after!r}")
        print(f"source_overlay_unchanged={source_unchanged}")
        print(f"exit_code={proc.returncode}")
        verdict = proc.returncode == 0 and not status_before and not status_after and source_unchanged
        print(f"SELFTEST_VERDICT: {'PASS' if verdict else 'FAIL'}")
        return 0 if verdict else 1
    finally:
        remove_tree(clone.parent)


if __name__ == "__main__":
    raise SystemExit(main())
