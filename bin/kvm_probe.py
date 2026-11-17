"""KVM_RUN: доказать, что комната действительно исполняется аппаратно.

Зачем отдельный прибор. Наличие `/dev/kvm` и флаг `-accel kvm` — ещё не доказательство:
QEMU мог уйти на TCG, а `query-kvm` мог быть прочитан не у той машины. Здесь измеряются
три независимых факта одной пробы:

1. QMP `query-kvm` отвечает `present=true, enabled=true`;
2. tracepoint `kvm:kvm_entry` в изолированном trace-инстансе даёт счётчик > 0;
3. отрицательный контроль под `setpriv` (uid/gid 65534, без доступа к `/dev/kvm`)
   обязан завершиться отказом, а не загрузить гостя через TCG.

Плюс гость печатает маркер `KVM-PROBE-GUEST-OK`; отсутствие маркера — провал даже при
зелёном QMP. Никакой fallback на WHPX/TCG не допускается.

    python bin/kvm_probe.py --verify          # Windows: запускает себя в WSL от root
    python bin/kvm_probe.py --verify --keep   # оставить артефакты в /tmp

Evidence: research/kvm/KVM-RUN-2026-11-17.txt. Провал пишется как FAIL, а не замалчивается.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "core-rs" / "boot" / "vmlinuz-lts"
KERNEL_URL = "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/netboot/vmlinuz-lts"
EVIDENCE = ROOT / "research" / "kvm" / "KVM-RUN-2026-11-17.txt"
TRACE_ROOT = Path("/sys/kernel/debug/tracing")
QEMU = "qemu-system-x86_64"
MARKER = "KVM-PROBE-GUEST-OK"
EXIT_VALUE = 0x10  # QEMU isa-debug-exit: код процесса = (value << 1) | 1


def wsl_path(path: Path) -> str:
    text = path.resolve().as_posix()
    if re.match(r"^[A-Za-z]:/", text):
        return "/mnt/" + text[0].lower() + text[2:]
    return text


def cpio_newc(entries: list[tuple[str, bytes, int]]) -> bytes:
    out = bytearray()
    inode = 1
    for name, data, mode in entries:
        name_bytes = name.encode() + b"\x00"
        header = b"070701" + b"".join(
            f"{value:08X}".encode()
            for value in (
                inode, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name_bytes), 0
            )
        )
        out += header + name_bytes
        out += b"\x00" * ((4 - (len(header) + len(name_bytes)) % 4) % 4)
        out += data
        out += b"\x00" * ((4 - len(data) % 4) % 4)
        inode += 1
    trailer = b"TRAILER!!!\x00"
    header = b"070701" + b"".join(
        f"{value:08X}".encode() for value in (0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(trailer), 0)
    )
    out += header + trailer
    out += b"\x00" * ((4 - (len(header) + len(trailer)) % 4) % 4)
    return bytes(out)


INIT_C = r"""
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/io.h>
#include <sys/reboot.h>
#include <unistd.h>

int main(void) {
    const char marker[] = "KVM-PROBE-GUEST-OK\n";
    write(1, marker, sizeof(marker) - 1);
    fsync(1);
    /* Дать QMP и trace успеть увидеть живую машину до выхода. */
    sleep(2);
    if (iopl(3) != 0) {
        return 2;
    }
    outl(0x10, 0xf4);  /* isa-debug-exit: rc = (0x10 << 1) | 1 = 33 */
    return 3;
}
"""


def qmp_query_kvm(sock_path: Path, timeout: float = 10.0) -> tuple[dict | None, str]:
    """Подключиться к QMP и спросить query-kvm. Возвращает (ответ, текст ошибки)."""
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        if not sock_path.exists():
            time.sleep(0.05)
            continue
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.settimeout(2.0)
                conn.connect(str(sock_path))
                stream = conn.makefile("rwb")
                greeting = stream.readline()
                if not greeting:
                    raise OSError("QMP закрыл соединение до приветствия")
                stream.write(json.dumps({"execute": "qmp_capabilities"}).encode() + b"\n")
                stream.flush()
                stream.readline()
                stream.write(json.dumps({"execute": "query-kvm"}).encode() + b"\n")
                stream.flush()
                line = stream.readline()
                if not line:
                    raise OSError("QMP не ответил на query-kvm")
                return json.loads(line.decode("utf-8", "replace")), ""
        except (OSError, ValueError) as error:
            last_error = str(error)
            time.sleep(0.05)
    return None, last_error


def start_trace() -> tuple[Path | None, str]:
    """Изолированный trace-инстанс: не трогаем глобальный буфер чужой работы."""
    if not TRACE_ROOT.exists():
        return None, f"нет tracefs: {TRACE_ROOT}"
    instance = TRACE_ROOT / "instances" / f"herness-kvm-{os.getpid()}"
    try:
        instance.mkdir()
        (instance / "trace").write_text("", encoding="utf-8")
        (instance / "events" / "kvm" / "kvm_entry" / "enable").write_text("1\n", encoding="utf-8")
        return instance, ""
    except OSError as error:
        stop_trace(instance)
        return None, f"trace-инстанс не создан: {error}"


def stop_trace(instance: Path | None) -> None:
    if instance is None:
        return
    try:
        (instance / "events" / "kvm" / "kvm_entry" / "enable").write_text("0\n", encoding="utf-8")
    except OSError:
        pass
    try:
        instance.rmdir()
    except OSError:
        pass


def trace_count(instance: Path | None) -> int:
    if instance is None:
        return 0
    try:
        text = (instance / "trace").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    return sum(1 for line in text.splitlines() if "kvm_entry:" in line)


def build_init(work: Path) -> tuple[Path, str]:
    source = work / "init.c"
    binary = work / "init"
    source.write_text(INIT_C, encoding="utf-8")
    compile_result = subprocess.run(
        ["gcc", "-static", "-O2", "-o", str(binary), str(source)],
        capture_output=True, text=True,
    )
    if compile_result.returncode != 0:
        return binary, f"gcc: {compile_result.returncode}: {compile_result.stderr.strip()}"
    return binary, ""


def build_initramfs(work: Path, init_binary: Path) -> Path:
    archive = cpio_newc([
        ("init", init_binary.read_bytes(), 0o100755),
        ("proc", b"", 0o040755),
        ("sys", b"", 0o040755),
        ("dev", b"", 0o040755),
    ])
    target = work / "initramfs.cpio.gz"
    target.write_bytes(gzip.compress(archive, 9))
    return target


def qemu_command(kernel: Path, initrd: Path, qmp: Path | None) -> list[str]:
    command = [
        QEMU,
        "-M", "microvm",
        "-accel", "kvm",
        "-m", "256",
        "-smp", "1",
        "-kernel", str(kernel),
        "-initrd", str(initrd),
        "-append", "console=ttyS0 rdinit=/init panic=-1",
        "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
        "-nic", "none",
        "-no-user-config",
        "-nographic",
        "-no-reboot",
    ]
    if qmp is not None:
        command += ["-qmp", f"unix:{qmp},server=on,wait=off"]
    return command


def run_positive(work: Path, kernel: Path, initrd: Path) -> dict:
    qmp = work / "qmp.sock"
    instance, trace_error = start_trace()
    command = qemu_command(kernel, initrd, qmp)
    started = time.time()
    process = None
    stdout = b""
    stderr = b""
    qmp_answer: dict | None = None
    qmp_error = ""
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        qmp_answer, qmp_error = qmp_query_kvm(qmp)
        try:
            stdout, stderr = process.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
    finally:
        entries = trace_count(instance)
        stop_trace(instance)
    return {
        "command": command,
        "rc": process.returncode if process is not None else -1,
        "seconds": round(time.time() - started, 3),
        "stdout": stdout.decode("utf-8", "replace"),
        "stderr": stderr.decode("utf-8", "replace"),
        "qmp": qmp_answer,
        "qmp_error": qmp_error,
        "trace_error": trace_error,
        "kvm_entry": entries,
        "marker": MARKER in stdout.decode("utf-8", "replace"),
    }


def run_negative(work: Path, kernel: Path, initrd: Path) -> dict:
    command = [
        "setpriv",
        "--reuid=65534", "--regid=65534", "--clear-groups",
        *qemu_command(kernel, initrd, None),
    ]
    try:
        process = subprocess.run(
            command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30
        )
        rc = process.returncode
        combined = (process.stdout or "") + (process.stderr or "")
    except subprocess.TimeoutExpired as error:
        rc = 124
        combined = f"timeout: {error}"
    return {
        "command": command,
        "rc": rc,
        "output": combined,
        "marker": MARKER in combined,
    }


def verdict(positive: dict, negative: dict) -> tuple[bool, list[str]]:
    problems: list[str] = []
    qmp = positive["qmp"] or {}
    answer = qmp.get("return") if isinstance(qmp, dict) else None
    if not isinstance(answer, dict) or answer.get("present") is not True or answer.get("enabled") is not True:
        problems.append(f"QMP query-kvm: {positive['qmp']!r} ({positive['qmp_error'] or 'нет ответа'})")
    if positive["trace_error"]:
        problems.append(positive["trace_error"])
    if positive["kvm_entry"] <= 0:
        problems.append("kvm:kvm_entry не сработал: KVM_RUN не наблюдался")
    if positive["rc"] != (EXIT_VALUE << 1) | 1:
        problems.append(f"гость завершился rc={positive['rc']}, ждали {(EXIT_VALUE << 1) | 1}")
    if not positive["marker"]:
        problems.append("маркер гостя не найден")
    if negative["rc"] == 0:
        problems.append("отрицательный контроль завершился rc=0: KVM не отказал")
    if negative["rc"] == 124:
        problems.append("отрицательный контроль не завершился: это не отказ")
    if negative["marker"]:
        problems.append("отрицательный контроль загрузил гостя: это TCG-подмена, а не отказ")
    if negative["rc"] not in (0, 124) and "kvm" not in negative["output"].lower():
        # Отказ может быть и про права на файл; тогда он не доказывает именно KVM.
        problems.append("отрицательный контроль отказал не по KVM")
    return not problems, problems


def describe(command: list[str]) -> str:
    return " ".join(command)


def evidence_text(positive: dict, negative: dict, problems: list[str], env: dict) -> str:
    ok = not problems
    lines = [
        "# KVM-RUN-2026-11-17 — измеренная комната",
        "",
        "Команда: `python bin/kvm_probe.py --verify`",
        f"Вердикт: {'PASS' if ok else 'FAIL'}",
        "",
        "## Среда",
        "",
        *[f"- {key}: {value}" for key, value in env.items()],
        "",
        "## Положительная проба",
        "",
        "```text",
        describe(positive["command"]),
        "```",
        f"rc: {positive['rc']} (ожидается {(EXIT_VALUE << 1) | 1})",
        f"время: {positive['seconds']} с",
        f"QMP query-kvm: {json.dumps(positive['qmp'], ensure_ascii=False)}",
        f"kvm:kvm_entry: {positive['kvm_entry']}",
        f"маркер гостя: {'найден' if positive['marker'] else 'НЕТ'}",
        "",
        "stdout (хвост):",
        "```text",
        "\n".join(positive["stdout"].splitlines()[-20:]),
        "```",
        "",
        "## Отрицательный контроль",
        "",
        "```text",
        describe(negative["command"]),
        "```",
        f"rc: {negative['rc']}",
        f"маркер гостя: {'найден (плохо)' if negative['marker'] else 'не найден'}",
        "```text",
        "\n".join(negative["output"].splitlines()[-15:]),
        "```",
        "",
        "## Что это доказывает",
        "",
        "- На этой машине и этом QEMU гость исполнялся через KVM: QMP говорит enabled,",
        "  `kvm:kvm_entry` дал счётчик > 0, гость дошёл до init.",
        "- Без доступа к `/dev/kvm` тот же запуск отказал; TCG не подставлен.",
        "",
        "## Что это НЕ доказывает",
        "",
        "- Что комната безопасна: измерен ускоритель, а не граница. Сеть/диск/host mounts",
        "  отсутствуют в команде, но это проверка конфигурации, а не доказательство.",
        "- Что `head` или любой инструмент ведёт себя по политике: это HEAD-SLICE-R1.",
        "- Что `K9_proven` выдан: он не выдаётся.",
        "",
    ]
    if problems:
        lines += ["## Провалы", "", *[f"- {problem}" for problem in problems], ""]
    return "\n".join(lines)


def environment() -> dict:
    def read(path: str, default: str = "") -> str:
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return default

    version = subprocess.run([QEMU, "--version"], capture_output=True, text=True)
    accel = subprocess.run([QEMU, "-accel", "help"], capture_output=True, text=True)
    machine = subprocess.run([QEMU, "-M", "help"], capture_output=True, text=True)
    microvm = [line.strip() for line in machine.stdout.splitlines() if line.startswith("microvm")]
    model = next(
        (
            line.split(":", 1)[1].strip()
            for line in read("/proc/cpuinfo").splitlines()
            if line.startswith("model name")
        ),
        "?",
    )
    kernel = KERNEL
    kernel_info = "нет файла"
    if kernel.exists():
        digest = hashlib.sha256(kernel.read_bytes()).hexdigest()
        kernel_info = f"{kernel} ({kernel.stat().st_size} байт, sha256:{digest})"
    return {
        "host": platform.platform(),
        "kernel": platform.release(),
        "guest_kernel": kernel_info,
        "guest_kernel_source": KERNEL_URL,
        "qemu": (version.stdout.splitlines() or ["?"])[0],
        "accel": " ".join(
            line.strip() for line in accel.stdout.splitlines()
            if line.strip() and not line.endswith(":")
        ) or accel.stdout.strip(),
        "machine": microvm[0] if microvm else "microvm не найден",
        "kvm_device": (
            "/dev/kvm доступен"
            if os.access("/dev/kvm", os.R_OK | os.W_OK)
            else "/dev/kvm НЕ доступен"
        ),
        "cpu": model,
    }


def empty_positive() -> dict:
    return {
        "command": [], "rc": -1, "seconds": 0, "stdout": "", "stderr": "",
        "qmp": None, "qmp_error": "", "trace_error": "", "kvm_entry": 0, "marker": False,
    }


def empty_negative() -> dict:
    return {"command": [], "rc": -1, "output": "", "marker": False}


def probe(kernel: Path, keep: bool) -> int:
    work = Path(tempfile.mkdtemp(prefix="herness-kvm-"))
    os.chmod(work, 0o755)
    problems: list[str] = []
    positive = empty_positive()
    negative = empty_negative()
    try:
        if not kernel.exists():
            problems.append(f"нет ядра: {kernel}")
        if shutil.which("gcc") is None:
            problems.append("нет gcc для статического init")
        if shutil.which(QEMU) is None:
            problems.append(f"нет {QEMU}")
        if not problems:
            init_binary, error = build_init(work)
            if error:
                problems.append(error)
            else:
                initrd = build_initramfs(work, init_binary)
                positive = run_positive(work, kernel, initrd)
                negative = run_negative(work, kernel, initrd)
                ok, found = verdict(positive, negative)
                problems.extend(found)
    except Exception as error:  # noqa: BLE001 — провал прибора должен попасть в evidence
        problems.append(f"{type(error).__name__}: {error}")
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(
        evidence_text(positive, negative, problems, environment()),
        encoding="utf-8",
    )
    print(evidence_text(positive, negative, problems, environment()))
    print(f"evidence: {EVIDENCE}")
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"артефакты: {work}")
    return 0 if not problems else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="KVM_RUN: QMP + tracepoint + отрицательный контроль")
    parser.add_argument("--verify", action="store_true", help="выполнить пробу")
    parser.add_argument("--keep", action="store_true", help="оставить артефакты в /tmp")
    parser.add_argument("--kernel", type=Path, default=KERNEL)
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        script = wsl_path(Path(__file__).resolve())
        command = ["wsl", "-d", "Ubuntu", "-u", "root", "--exec", "python3", script, "--verify"]
        if args.keep:
            command.append("--keep")
        if args.kernel != KERNEL:
            command += ["--kernel", wsl_path(args.kernel)]
        result = subprocess.run(command)
        return result.returncode

    if not args.verify:
        parser.print_help()
        return 2
    return probe(args.kernel, args.keep)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
