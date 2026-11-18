"""proc_isolation — остаток /proc: same-uid ребёнок читает env родителя, namespace его скрывает.

Зачем. BRIDGE-KEY-ISOLATION-R1 закрыл наследование os.environ в /v1/net, но на Linux
остаётся /proc/<ppid>/environ: дочерний процесс того же uid читает стартовое окружение
моста, включая HS_BRIDGE_KEY. Allowlist окружения этого не закрывает — он влияет на
то, что ребёнок получает при старте, а не на то, что он может прочитать.

Здесь измеряются два плеча, без изменения bin/bridge.py:
  A — без изоляции: ребёнок с allowlist-окружением видит канарейку в /proc родителя;
  B — unshare -U -p -f --mount-proc: родитель не виден, поиск по всему /proc даёт 0.

Это прототип и измерение, а не защита Windows и не K9-доказательство. Запуск:

    python bin/proc_isolation.py            # Windows: делегирует в WSL Ubuntu
    python bin/proc_isolation.py --run-arms # внутреннее: два плеча
    python bin/proc_isolation.py --probe ...# внутреннее: ребёнок-измеритель
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_NAME = "HS_BRIDGE_KEY"
CHILD_ENV_ALLOW = frozenset({
    "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
    "LANG", "LC_ALL", "PYTHONIOENCODING", "PYTHONUTF8",
})


def child_env() -> dict[str, str]:
    """То же, что NET_CHILD_ENV в мосте: канарейка в это окружение не входит."""
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() in CHILD_ENV_ALLOW
    }


def probe(parent_pid: int, needle: str) -> int:
    """Ребёнок: ищет HS_BRIDGE_KEY=<needle> в /proc родителя и во всём /proc."""
    marker = f"{ENV_NAME}={needle}".encode("utf-8")
    direct = False
    try:
        direct = marker in Path(f"/proc/{parent_pid}/environ").read_bytes()
    except OSError:
        direct = False
    anywhere = False
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if marker in (entry / "environ").read_bytes():
                anywhere = True
                break
        except OSError:
            continue
    print("PROBE_RAN=1")
    print(f"FOUND={int(direct)}")
    print(f"FOUND_ANY={int(anywhere)}")
    return 0


def run_arm(use_unshare: bool, parent_pid: int, needle: str) -> tuple[subprocess.CompletedProcess | None, str]:
    script = str(Path(__file__).resolve())
    argv = [
        sys.executable, script, "--probe",
        "--parent-pid", str(parent_pid), "--needle", needle,
    ]
    if use_unshare:
        unshare = shutil.which("unshare")
        if not unshare:
            return None, "unshare не найден"
        argv = [unshare, "-U", "-p", "-f", "--mount-proc", *argv]
    result = subprocess.run(
        argv,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=child_env(), timeout=60,
    )
    return result, ""


def numbers(text: str) -> dict[str, int | None]:
    found: dict[str, int | None] = {}
    for name in ("PROBE_RAN", "FOUND", "FOUND_ANY"):
        match = re.search(rf"^{name}=(\d+)$", text, re.MULTILINE)
        found[name] = int(match.group(1)) if match else None
    return found


def run_arms() -> int:
    """Внутреннее плечо: родитель уже запущен с синтетической канарейкой."""
    needle = os.environ.get(ENV_NAME, "")
    if not needle:
        print("FAIL: в стартовом окружении родителя нет синтетической канарейки")
        return 1
    parent_pid = os.getpid()

    arm_a, error_a = run_arm(False, parent_pid, needle)
    arm_b, error_b = run_arm(True, parent_pid, needle)
    text_a = ((arm_a.stdout or "") + (arm_a.stderr or "")) if arm_a else ""
    text_b = ((arm_b.stdout or "") + (arm_b.stderr or "")) if arm_b else ""
    num_a = numbers(text_a) if arm_a else {}
    num_b = numbers(text_b) if arm_b else {}

    print("плечо A (без изоляции):")
    print(text_a.strip() or f"нет вывода ({error_a})")
    print("плечо B (unshare -U -p -f --mount-proc):")
    print(text_b.strip() or f"нет вывода ({error_b})")

    def is_value(values: dict[str, int | None], name: str, expected: int) -> bool:
        return values.get(name) == expected

    checks = [
        (arm_a is not None and is_value(num_a, "PROBE_RAN", 1),
         "A: probe выполнился"),
        (is_value(num_a, "FOUND", 1),
         "A: канарейка видна напрямую в /proc родителя (остаток воспроизведён)"),
        (is_value(num_a, "FOUND_ANY", 1),
         "A: канарейка видна при поиске по всему /proc"),
        (arm_b is not None and is_value(num_b, "PROBE_RAN", 1),
         "B: probe выполнился в namespace"),
        (is_value(num_b, "FOUND", 0),
         "B: родитель не виден напрямую"),
        (is_value(num_b, "FOUND_ANY", 0),
         "B: канарейка не видна при поиске по всему /proc"),
    ]
    failed = 0
    for ok, message in checks:
        print(f"[{'ok' if ok else 'FAIL'}] {message}")
        failed += 0 if ok else 1
    print(f"провалов: {failed}")
    if failed:
        print("ВЕРДИКТ: FAIL — остаток /proc не воспроизведён или namespace не скрыл родителя")
        return 1
    print("ВЕРДИКТ: PASS — same-uid /proc видит env; PID-namespace скрывает родителя")
    return 0


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = str(resolved).replace("\\", "/")[len(resolved.drive):]
    return f"/mnt/{drive}{rest}"


def delegate_wsl() -> int:
    if shutil.which("wsl") is None:
        print("N/A: WSL не найден, срез не выполнен")
        return 2
    script = wsl_path(ROOT / "bin" / "proc_isolation.py")
    result = subprocess.run(
        ["wsl", "-d", "Ubuntu", "--exec", "python3", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180,
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="остаток /proc и PID-namespace")
    parser.add_argument("--probe", action="store_true", help="внутреннее: ребёнок")
    parser.add_argument("--run-arms", action="store_true", help="внутреннее: два плеча")
    parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--needle", default="")
    args = parser.parse_args(argv)

    if args.probe:
        return probe(args.parent_pid, args.needle)
    if args.run_arms:
        return run_arms()
    if not sys.platform.startswith("linux"):
        return delegate_wsl()

    canary = "hs-proc-" + secrets.token_hex(12)
    env = {**os.environ, ENV_NAME: canary}
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--run-arms"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=180,
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
