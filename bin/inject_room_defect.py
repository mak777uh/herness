"""Инъекция дефекта F-ROOM-1 в плагин и проверка, что тест его ловит.

Зачем: проверка без отрицательного контроля меряет полноту, но не точность
(AGENTS.md §4). Здесь снимается защита «пустой ответ не PASS», тест обязан
покраснеть; затем файл возвращается из бэкапа.

    python bin/inject_room_defect.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "plugin" / "lib" / "index.js"
BACKUP = TARGET.with_suffix(".js.bak")

GUARD = '  if (verdict === "PASS" && !String(answer ?? "").trim()) return "UNKNOWN";'


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if GUARD not in text:
        print("защита не найдена в файле — инъекция невозможна, это UNKNOWN, не PASS")
        return 2

    shutil.copy2(TARGET, BACKUP)
    try:
        TARGET.write_text(text.replace(GUARD, "  // ИНЪЕКЦИЯ: защита снята"), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "check_room_verdict.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
        )
    finally:
        shutil.move(str(BACKUP), str(TARGET))

    caught = result.returncode != 0
    print("=== тест на сломанной версии ===")
    for line in (result.stdout or "").strip().splitlines():
        if line.strip().startswith(("FAIL", "[FAIL]")):
            print(" ", line.strip())
    print()
    print(f"[{'ok' if caught else 'FAIL'}] тест {'поймал' if caught else 'НЕ поймал'} подложенный дефект")
    return 0 if caught else 1


if __name__ == "__main__":
    sys.exit(main())
