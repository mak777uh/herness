"""initramfs с каталогом /mnt и файлом режима: write (писать журнал) или check (читать)."""

from __future__ import annotations

import gzip
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\111\herness")
BOOT = ROOT / "core-rs" / "boot"
KERNEL_URL = "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/netboot/vmlinuz-lts"
BINARY = ROOT / "core-rs" / "target" / "x86_64-unknown-linux-musl" / "release" / "hs-core"


def cpio_newc(entries: list[tuple[str, bytes, int]]) -> bytes:
    out = bytearray()
    inode = 1
    for name, data, mode in entries:
        name_bytes = name.encode() + b"\x00"
        header = b"070701" + b"".join(
            f"{value:08X}".encode()
            for value in (inode, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name_bytes), 0)
        )
        out += header + name_bytes
        out += b"\x00" * ((4 - (len(header) + len(name_bytes)) % 4) % 4)
        out += data
        out += b"\x00" * ((4 - len(data) % 4) % 4)
        inode += 1
    trailer_name = b"TRAILER!!!\x00"
    header = b"070701" + b"".join(
        f"{value:08X}".encode() for value in (0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(trailer_name), 0)
    )
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
        print(f"нет бинарника: {BINARY} — сначала cargo build")
        return 2
    payload = BINARY.read_bytes()

    mode = os.environ.get("HS_MODE", "check")
    method = "гипотеза: система из ядра и харнесса\n## Seal\nпечать\n".encode()
    entries = [
        ("init", payload, 0o100755),
        ("method.md", method, 0o100644),
        ("mode", mode.encode(), 0o100644),
        ("dev", b"", 0o040755),
        ("mnt", b"", 0o040755),
    ]
    archive = cpio_newc(entries)
    target = BOOT / "initramfs.cpio.gz"
    target.write_bytes(gzip.compress(archive, 9))
    print(f"initramfs: {target.stat().st_size} байт | режим: {mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
