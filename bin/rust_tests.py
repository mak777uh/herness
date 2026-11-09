"""rust_tests.py — прогнать Rust-тесты ядра в WSL честно.

Почему отдельный скрипт (F-BUILD-1, 09.11.2026). Первый прогон в WSL дал
«55 из 55», а после правки исходника — «53 из 55», хотя правка была верной:
Cargo на `/mnt/c` (DrvFs) не замечает изменения mtime и **не пересобирает**,
оставляя старый `libhs_core.rlib`. Тесты при этом исполняются — над прежним
кодом. Это ложное зелёное, худший вид проверки.

Поэтому перед тестами артефакты ядра удаляются принудительно. Цена — секунды
сборки; выгода — тесты меряют тот код, который лежит в файле.

    python bin/rust_tests.py            # тесты
    python bin/rust_tests.py --build    # только сборка

Сеть WSL блокирует crates.io, поэтому сборка офлайн: кэш крейтов скопирован
из Windows (`CARGO_NET_OFFLINE=true`).
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE = ROOT / "core-rs"

CLEAN = ("rm -rf target/release/libhs_core.rlib "
         "target/release/deps/hs_core-* target/release/deps/libhs_core-*")


def wsl(script: str, timeout: int = 900) -> tuple[int, str]:
    result = subprocess.run(
        ["wsl", "-d", "Ubuntu", "--exec", "bash", "-lc", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Rust-тесты ядра в WSL")
    parser.add_argument("--build", action="store_true", help="только сборка")
    args = parser.parse_args(argv)

    command = "cargo build --release" if args.build else "cargo test --release --lib"
    script = (f"cd /mnt/c/111/herness/core-rs && {CLEAN} && "
              f"CARGO_NET_OFFLINE=true rustup run stable {command} 2>&1")

    code, out = wsl(script)
    tail = [line for line in out.splitlines()
            if re.search(r"test result|error\[|error:|FAILED|Compiling hs-core|Finished", line)]
    for line in tail[-12:]:
        print(line.strip())

    passed = re.search(r"test result: ok\. (\d+) passed; 0 failed", out)
    if passed and code == 0:
        print(f"\n[ok] тестов пройдено: {passed.group(1)}, провалов 0")
        return 0
    failed = re.search(r"(\d+) failed", out)
    print(f"\n[FAIL] провалов: {failed.group(1) if failed else 'неизвестно'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
