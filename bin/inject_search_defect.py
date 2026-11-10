"""Инъекция F-SEARCH-1: вернуть старое окно (последние 160 символов).

Тесты обязаны покраснеть, иначе они ничего не проверяют (AGENTS.md §4).

    python bin/inject_search_defect.py
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / "core-rs" / "src" / "loopmod.rs"
BACKUP = TARGET.with_suffix(".rs.bak")

# Старое поведение: окно = последние 160 символов, без учёта позиции совпадения.
NEW_BLOCK_START = "                let trimmed = line.trim();\n                let chars: Vec<char> = trimmed.chars().collect();"
OLD_BLOCK = (
    "                let trimmed = line.trim();\n"
    "                let start = trimmed.chars().count().saturating_sub(160);\n"
    "                let shown: String = if start == 0 {\n"
    "                    trimmed.chars().take(160).collect()\n"
    "                } else {\n"
    "                    let offset = trimmed\n"
    "                        .char_indices()\n"
    "                        .nth(start.min(trimmed.chars().count().saturating_sub(1)))\n"
    "                        .map(|(byte, _)| byte)\n"
    "                        .unwrap_or(0);\n"
    "                    format!(\"…{}\", trimmed[offset..].chars().take(160).collect::<String>())\n"
    "                };\n"
)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if NEW_BLOCK_START not in text:
        print("новый блок не найден — инъекция невозможна, это UNKNOWN")
        return 2

    # Находим весь новый блок до строки matches.push.
    start = text.index(NEW_BLOCK_START)
    end = text.index("                matches.push(format!(", start)
    shutil.copy2(TARGET, BACKUP)
    try:
        injected = text[:start] + OLD_BLOCK + text[end:]
        TARGET.write_text(injected, encoding="utf-8")
        result = subprocess.run([sys.executable, str(ROOT / "bin" / "rust_tests.py")],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=900)
    finally:
        shutil.move(str(BACKUP), str(TARGET))

    caught = result.returncode != 0
    print("=== тесты на старом окне ===")
    for line in ((result.stdout or "") + (result.stderr or "")).splitlines():
        if "FAILED" in line or "провалов" in line:
            print(" ", line.strip()[:120])
    print()
    print(f"[{'ok' if caught else 'FAIL'}] тесты {'поймали' if caught else 'НЕ поймали'} "
          f"старое окно")
    return 0 if caught else 1


if __name__ == "__main__":
    sys.exit(main())
