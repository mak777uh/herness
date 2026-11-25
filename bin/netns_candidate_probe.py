"""Candidate probe: --propagation unchanged без снятия user/PID namespace.

Это наблюдаемый эксперимент E-0084, не production bridge. Working требует rc=0,
USER_NS_UID=0 и PID_NS_PID=1. Среда проходит через net_child_env; итоговый report
полностью редактирует известные секреты. Privileged execution не используется.

    python bin/netns_candidate_probe.py --output runs/netns-candidate.json
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

from bin.netns_diagnostics import redact_value, run_probe, secret_values  # noqa: E402

CHILD = (
    "import os; "
    "print('USER_NS_UID=' + str(os.getuid())); "
    "print('PID_NS_PID=' + str(os.getpid())); "
    "assert os.getuid() == 0 and os.getpid() == 1"
)


def collect(*, environ: dict[str, str] | None = None, platform: str | None = None,
            timeout: float = 15, runner=subprocess.run, which=shutil.which) -> dict:
    source = dict(os.environ if environ is None else environ)
    secrets = secret_values(source)
    current_platform = sys.platform if platform is None else platform
    executable = which("unshare", path=source.get("PATH")) if current_platform.startswith("linux") else None
    report = {
        "schema": "netns-propagation-candidate-v1",
        "diagnostic_ok": True,
        "platform": current_platform,
        "uid": os.getuid() if current_platform != "win32" and hasattr(os, "getuid") else None,
        "euid": os.geteuid() if current_platform != "win32" and hasattr(os, "geteuid") else None,
        "probe": {
            "command": [], "state": "missing", "timeout_seconds": timeout,
            "returncode": None, "stdout": "", "stderr": "", "exception": "UnshareNotFound",
        },
        "user_namespace_ok": False,
        "pid_namespace_ok": False,
        "unshare_ok": False,
    }
    if executable:
        command = [
            executable, "-U", "-p", "-f", "--propagation", "unchanged",
            "--mount-proc", sys.executable, "-c", CHILD,
        ]
        result = run_probe(command, source, timeout, runner)
        result["command"] = command
        lines = set((result.get("stdout") or "").splitlines())
        rc = result.get("returncode")
        result["user_namespace_ok"] = rc == 0 and "USER_NS_UID=0" in lines
        result["pid_namespace_ok"] = rc == 0 and "PID_NS_PID=1" in lines
        result["unshare_ok"] = bool(result["user_namespace_ok"] and result["pid_namespace_ok"])
        result["state"] = "working" if result["unshare_ok"] else "broken"
        report["probe"] = {**report["probe"], **result}
        for key in ("user_namespace_ok", "pid_namespace_ok", "unshare_ok"):
            report[key] = report["probe"][key]
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
    return 3 if args.require_works and not report["unshare_ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
