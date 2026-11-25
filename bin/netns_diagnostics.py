"""Собрать capability-диагностику Linux namespace без запуска /v1/net.

Прибор не доказывает изоляцию и не меняет bridge. Он повторяет ровно команду
Bridge.unshare_works с тем же allowlist окружения и сохраняет результат, включая
отказ. Секреты из родительского окружения не наследуются и дополнительно
редактируются в диагностических строках.

    python bin/netns_diagnostics.py --output runs/netns-diagnostics.json
    python bin/netns_diagnostics.py --require-works  # rc=3, если probe не рабочий
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin.bridge import net_child_env  # noqa: E402

SYSCTLS = (
    "kernel.apparmor_restrict_unprivileged_userns",
    "kernel.apparmor_restrict_unconfined",
)
SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def secret_values(environ: dict[str, str]) -> list[str]:
    return [
        value for key, value in environ.items()
        if len(value) >= 4 and any(marker in key.upper() for marker in SECRET_MARKERS)
    ]


def redact(text: str, secrets: list[str]) -> str:
    for value in sorted(set(secrets), key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    return text


def redact_value(value, secrets: list[str]):
    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, list):
        return [redact_value(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: redact_value(item, secrets) for key, item in value.items()}
    return value


def run_probe(command: list[str], environ: dict[str, str], timeout: float = 15,
              runner=subprocess.run) -> dict:
    try:
        result = runner(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, env=net_child_env(environ),
            close_fds=True,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "exception": None,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "stdout": (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            "stderr": (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
            "exception": "TimeoutExpired",
        }
    except OSError as exc:
        return {"returncode": None, "stdout": "", "stderr": "", "exception": type(exc).__name__}


def collect(*, environ: dict[str, str] | None = None, platform: str | None = None,
            timeout: float = 15, runner=subprocess.run, which=shutil.which) -> dict:
    source = dict(os.environ if environ is None else environ)
    secrets = secret_values(source)
    current_platform = sys.platform if platform is None else platform
    executable = which("unshare", path=source.get("PATH")) if current_platform.startswith("linux") else None
    report = {
        "schema": "netns-diagnostics-v1",
        "diagnostic_ok": True,
        "platform": current_platform,
        "python": sys.version.split()[0],
        "uid": os.getuid() if current_platform != "win32" and hasattr(os, "getuid") else None,
        "euid": os.geteuid() if current_platform != "win32" and hasattr(os, "geteuid") else None,
        "unshare": {"path": executable, "version": None, "version_returncode": None},
        "apparmor": {
            "enabled": read_text(Path("/sys/module/apparmor/parameters/enabled")),
            "securityfs_mounted": Path("/sys/kernel/security/apparmor").is_dir(),
            "profiles": read_text(Path("/sys/kernel/security/apparmor/profiles")),
        },
        "sysctl": {name: read_text(Path("/proc/sys") / name.replace(".", "/")) for name in SYSCTLS},
        "probe": {
            "command": [], "state": "missing", "timeout_seconds": timeout,
            "returncode": None, "stdout": "", "stderr": "", "exception": "UnshareNotFound",
        },
    }
    if executable:
        version = run_probe([executable, "--version"], source, timeout, runner)
        report["unshare"]["version"] = redact(version["stdout"] or version["stderr"], secrets)
        report["unshare"]["version_returncode"] = version["returncode"]
        command = [executable, "-U", "-p", "-f", "--mount-proc", sys.executable, "-c", "pass"]
        result = run_probe(command, source, timeout, runner)
        for key in ("stdout", "stderr"):
            result[key] = redact(result[key], secrets)
        result["command"] = command
        result["state"] = "working" if result["returncode"] == 0 else "broken"
        report["probe"] = {**report["probe"], **result}
    report["unshare_ok"] = report["probe"]["state"] == "working"
    return redact_value(report, secrets)


def render(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-works", action="store_true")
    args = parser.parse_args(argv)
    report = collect()
    text = render(report)
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")
    if args.require_works and not report["unshare_ok"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
