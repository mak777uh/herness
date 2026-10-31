"""Тесты бюджета прогона: три предела останавливают цикл, а не «предупреждают»."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    # Бюджет проверяется сборочными тестами Rust: денежный, временной и по шагам.
    result = subprocess.run(
        ["cargo", "test", "--lib", "бюджет"],
        cwd=ROOT / "core-rs",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = (result.stdout or result.stderr).strip().splitlines()
    failed = 0 if result.returncode == 0 else 1
    print("\n".join(tail[-6:]))
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
