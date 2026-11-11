"""Собрать core-rs/relay.exe из bin/tcp_relay.py (нужен для QEMU guestfwd).

Зачем .exe, а не .cmd: `guestfwd` запускает команду через CreateProcess, а `.cmd` — скрипт для
`cmd.exe`, который так не исполняется. Гость получает Connection refused, потому что команда
не стартовала.

    python bin/build_relay.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "bin" / "tcp_relay.py"
TARGET = ROOT / "core-rs" / "relay.exe"


def main() -> int:
    if shutil.which("pyinstaller") is None:
        print("нет pyinstaller: pip install pyinstaller", file=sys.stderr)
        return 2
    result = subprocess.run(
        [
            "pyinstaller",
            "--onefile",
            "--noconsole",
            "--distpath", str(TARGET.parent),
            "--workpath", str(TARGET.parent / "build-relay"),
            "--specpath", str(TARGET.parent / "build-relay"),
            "--name", "relay",
            str(SOURCE),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout[-2000:], file=sys.stderr)
        print(result.stderr[-2000:], file=sys.stderr)
        return result.returncode
    print(f"собран {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
