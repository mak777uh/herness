"""gate_rust — Rust-тесты ядра должны быть исполнены, а не «наверное, проходят».

Зачем отдельный гейт (F-BUILD-1, 09.11.2026). Первый прогон в WSL дал
«55 из 55», а после правки исходника — «53 из 55», хотя правка была верной:
Cargo на `/mnt/c` (DrvFs) не замечает изменение mtime и не пересобирает,
оставляя старый `libhs_core.rlib`. Тесты исполнялись над прежним кодом.
Это ложное зелёное — худший вид проверки, и без гейта оно вернётся молча.

Два режима:

* **быстрый** (по умолчанию, в контуре A): проверяет, что артефакт тестов
  свежее самого нового исходника `core-rs/src/*.rs`. Если исходник новее
  артефакта — тесты не отражают код, и это провал гейта;
* **полный** (`--rust`): запускает `bin/rust_tests.py` (чистит артефакты и
  прогоняет 55 тестов в WSL). Занимает около 70 секунд, поэтому не в каждом
  прогоне гейтов.

Почему не полный всегда: гейты гоняются часто, и минута на каждый прогон
сделает их тем, что перестают запускать. Быстрый режим ловит именно тот
дефект, из-за которого гейт заведён, за доли секунды.

    python bin/gate_rust.py            # быстрый
    python bin/gate_rust.py --rust     # полный прогон в WSL
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "core-rs" / "src"
# Артефакты, которые Cargo переиспользует, не замечая правок. Проверяем ОБА
# места: target/release (тесты) и target/x86_64-unknown-linux-musl/release
# (бинарник, который попадает в комнату). Второй важнее: 09.11.2026
# make_initramfs взял musl-бинарник от 01:09 при исходнике новее, и в комнату
# уехало старое поведение поиска — исправление не дошло до прогона.
TARGETS = [
    ROOT / "core-rs" / "target" / "release",
    ROOT / "core-rs" / "target" / "x86_64-unknown-linux-musl" / "release",
]


def newest_artifact() -> tuple[float, str]:
    """Самый свежий артефакт ядра: rlib, тестовый бинарник или musl-бинарник."""
    latest, name = 0.0, ""
    for target in TARGETS:
        candidates = (list(target.glob("libhs_core*.rlib"))
                      + list(target.glob("deps/hs_core-*"))
                      + list(target.glob("hs-core")))
        for path in candidates:
            if not path.is_file():
                continue
            mtime = path.stat().st_mtime
            if mtime > latest:
                latest, name = mtime, path.name
    return latest, name


def newest_source() -> tuple[float, str]:
    latest, name = 0.0, ""
    for path in SRC.glob("*.rs"):
        mtime = path.stat().st_mtime
        if mtime > latest:
            latest, name = mtime, path.name
    return latest, name


def check_fresh() -> list[str]:
    """Артефакт тестов должен быть свежее самого нового исходника."""
    problems: list[str] = []
    source_mtime, source_name = newest_source()
    if not source_name:
        return ["в core-rs/src нет исходников — проверять нечего"]

    artifact_mtime, artifact_name = newest_artifact()
    if not artifact_name:
        # Артефакта нет: тесты не собирались вовсе. Это не провал механизма,
        # а отсутствие прогона — но гейт обязан это назвать, а не промолчать.
        problems.append(
            "нет артефактов ядра в core-rs/target/release: Rust-тесты не собирались. "
            "Запусти: python bin/rust_tests.py")
        return problems

    if artifact_mtime < source_mtime:
        problems.append(
            f"артефакт {artifact_name} старше исходника {source_name}: тесты "
            f"исполнялись над прежним кодом (F-BUILD-1). Запусти: python bin/rust_tests.py")
    return problems


def run_full() -> list[str]:
    """Полный прогон: bin/rust_tests.py чистит артефакты и гоняет тесты в WSL."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "rust_tests.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
    )
    if result.returncode == 0:
        return []
    tail = " ".join(((result.stdout or "") + (result.stderr or "")).strip().splitlines()[-3:])
    return [f"Rust-тесты не прошли: {tail[:200]}"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="гейт Rust-тестов ядра")
    parser.add_argument("--rust", action="store_true", help="полный прогон в WSL")
    args = parser.parse_args(argv)

    problems = run_full() if args.rust else check_fresh()
    mode = "полный" if args.rust else "быстрый"
    if problems:
        print(f"[FAIL] rust ({mode}): {len(problems)} проблем")
        for problem in problems:
            print(f"   - {problem}")
        return 1
    print(f"[ok] rust ({mode}): 0 проблем")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
