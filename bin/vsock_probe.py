"""VSOCK-WIN-R1: фактический запуск Windows QEMU с vhost-vsock-pci.

Проба реализует только device-start решение зарегистрированного эксперимента.
Если QEMU не запущен, результат N/A. Если процесс запущен, но устройство не
поднялось, результат RED с command/rc/stderr и metrics=null. Если процесс
пережил startup timeout, это ещё не GREEN: guest→host→guest измерения не
выполнены, поэтому результат тоже RED с явной причиной.

TCP, stdio, guestfwd и любые другие fallback-каналы не создаются. На отказе
устройства stopping rule запрещает выдумывать latency/loss и переходить к TCP.
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin.store import write_text  # noqa: E402

DEFAULT_QEMU = r"C:\Program Files\qemu\qemu-system-x86_64.exe"
STARTUP_TIMEOUT_SECONDS = 5.0
FALLBACK_FLAGS = ("-netdev", "-nic", "-guestfwd", "-chardev")


@dataclass(frozen=True)
class LaunchObservation:
    command: tuple[str, ...]
    launched: bool
    returncode: int | None
    timed_out: bool
    stdout: str
    stderr: str


def qemu_command(qemu: str) -> tuple[str, ...]:
    """Один неизменяемый launch: paused VM, только CID 2↔3, без fallback."""
    return (
        qemu,
        "-machine", "q35",
        "-accel", "whpx",
        "-m", "256",
        "-smp", "1",
        "-nodefaults",
        "-display", "none",
        "-monitor", "none",
        "-serial", "none",
        "-S",
        "-device", "vhost-vsock-pci,guest-cid=3",
    )


def observe_launch(command: tuple[str, ...], timeout: float) -> LaunchObservation:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        return LaunchObservation(command, False, None, False, "", str(error))
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        if isinstance(stdout, str):
            stdout_text = stdout
        else:
            stdout_text = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, str):
            stderr_text = stderr
        else:
            stderr_text = stderr.decode("utf-8", errors="replace")
        return LaunchObservation(command, True, None, True, stdout_text, stderr_text)
    return LaunchObservation(
        command,
        True,
        completed.returncode,
        False,
        completed.stdout.decode("utf-8", errors="replace"),
        completed.stderr.decode("utf-8", errors="replace"),
    )


def classify(observation: LaunchObservation) -> dict[str, object]:
    """Ни один исход device-start пробы не может сам по себе стать GREEN."""
    fallback_calls = sum(argument in FALLBACK_FLAGS for argument in observation.command)
    if not observation.launched:
        verdict, reason = "N/A", "qemu-not-launched"
    elif observation.timed_out:
        verdict, reason = "RED", "device-process-started-but-guest-measurements-not-executed"
    elif observation.returncode != 0:
        verdict, reason = "RED", "device-start-failed"
    else:
        verdict, reason = "RED", "qemu-exited-before-guest-measurements"
    return {
        "verdict": verdict,
        "reason": reason,
        "fallback_calls": fallback_calls,
        "metrics": None,
    }


def command_text(command: tuple[str, ...]) -> str:
    return subprocess.list2cmdline(list(command))


def render_report(
    *,
    qemu: str,
    version_rc: int | None,
    version_output: str,
    observation: LaunchObservation,
    result: dict[str, object],
    timeout: float,
) -> str:
    lines = [
        "VSOCK-WIN-R1 — device-start probe",
        "Дата: 2026-11-24",
        f"Хост: {platform.system()} {platform.release()} build {platform.version()}",
        f"QEMU: {qemu}",
        f"QEMU --version rc: {version_rc if version_rc is not None else 'N/A'}",
        "QEMU --version output:",
        version_output.rstrip() or "(пусто)",
        "",
        f"Launch command: {command_text(observation.command)}",
        f"Launch performed: {'yes' if observation.launched else 'no'}",
        f"Startup timeout seconds: {timeout:g}",
        f"Launch rc: {observation.returncode if observation.returncode is not None else 'N/A'}",
        f"Timed out: {'yes' if observation.timed_out else 'no'}",
        "Launch stdout:",
        observation.stdout.rstrip() or "(пусто)",
        "Launch stderr:",
        observation.stderr.rstrip() or "(пусто)",
        "",
        f"VERDICT: {result['verdict']}",
        f"REASON: {result['reason']}",
        f"fallback_calls: {result['fallback_calls']}",
        "metrics: null",
        "echo_success: N/A",
        "p99_latency_ms: N/A",
        "lost_frames: N/A",
        "reconnect_ok: N/A",
        "reachable_non_host_cids: N/A",
        "",
        "Граница: это фактический Windows/QEMU device-start запуск, не Linux/WSL",
        "и не Hyper-V AF_HYPERV/VMBus. RED не запрещает другие транспорты и не",
        "разрешает fallback. Достаточность RED для HTTP-subset остаётся owner decision.",
    ]
    return "\n".join(lines) + "\n"


def qemu_version(qemu: str) -> tuple[int | None, str]:
    try:
        completed = subprocess.run(
            [qemu, "--version"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, str(error)
    output = completed.stdout.decode("utf-8", errors="replace")
    errors = completed.stderr.decode("utf-8", errors="replace")
    return completed.returncode, output + errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qemu", default=os.environ.get("HS_QEMU", DEFAULT_QEMU))
    parser.add_argument("--timeout", type=float, default=STARTUP_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout должен быть больше нуля")

    version_rc, version_output = qemu_version(args.qemu)
    observation = observe_launch(qemu_command(args.qemu), args.timeout)
    result = classify(observation)
    report = render_report(
        qemu=args.qemu,
        version_rc=version_rc,
        version_output=version_output,
        observation=observation,
        result=result,
        timeout=args.timeout,
    )
    write_text(args.output, report)
    print(report, end="")
    return 2 if result["verdict"] == "N/A" else 0


if __name__ == "__main__":
    sys.exit(main())
