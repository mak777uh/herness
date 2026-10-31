"""Собрать initramfs (cpio newc) на Windows: ядро + наш ELF + методика.

Нужен, чтобы проверить полный путь без WSL: сборка на Windows, упаковка на Windows, загрузка в QEMU.
"""

from __future__ import annotations

import os
import struct
import sys
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\111\herness")
BOOT = ROOT / "core-rs" / "boot"
KERNEL_URL = "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/netboot/vmlinuz-lts"
BINARY = ROOT / "core-rs" / "target" / "x86_64-unknown-linux-musl" / "release" / "hs-core"


def cpio_newc(entries: list[tuple[str, bytes, int]]) -> bytes:
    """Минимальный cpio в формате newc (как у GNU cpio -H newc)."""
    out = bytearray()
    inode = 1
    for name, data, mode in entries:
        name_bytes = name.encode() + b"\x00"
        header = b"070701"
        header += b"".join(
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
    # завершающий элемент
    trailer_name = b"TRAILER!!!\x00"
    header = b"070701" + b"".join(f"{value:08X}".encode() for value in (0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(trailer_name), 0))
    out += header + trailer_name
    out += b"\x00" * ((4 - (len(header) + len(trailer_name)) % 4) % 4)
    return bytes(out)


def main() -> int:
    BOOT.mkdir(parents=True, exist_ok=True)

    kernel = BOOT / "vmlinuz-lts"
    if not kernel.exists():
        print("качаю ядро…")
        urllib.request.urlretrieve(KERNEL_URL, kernel)
    chosen = os.environ.get("HS_KERNEL", "vmlinuz-own")
    chosen_path = BOOT / chosen
    if chosen_path.exists():
        print(f"ядро для загрузки: {chosen} ({chosen_path.stat().st_size} байт)")
    else:
        print(f"ВНИМАНИЕ: ядра {chosen} нет в boot/")

    if not BINARY.exists():
        print(f"нет бинарника: {BINARY} — сначала cargo build --target x86_64-unknown-linux-musl")
        return 2
    payload = BINARY.read_bytes()

    method = "гипотеза: система из ядра и харнесса\n## Seal\nпечать\n".encode()
    archive = cpio_newc([("init", payload, 0o100755), ("method.md", method, 0o100644)])

    import gzip
    target = BOOT / "initramfs.cpio.gz"
    target.write_bytes(gzip.compress(archive, 9))
    print("initramfs:", target.stat().st_size, "байт | init:", len(payload), "| method:", len(method))
    return 0


if __name__ == "__main__":
    sys.exit(main())
