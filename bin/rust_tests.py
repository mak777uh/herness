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


def wsl_path(path: pathlib.Path) -> str:
    """Windows-путь → путь WSL (/mnt/<drive>/...), без захардкоженного каталога.

    Было: жёстко записанный каталог C:/111/herness/core-rs — тесты гоняли **другой чекаут** и давали зелёное
    про тот код, которого в этом репозитории может не быть. Тот же класс, что N4.
    """
    text = path.resolve().as_posix()
    if re.match(r"^[A-Za-z]:/", text):
        return "/mnt/" + text[0].lower() + text[2:]
    return text


def parse_results(out: str) -> tuple[int, int]:
    """Сумма passed/failed по всем тестовым бинарникам, а не первый попавшийся.

    Дефект F-BRIDGE-TAINT-1 (18.11.2026): при красном интеграционном тесте
    вывод содержал сначала «133 passed; 0 failed» (lib), потом
    «0 passed; 2 failed» (integration). Старый код брал первый `(\\d+) failed`
    и печатал «провалов: 0», хотя rc=1. Это не ложное зелёное (гейт красный),
    но ложное объяснение: агент читает «0» и ищет причину не там.
    """
    passed = sum(int(value) for value in re.findall(r"test result: ok\. (\d+) passed", out))
    failed = sum(int(value) for value in re.findall(r"test result: FAILED\. \d+ passed; (\d+) failed", out))
    return passed, failed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Rust-тесты ядра в WSL")
    parser.add_argument("--build", action="store_true", help="только сборка")
    args = parser.parse_args(argv)

    command = "cargo build --release" if args.build else "cargo test --release --lib --tests"
    core_wsl = wsl_path(CORE)
    # fail-closed: нет каталога — это отказ с кодом 3, а не «0 тестов = успех».
    guard = (f"test -d '{core_wsl}' || {{ echo \"нет каталога: {core_wsl}\" >&2; exit 3; }}; ")
    script = (guard + f"cd '{core_wsl}' && {CLEAN} && "
              f"CARGO_NET_OFFLINE=true rustup run stable {command} 2>&1")

    code, out = wsl(script)
    tail = [line for line in out.splitlines()
            if re.search(r"test result|error\[|error:|FAILED|Compiling hs-core|Finished", line)]
    for line in tail[-12:]:
        print(line.strip())

    passed, failed = parse_results(out)
    if passed and code == 0 and failed == 0:
        print(f"\n[ok] тестов пройдено: {passed}, провалов 0")
        return 0
    # Провал без строки `test result: FAILED` — это не «0 провалов», а ошибка
    # сборки/запуска: причина неизвестна, и скрывать её нельзя.
    print(f"\n[FAIL] провалов: {failed if failed else 'неизвестно'}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
