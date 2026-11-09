"""Инъекция F-BRIDGE-1: снять проверку порта и убедиться, что тест краснеет.

Без этого «тест проходит» ничего не значит (AGENTS.md §4).

    python bin/inject_bridge_defect.py
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / "bin" / "bridge.py"
BACKUP = TARGET.with_suffix(".py.bak")

GUARD = """    if port_in_use(args.bind, args.port):
        print(f"порт {args.bind}:{args.port} уже занят — второй мост не нужен "
              f"и не запускается (иначе процессы копятся)", file=sys.stderr)
        return 3
"""


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if GUARD not in text:
        print("защита не найдена — инъекция невозможна, это UNKNOWN, не PASS")
        return 2

    shutil.copy2(TARGET, BACKUP)
    try:
        TARGET.write_text(text.replace(GUARD, "    # ИНЪЕКЦИЯ: проверка порта снята\n"),
                          encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "check_bridge_singleton.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    finally:
        shutil.move(str(BACKUP), str(TARGET))

    caught = result.returncode != 0
    print("=== тест на сломанном мосте ===")
    for line in (result.stdout or "").strip().splitlines():
        if line.strip().startswith(("FAIL", "[FAIL]")):
            print(" ", line.strip())
    print()
    print(f"[{'ok' if caught else 'FAIL'}] тест {'поймал' if caught else 'НЕ поймал'} "
          f"утечку процессов")
    return 0 if caught else 1


if __name__ == "__main__":
    sys.exit(main())
