"""Проверить tool_search напрямую: находит ли он C-0295 в CLAIMS.md.

Модель ищет и не находит. Нужно проверить сам инструмент, а не модель.
Временный тест Rust: ищем подстроку в настоящем CLAIMS.md.

    python work/test_search_direct.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(r"C:\111\herness")

TEST = '''
    #[test]
    fn probe_search_finds_c0295() {
        let root = std::path::Path::new("/mnt/c/111/herness");
        let out = tool_search_in("CLAIMS.md C-0295", root)
            .unwrap_or_else(|e| format!("ERR {e}"));
        println!("РЕЗУЛЬТАТ: {out}");
        assert!(out.contains("C-0295"), "не нашёл: {out}");
    }
'''


def main() -> int:
    target = ROOT / "core-rs" / "src" / "loopmod.rs"
    backup = target.with_suffix(".rs.probe")
    text = target.read_text(encoding="utf-8")
    anchor = "mod tests {\n    use super::*;\n"
    if anchor not in text:
        print("не найдено место для теста — это UNKNOWN")
        return 2
    backup.write_text(text, encoding="utf-8")
    try:
        target.write_text(text.replace(anchor, anchor + TEST, 1), encoding="utf-8")
        command = ("cd /mnt/c/111/herness/core-rs && CARGO_NET_OFFLINE=true "
                   "rustup run stable cargo test --release --lib probe_search -- --nocapture 2>&1")
        result = subprocess.run(["wsl", "-d", "Ubuntu", "--exec", "bash", "-lc", command],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=900)
        out = (result.stdout or "") + (result.stderr or "")
        for line in out.splitlines():
            if "РЕЗУЛЬТАТ" in line or "test result" in line or "panicked" in line:
                print(line.strip()[:400])
    finally:
        target.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        backup.unlink(missing_ok=True)
        print("исходник восстановлен")
    return 0


if __name__ == "__main__":
    sys.exit(main())
