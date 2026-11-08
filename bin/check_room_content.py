"""Отрицательный контроль для build_room.py --check (F-ROOM-6).

Проверка, которая не ловит подмену, меряет только полноту. Здесь
подкладывается файл с ДРУГИМ содержимым и тем же именем: --check обязан
покраснеть. Затем образ восстанавливается.

    python bin/check_room_content.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "history" / "gitlog.txt"


def run_check() -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "build_room.py"), "--check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    if not TARGET.exists():
        print(f"нет файла для подмены: {TARGET} — это UNKNOWN, не PASS")
        return 2

    original = TARGET.read_bytes()
    print(f"контроль: подменяю {TARGET.relative_to(ROOT)} тем же именем, другим содержимым")

    code_before, out_before = run_check()
    print(f"  до подмены: код {code_before} "
          f"({'зелёная' if code_before == 0 else 'красная'})")

    caught = False
    try:
        TARGET.write_bytes(original + "\n# подложено проверкой\n".encode("utf-8"))
        code_after, out_after = run_check()
        caught = code_after != 0 and "содержимое расходится" in out_after
        print(f"  после подмены: код {code_after} "
              f"({'поймала' if caught else 'НЕ поймала'})")
        for line in out_after.splitlines():
            if "расходится" in line or "ПРОБЛЕМЫ" in line:
                print("   ", line.strip())
    finally:
        TARGET.write_bytes(original)

    code_restored, _ = run_check()
    restored = code_restored == 0
    print(f"  после восстановления: код {code_restored} "
          f"({'зелёная' if restored else 'красная'})")

    print()
    if caught and restored:
        print("[ok] проверка ловит подмену содержимого и возвращается в зелёное")
        return 0
    print("[FAIL] проверка не ловит подмену или образ не восстановился")
    return 1


if __name__ == "__main__":
    sys.exit(main())
