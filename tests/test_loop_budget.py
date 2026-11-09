"""Тесты бюджета прогона: три предела останавливают цикл, а не «предупреждают»."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cargo_test(filter_word: str) -> tuple[int, str]:
    """Запустить cargo test там, где он исполним.

    На Windows бинарник ядра — Linux, и `cargo test` падает с «не является
    приложением Win32». Тогда идём в WSL, как bin/rust_tests.py: там Rust есть
    и тесты исполняются по-настоящему (C-0292).
    """
    if sys.platform == "win32":
        if shutil.which("wsl") is None:
            return 2, "нет wsl: Rust-тесты не запустить на Windows"
        command = ("cd /mnt/c/111/herness/core-rs && CARGO_NET_OFFLINE=true "
                   f"rustup run stable cargo test --release --lib {filter_word} 2>&1")
        result = subprocess.run(["wsl", "-d", "Ubuntu", "--exec", "bash", "-lc", command],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace")
        return result.returncode, (result.stdout or "") + (result.stderr or "")

    result = subprocess.run(["cargo", "test", "--release", "--lib", filter_word],
                            cwd=ROOT / "core-rs", capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    # Бюджет проверяется сборочными тестами Rust: денежный, временной и по шагам.
    code, out = cargo_test("бюджет")
    tail = out.strip().splitlines()
    failed = 0 if code == 0 else 1
    print("\n".join(tail[-6:]))
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
