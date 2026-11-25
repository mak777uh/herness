"""E-0087 review2: real ordinary gates byte/mtime/status snapshot.

The gate command intentionally runs without PYTHONDONTWRITEBYTECODE so accidental
bytecode creation is observable. Only hashes/metadata are printed; file contents
and secrets are never copied into the evidence.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_suffix(".txt")
PRUNED = {
    ".git", "target", "runs", ".venv", "venv", "node_modules", "refs-cache",
    "home", ".secrets", ".ssh",
}


def git_output(args: list[str], env: dict[str, str]) -> str:
    proc = subprocess.run(["git", *args], cwd=str(ROOT), env=env,
                          capture_output=True, check=True)
    return proc.stdout.decode("utf-8", "surrogateescape")


def source_state(env: dict[str, str]) -> dict[str, tuple]:
    names = git_output(["ls-files", "-c", "-o", "--exclude-standard", "-z"], env)
    state: dict[str, tuple] = {}
    for name in sorted({item for item in names.split("\0") if item}):
        path = ROOT / name
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if path.is_symlink():
            state[name] = ("symlink", os.readlink(path), info.st_mtime_ns)
        elif path.is_file():
            state[name] = ("file", hashlib.sha256(path.read_bytes()).hexdigest(),
                           info.st_mtime_ns)
    return state


def cache_state() -> dict[str, tuple[int, int]]:
    state: dict[str, tuple[int, int]] = {}
    for directory, dirs, files in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in PRUNED]
        current = Path(directory)
        if "__pycache__" not in current.relative_to(ROOT).parts:
            continue
        for name in files:
            path = current / name
            try:
                info = path.stat()
            except FileNotFoundError:
                continue
            state[path.relative_to(ROOT).as_posix()] = (info.st_mtime_ns, info.st_size)
    return state


def delta(before: dict, after: dict) -> tuple[list[str], list[str], list[str]]:
    changed = sorted(name for name in before.keys() & after.keys()
                     if before[name] != after[name])
    added = sorted(after.keys() - before.keys())
    removed = sorted(before.keys() - after.keys())
    return changed, added, removed


def main() -> int:
    env = os.environ.copy()
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["GIT_OPTIONAL_LOCKS"] = "0"

    before = source_state(env)
    cache_before = cache_state()
    status_before = git_output(["status", "--porcelain=v1"], env)
    proc = subprocess.run([sys.executable, "bin/hs.py", "gates", "--profile", "auto"],
                          cwd=str(ROOT), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900)
    after = source_state(env)
    cache_after = cache_state()
    status_after = git_output(["status", "--porcelain=v1"], env)

    changed, added, removed = delta(before, after)
    cache_changed, cache_added, cache_removed = delta(cache_before, cache_after)
    passed = (proc.returncode == 0 and not changed and not added and not removed
              and not cache_changed and not cache_added and not cache_removed
              and status_before == status_after)
    lines = [
        "E-0087 review2 — REAL ORDINARY GATES BYTE/MTIME SNAPSHOT",
        "Команда: python bin/hs.py gates --profile auto (без внешнего PYTHONDONTWRITEBYTECODE)",
        f"nonignored files before/after: {len(before)}/{len(after)}",
        f"changed bytes or mtime: {len(changed)} {changed}",
        f"added: {len(added)} {added}",
        f"removed: {len(removed)} {removed}",
        f"__pycache__ before/after: {len(cache_before)}/{len(cache_after)}",
        f"cache_changed={cache_changed}",
        f"cache_added={cache_added}",
        f"cache_removed={cache_removed}",
        f"status_before={status_before!r}",
        f"status_after={status_after!r}",
        f"gate rc: {proc.returncode}",
        "--- gates stdout ---",
        proc.stdout,
        "--- gates stderr ---",
        proc.stderr,
        f"READONLY_SNAPSHOT: {'PASS' if passed else 'FAIL'}",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
