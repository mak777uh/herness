"""Инъекция в Rust: вернуть общий запрет net:** и прогнать тесты в WSL.

Проверка, которая не ловила бы возврат дефекта, ничего не стоит
(AGENTS.md §4). Здесь дефект возвращается в исходник, тесты обязаны
покраснеть, затем файл восстанавливается.

    python bin/inject_net_rust_defect.py
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


def run_tests() -> tuple[int, str]:
    # Через bin/rust_tests.py, а не напрямую: он чистит артефакты ядра.
    # Без этого Cargo на /mnt/c не замечает правку и тестирует СТАРЫЙ код —
    # инъекция «не ловилась» бы, хотя дефект внесён (F-BUILD-1).
    result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "rust_tests.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if ANCHOR not in text:
        print("место для инъекции не найдено — это UNKNOWN, не PASS")
        return 2

    shutil.copy2(TARGET, BACKUP)
    try:
        TARGET.write_text(text.replace(ANCHOR, INJECT, 1), encoding="utf-8")
        code, out = run_tests()
    finally:
        shutil.move(str(BACKUP), str(TARGET))

    failed = [line.strip() for line in out.splitlines() if "FAILED" in line or "panicked" in line]
    caught = code != 0
    print("=== тесты на сломанной политике ===")
    for line in failed[:6]:
        print(" ", line[:120])
    print()
    print(f"[{'ok' if caught else 'FAIL'}] тесты {'поймали' if caught else 'НЕ поймали'} "
          f"возврат общего запрета")
    return 0 if caught else 1


if __name__ == "__main__":
    sys.exit(main())
