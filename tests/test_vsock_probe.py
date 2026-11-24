"""VSOCK-WIN-R1: прибор не обязан превращать device-start в GREEN."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import vsock_probe as probe  # noqa: E402


def observation(
    *,
    launched: bool = True,
    returncode: int | None = 1,
    timed_out: bool = False,
    stderr: str = "device not found",
) -> probe.LaunchObservation:
    return probe.LaunchObservation(
        probe.qemu_command("qemu.exe"), launched, returncode, timed_out, "", stderr
    )


def missing_qemu_is_na() -> None:
    result = probe.classify(observation(launched=False, returncode=None, stderr="not found"))
    assert result["verdict"] == "N/A"
    assert result["metrics"] is None
    assert result["fallback_calls"] == 0


def device_failure_is_red_without_metrics() -> None:
    result = probe.classify(observation())
    assert result["verdict"] == "RED"
    assert result["reason"] == "device-start-failed"
    assert result["metrics"] is None
    assert result["fallback_calls"] == 0


def startup_timeout_is_not_green() -> None:
    result = probe.classify(observation(returncode=None, timed_out=True, stderr=""))
    assert result["verdict"] == "RED"
    assert result["reason"] == "device-process-started-but-guest-measurements-not-executed"
    assert result["metrics"] is None


def clean_exit_is_not_green() -> None:
    result = probe.classify(observation(returncode=0, stderr=""))
    assert result["verdict"] == "RED"
    assert result["reason"] == "qemu-exited-before-guest-measurements"
    assert result["metrics"] is None


def launch_has_no_fallback_channel() -> None:
    command = probe.qemu_command("qemu.exe")
    assert not any(argument in probe.FALLBACK_FLAGS for argument in command)
    assert command[-2:] == ("-device", "vhost-vsock-pci,guest-cid=3")
    assert probe.classify(observation())["fallback_calls"] == 0


def main() -> int:
    checks = [
        ("missing-qemu-is-na", missing_qemu_is_na),
        ("device-failure-is-red-without-metrics", device_failure_is_red_without_metrics),
        ("startup-timeout-is-not-green", startup_timeout_is_not_green),
        ("clean-exit-is-not-green", clean_exit_is_not_green),
        ("launch-has-no-fallback-channel", launch_has_no_fallback_channel),
    ]
    failures = 0
    for label, check in checks:
        try:
            check()
        except Exception as exc:  # noqa: BLE001 — корпус печатает все провалы
            failures += 1
            print(f"[FAIL] {label}: {exc}")
        else:
            print(f"[ok] {label}")
    print(f"проверок: {len(checks)}; провалов: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
