"""lean_paths — единый резолвер путей Lean-контура (N4, host-side; смежное F-0080).

Дефект (N4): пять скриптов жёстко искали доказательства во внешнем каталоге
окружения (не в репо) и toolchain rc1, тогда как доказательства лежат В РЕПО
(`proofs/`), а `proofs/lean-toolchain` объявляет **rc2**, не rc1. Резолвер убирает
хардкод: сначала репо `proofs/`, env-override, fail-closed.

    python bin/lean_paths.py          # напечатать разрешённый каталог proofs
    python bin/lean_paths.py --bin    # напечатать разрешённый каталог lean bin

`proofs_dir()`: env `HERNESS_PROOFS` override, иначе `ROOT/proofs`; fail-closed
`SystemExit(3)`, если каталог не существует (нет доказательств — нет проверки,
а не молчаливый уход в чужой путь). `lean_bin()`: env `HERNESS_LEAN_BIN` override,
иначе `~/.elan/toolchains/<нормализованный toolchain>/bin`. Существование bin НЕ
проверяется здесь — это решает вызывающий (`lean_check.main`: `if not BIN.exists():
return 2`), чтобы резолвер оставался чистым разрешением пути.

Lean на хосте не вызывается (`~/.elan/toolchains` может отсутствовать, `lean`/`lake`
не на PATH). Поэтому N4 проверяется СТАТИЧЕСКИ (`bin/check_lean_paths.py`):
разрешение путей + fail-closed, не сборкой доказательств. N4 как proof-вопрос
остаётся открытым.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _normalize_toolchain(raw: str) -> str:
    """leanprover/lean4:v4.36.0-rc2 -> leanprover--lean4---v4.36.0-rc2 (elan dir name)."""
    return raw.strip().replace("/", "--").replace(":", "---")


def proofs_dir() -> Path:
    """Каталог доказательств: env override, иначе репо proofs/. Fail-closed exit 3."""
    override = os.environ.get("HERNESS_PROOFS")
    path = Path(override) if override else ROOT / "proofs"
    if not path.is_dir():
        raise SystemExit(3)
    return path


def lean_toolchain() -> str:
    """Строка toolchain из proofs/lean-toolchain (fail-closed, если proofs нет)."""
    path = proofs_dir() / "lean-toolchain"
    if not path.exists():
        raise SystemExit(3)
    return path.read_text(encoding="utf-8").strip()


def lean_bin() -> Path:
    """Каталог lean bin: env override, иначе elan toolchain из proofs/lean-toolchain.

    Существование НЕ проверяется (вызывающий решает сам). Но toolchain читается
    через proofs_dir(), поэтому при отсутствии proofs — fail-closed exit 3.
    """
    override = os.environ.get("HERNESS_LEAN_BIN")
    if override:
        return Path(override)
    name = _normalize_toolchain(lean_toolchain())
    return Path.home() / ".elan" / "toolchains" / name / "bin"


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if "--bin" in argv:
        print(lean_bin())
    else:
        print(proofs_dir())
    return 0


if __name__ == "__main__":
    sys.exit(main())