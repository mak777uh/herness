"""Инъекция: вернуть общий запрет net:** и проверить, что проверка краснеет.

Без этого «проверка проходит» ничего не значит (AGENTS.md §4).

    python bin/inject_net_policy_defect.py
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / "core-rs" / "src" / "loopmod.rs"
BACKUP = TARGET.with_suffix(".rs.bak")

ANCHOR = '    Rule { tool: "net", action: "write", resource: "file:/mnt/**", effect: Effect::Deny },'
INJECT = ('    Rule { tool: "net", action: "net", resource: "net:**", effect: Effect::Deny },\n'
          + ANCHOR)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if ANCHOR not in text:
        print("место для инъекции не найдено — это UNKNOWN, не PASS")
        return 2

    shutil.copy2(TARGET, BACKUP)
    try:
        TARGET.write_text(text.replace(ANCHOR, INJECT, 1), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "check_net_policy.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    finally:
        shutil.move(str(BACKUP), str(TARGET))

    caught = result.returncode != 0
    print("=== проверка на сломанной политике ===")
    for line in (result.stdout or "").strip().splitlines():
        if line.strip().startswith(("FAIL", "[FAIL]")):
            print(" ", line.strip())
    print()
    print(f"[{'ok' if caught else 'FAIL'}] проверка {'поймала' if caught else 'НЕ поймала'} "
          f"запрет, перекрывающий мост")
    return 0 if caught else 1


if __name__ == "__main__":
    sys.exit(main())
