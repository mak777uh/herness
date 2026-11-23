"""Тесты бюджета прогона: три предела останавливают цикл, а не «предупреждают»."""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin import rust_tests  # noqa: E402


def cargo_test(filter_word: str) -> tuple[int, str]:
    """Запустить cargo test там, где он исполним.

    На Windows бинарник ядра — Linux, и `cargo test` падает с «не является
    приложением Win32». Тогда идём в WSL, как bin/rust_tests.py: там Rust есть
    и тесты исполняются по-настоящему (C-0292).
    """
    if sys.platform == "win32":
        if shutil.which("wsl") is None:
            return 2, "нет wsl: Rust-тесты не запустить на Windows"
        core_wsl = shlex.quote(rust_tests.wsl_path(ROOT / "core-rs"))
        command = (f"cd {core_wsl} && {rust_tests.CLEAN} && CARGO_NET_OFFLINE=true "
                   f"rustup run stable cargo test --release --lib {shlex.quote(filter_word)} 2>&1")
        return rust_tests.wsl(command)

    result = subprocess.run(["cargo", "test", "--release", "--lib", filter_word],
                            cwd=ROOT / "core-rs", capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    # Бюджет проверяется сборочными тестами Rust: денежный, временной и по шагам.
    code, out = cargo_test("бюджет")
    tail = out.strip().splitlines()
    matches = re.findall(r"test result: ok\. (\d+) passed;", out)
    passed = sum(int(value) for value in matches)
    ok = code == 0 and passed > 0
    print("\n".join(tail[-6:]))
    print(f"[{'ok' if ok else 'FAIL'}] Rust budget tests: {passed} passed, rc={code}")
    print(f"провалов: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
