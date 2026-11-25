"""Focused controls E-0084: candidate не объявляет isolation без обоих markers."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin import netns_candidate_probe as candidate  # noqa: E402


class Runner:
    def __init__(self, returncode=0, stdout="", stderr="", exception=None):
        self.returncode, self.stdout, self.stderr, self.exception = returncode, stdout, stderr, exception
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.exception:
            raise self.exception
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)


def exact_command_and_filtered_env():
    runner = Runner(stdout="USER_NS_UID=0\nPID_NS_PID=1\n")
    env = {"PATH": "/usr/bin", "TMP": "/tmp", "HOME": "/home/test", "NET_ALLOW": "1", "API_KEY": "hidden"}
    report = candidate.collect(platform="linux", environ=env, timeout=7, runner=runner,
                               which=lambda name, path: "/usr/bin/unshare")
    command = ["/usr/bin/unshare", "-U", "-p", "-f", "--propagation", "unchanged",
               "--mount-proc", sys.executable, "-c", candidate.CHILD]
    assert runner.calls[0][0] == command
    assert runner.calls[0][1]["env"] == {"PATH": "/usr/bin", "TMP": "/tmp"}
    assert runner.calls[0][1]["timeout"] == 7 and runner.calls[0][1]["close_fds"] is True
    assert report["unshare_ok"] and report["probe"]["state"] == "working"


def rc_zero_without_both_markers_is_broken():
    for stdout in ("", "USER_NS_UID=0\n", "PID_NS_PID=1\n", "USER_NS_UID=1\nPID_NS_PID=1\n"):
        runner = Runner(stdout=stdout)
        report = candidate.collect(platform="linux", environ={"PATH": "/usr/bin"}, runner=runner,
                                   which=lambda name, path: "/usr/bin/unshare")
        assert not report["unshare_ok"] and report["probe"]["state"] == "broken"


def nonzero_with_markers_is_broken():
    runner = Runner(returncode=1, stdout="USER_NS_UID=0\nPID_NS_PID=1\n")
    report = candidate.collect(platform="linux", environ={"PATH": "/usr/bin"}, runner=runner,
                               which=lambda name, path: "/usr/bin/unshare")
    assert not report["unshare_ok"] and not report["user_namespace_ok"] and not report["pid_namespace_ok"]


def missing_unshare_does_not_run_child():
    runner = Runner()
    report = candidate.collect(platform="linux", environ={}, runner=runner, which=lambda name, path: None)
    assert not runner.calls and report["probe"]["state"] == "missing"
    assert report["probe"]["exception"] == "UnshareNotFound" and not report["unshare_ok"]


def oserror_is_visible():
    runner = Runner(exception=FileNotFoundError("secret-free"))
    report = candidate.collect(platform="linux", environ={"PATH": "/usr/bin"}, runner=runner,
                               which=lambda name, path: "/usr/bin/unshare")
    assert report["probe"]["exception"] == "FileNotFoundError" and not report["unshare_ok"]


def timeout_is_broken_not_working():
    runner = Runner(exception=subprocess.TimeoutExpired("unshare", 3))
    report = candidate.collect(platform="linux", environ={"PATH": "/usr/bin"}, runner=runner,
                               which=lambda name, path: "/usr/bin/unshare")
    assert report["probe"]["exception"] == "TimeoutExpired" and not report["unshare_ok"]


def canary_is_redacted_from_every_field():
    canary = "CANDIDATE-CANARY-7f4b"
    runner = Runner(stdout=f"USER_NS_UID=0\n{canary}\n", stderr=canary)
    report = candidate.collect(platform="linux", environ={"PATH": f"/secret/{canary}", "API_KEY": canary}, runner=runner,
                               which=lambda name, path: f"/secret/{canary}/unshare")
    text = candidate.render(report)
    assert canary not in text and "[REDACTED]" in text


def cli_writes_output_and_require_works_exit_codes():
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "candidate.json"
        with patch.object(candidate, "collect", return_value={"unshare_ok": False}):
            assert candidate.main(["--output", str(output), "--require-works"]) == 3
        assert json.loads(output.read_text(encoding="utf-8")) == {"unshare_ok": False}
        with patch.object(candidate, "collect", return_value={"unshare_ok": True}):
            assert candidate.main(["--require-works"]) == 0
    assert candidate.collect(platform="win32", environ={})["probe"]["state"] == "missing"


def manifest_workflow_and_frozen_production():
    manifest = json.loads((ROOT / "tests/test-manifest.json").read_text(encoding="utf-8"))
    entries = manifest.get("suites", []) if isinstance(manifest, dict) else manifest
    if not entries and isinstance(manifest, dict):
        entries = manifest.get("python", [])
    entry = next(item for item in entries if item["id"] == "test_linux_netns_propagation.py")
    assert entry["platforms"] == ["linux"] and entry["minimum_checks"] == 9
    workflow = (ROOT / ".github/workflows/gates.yml").read_text(encoding="utf-8")
    trust = "if: github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository"
    step = workflow.split("- name: Linux namespace propagation candidate", 1)[1].split("- name:", 1)[0]
    assert trust in step and "bin/netns_candidate_probe.py --output" in step
    frozen = {
        "bin/bridge.py": "e3762b0f989d902a211079012d02c4b9085a829b322f044e5db1dea6aed1865e",
        "tests/test_bridge_net_namespace.py": "c8efc7e10d5587a8e9402c076014464818aab5596664cbc53b6329f6b5caa958",
    }
    for relative, expected in frozen.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


def main():
    checks = [
        exact_command_and_filtered_env,
        rc_zero_without_both_markers_is_broken,
        nonzero_with_markers_is_broken,
        missing_unshare_does_not_run_child,
        oserror_is_visible,
        timeout_is_broken_not_working,
        canary_is_redacted_from_every_field,
        cli_writes_output_and_require_works_exit_codes,
        manifest_workflow_and_frozen_production,
    ]
    failures = 0
    for check in checks:
        try:
            check()
            print(f"[ok] {check.__name__}")
        except Exception as exc:
            failures += 1
            print(f"[FAIL] {check.__name__} — {type(exc).__name__}: {exc}")
    print(f"netns propagation candidate: {len(checks) - failures}/{len(checks)} ok; провалов: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
