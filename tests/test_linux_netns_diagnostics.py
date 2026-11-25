"""LINUX-NETNS-CI-R1: диагностический прибор не маскирует capability failure.

Запуск: python tests/test_linux_netns_diagnostics.py
Windows и POSIX: 10/10 без N/A; production bridge и namespace corpus неизменны.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import netns_diagnostics as diagnostics  # noqa: E402

CASES: list[tuple[str, callable]] = []
CANARY = "netns-secret-canary-7f43a9"


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


@case("missing-unshare-not-run")
def _():
    calls = []

    def runner(*args, **kwargs):
        calls.append(args)
        raise AssertionError("probe не должен запускаться")

    report = diagnostics.collect(
        environ={"PATH": ""}, platform="linux", runner=runner, which=lambda *a, **k: None,
    )
    assert not calls
    assert report["probe"]["state"] == "missing"
    assert report["probe"]["exception"] == "UnshareNotFound"
    assert report["probe"]["command"] == []
    assert not report["unshare_ok"]


@case("broken-unshare-keeps-rc-and-stderr")
def _():
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return completed(0, "util-linux 2.41") if "--version" in command else completed(1, "", "unshare: EPERM")

    report = diagnostics.collect(
        environ={"PATH": "/fake"}, platform="linux", runner=runner, which=lambda *a, **k: "/fake/unshare",
    )
    assert report["probe"]["state"] == "broken"
    assert report["probe"]["returncode"] == 1
    assert report["probe"]["stderr"] == "unshare: EPERM"
    assert report["probe"]["command"] == ["/fake/unshare", "-U", "-p", "-f", "--mount-proc", sys.executable, "-c", "pass"]
    assert calls[-1] == report["probe"]["command"]
    assert not report["unshare_ok"]


@case("working-unshare-exact-command-and-filtered-env")
def _():
    seen = []

    def runner(command, **kwargs):
        seen.append((command, kwargs["env"]))
        return completed(0, "util-linux 2.41") if "--version" in command else completed(0)

    report = diagnostics.collect(
        environ={"PATH": "/fake", "HS_BRIDGE_KEY": CANARY}, platform="linux",
        runner=runner, which=lambda *a, **k: "/fake/unshare",
    )
    assert report["probe"]["state"] == "working"
    assert report["unshare_ok"]
    assert seen[-1][0] == report["probe"]["command"]
    assert "HS_BRIDGE_KEY" not in seen[-1][1]
    assert CANARY not in diagnostics.render(report)


@case("timeout-is-broken-not-working")
def _():
    def runner(command, **kwargs):
        if "--version" in command:
            return completed(0, "util-linux")
        raise subprocess.TimeoutExpired(command, 15, output=b"partial", stderr=b"timeout-detail")

    report = diagnostics.collect(
        environ={"PATH": "/fake"}, platform="linux", timeout=0.01,
        runner=runner, which=lambda *a, **k: "/fake/unshare",
    )
    assert report["probe"]["state"] == "broken"
    assert report["probe"]["returncode"] is None
    assert report["probe"]["exception"] == "TimeoutExpired"
    assert report["probe"]["stdout"] == "partial"
    assert report["probe"]["stderr"] == "timeout-detail"
    assert not report["unshare_ok"]


@case("oserror-is-visible")
def _():
    def runner(command, **kwargs):
        if "--version" in command:
            return completed(0, "util-linux")
        raise PermissionError("denied")

    report = diagnostics.collect(
        environ={"PATH": "/fake"}, platform="linux", runner=runner, which=lambda *a, **k: "/fake/unshare",
    )
    assert report["probe"]["state"] == "broken"
    assert report["probe"]["exception"] == "PermissionError"
    assert report["probe"]["returncode"] is None


@case("secret-canary-redacted-from-all-output")
def _():
    def runner(command, **kwargs):
        return completed(0, CANARY, CANARY)

    report = diagnostics.collect(
        environ={"PATH": "/" + CANARY, "HS_BRIDGE_KEY": CANARY, "API_TOKEN": CANARY},
        platform="linux", runner=runner, which=lambda *a, **k: "/" + CANARY + "/unshare",
    )
    rendered = diagnostics.render(report)
    assert CANARY not in rendered
    assert rendered.count("[REDACTED]") >= 5
    assert report["probe"]["command"][0] == "/[REDACTED]/unshare"
    assert "HS_BRIDGE_KEY" not in rendered


@case("require-works-missing-returns-three")
def _():
    report = diagnostics.collect(environ={"PATH": ""}, platform="linux", which=lambda *a, **k: None)
    output = io.StringIO()
    with patch.object(diagnostics, "collect", return_value=report), redirect_stdout(output):
        assert diagnostics.main(["--require-works"]) == 3
    assert json.loads(output.getvalue())["probe"]["state"] == "missing"


@case("output-file-and-working-require-rc")
def _():
    report = diagnostics.collect(
        environ={"PATH": "/fake"}, platform="linux",
        runner=lambda command, **kwargs: completed(0, "util-linux"), which=lambda *a, **k: "/fake/unshare",
    )
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "netns.json"
        output = io.StringIO()
        with patch.object(diagnostics, "collect", return_value=report), redirect_stdout(output):
            assert diagnostics.main(["--output", str(target), "--require-works"]) == 0
        assert target.read_text(encoding="utf-8") == output.getvalue()
        assert json.loads(target.read_text(encoding="utf-8"))["unshare_ok"]


@case("capability-fields-and-non-linux")
def _():
    report = diagnostics.collect(environ={}, platform="win32", which=lambda *a, **k: "/should-not-use")
    assert report["platform"] == "win32"
    assert report["uid"] is None
    assert report["unshare"]["path"] is None
    assert set(report["sysctl"]) == set(diagnostics.SYSCTLS)
    assert "enabled" in report["apparmor"]
    assert "securityfs_mounted" in report["apparmor"]
    assert "profiles" in report["apparmor"]
    assert report["diagnostic_ok"] and not report["unshare_ok"]


@case("linux-manifest-and-frozen-production-hashes")
def _():
    manifest = json.loads((ROOT / "tests/test-manifest.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest["python"] if item["id"] == "test_linux_netns_diagnostics.py")
    assert entry["platforms"] == ["linux"]
    assert entry["minimum_checks"] == 10
    expected = {
        "bin/bridge.py": "e3762b0f989d902a211079012d02c4b9085a829b322f044e5db1dea6aed1865e",
        "tests/test_bridge_net_namespace.py": "c8efc7e10d5587a8e9402c076014464818aab5596664cbc53b6329f6b5caa958",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    workflow = (ROOT / ".github/workflows/gates.yml").read_text(encoding="utf-8")
    diagnostic = workflow.split("- name: Linux namespace capability diagnostic", 1)[1].split("- name: Selftest", 1)[0]
    assert "github.event.pull_request.head.repo.full_name == github.repository" in diagnostic


def main() -> int:
    assert len(CASES) == 10, len(CASES)
    passed = failed = 0
    for name, fn in CASES:
        try:
            fn()
            passed += 1
            print(f"[ok] {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[FAIL] {name} — {type(exc).__name__}: {exc}")
    print(f"\nnetns diagnostics: {passed}/{len(CASES)} ok; провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
