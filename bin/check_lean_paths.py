"""check_lean_paths — замороженный прибор N4 (статическая проверка путей Lean).

Lean на хосте не вызывается, поэтому N4 проверяется СТАТИЧЕСКИ:
  * 0 хардкодов `C:/111/env/lean/proofs` и устаревшего toolchain `v4.36.0-rc1`
    в `bin/*.py` (сам чекер исключён — иглы собраны из фрагментов);
  * все 5 Lean-скриптов импортируют резолвер `from bin.lean_paths import`;
  * поведенческий fail-closed NC: `HERNESS_PROOFS` на несуществующий каталог → exit 3;
  * позитивный контроль: default → exit 0, печатает разрешённый `ROOT/proofs`.

КРАСНЫЙ-ДО: 3 немигрированных (`bridge_lean.py`, `bridge_parts.py`, `session_types.py`).
ЗЕЛЁНЫЙ-ПОСЛЕ: все 5 мигрированы на резолвер.

    python bin/check_lean_paths.py

Выход 0 — пути разрешаются через резолвер, fail-closed работает; 1 — хардкод остался
или резолвер не подключён, или fail-closed/позитивный контроль не сработали.

Это ПРИБОР, не гейт: в `hs.py gates` не входит (32/32 probe-покрытие не ломается).
Заморожен до прогона CONTINUITY-R1: хеш файла запечатан в ключе ответа, агент B
не имеет права его редактировать (allowlist). N4 как proof-вопрос остаётся открытым.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = ROOT / "bin"

# Иглы собраны из фрагментов: сам чекер не содержит хардкод-литерал целиком.
HARDCODE = "C:/111/env/" + "lean/proofs"
STALE_TC = "v4.36.0-" + "rc1"
IMPORT_MARK = "from bin.lean_paths import"
LEAN_SCRIPTS = ("lean_check.py", "policy_diff.py", "bridge_lean.py",
                "bridge_parts.py", "session_types.py")
SELF = "check_lean_paths.py"


def static_problems() -> list[str]:
    problems: list[str] = []
    for path in sorted(BIN_DIR.glob("*.py")):
        if path.name == SELF:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if HARDCODE in text:
            problems.append(f"{path.name}: хардкод пути доказательств ({HARDCODE})")
        if STALE_TC in text:
            problems.append(f"{path.name}: устаревший toolchain ({STALE_TC})")
    for name in LEAN_SCRIPTS:
        path = BIN_DIR / name
        if not path.exists():
            problems.append(f"{name}: отсутствует")
            continue
        if IMPORT_MARK not in path.read_text(encoding="utf-8", errors="replace"):
            problems.append(f"{name}: не импортирует резолвер ({IMPORT_MARK})")
    return problems


def behavioral() -> tuple[bool, list[str]]:
    """NC fail-closed + позитивный контроль через subprocess lean_paths.py."""
    notes: list[str] = []
    ok = True
    resolver = BIN_DIR / "lean_paths.py"
    if not resolver.exists():
        return False, ["резолвер bin/lean_paths.py отсутствует"]

    # NC: env override на несуществующий каталог → fail-closed exit 3.
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "no-such-proofs"
        env = dict(os.environ, HERNESS_PROOFS=str(missing))
        proc = subprocess.run([sys.executable, str(resolver)], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env)
        if proc.returncode != 3:
            ok = False
            notes.append(f"NC fail-closed: ожидался exit 3, получен {proc.returncode}")
        else:
            notes.append("NC fail-closed: exit 3 (несуществующий HERNESS_PROOFS отвергнут)")

    # Позитивный контроль: default → exit 0, печатает ROOT/proofs.
    proc = subprocess.run([sys.executable, str(resolver)], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        ok = False
        notes.append(f"позитивный контроль: ожидался exit 0, получен {proc.returncode}")
    else:
        printed = proc.stdout.strip()
        expected = str(ROOT / "proofs")
        if printed != expected:
            ok = False
            notes.append(f"позитивный контроль: напечатано {printed!r}, ожидалось {expected!r}")
        else:
            notes.append(f"позитивный контроль: exit 0, proofs={printed}")
    return ok, notes


def main() -> int:
    lines = ["# N4: статическая проверка путей Lean (check_lean_paths)", ""]
    sp = static_problems()
    ok, notes = behavioral()
    lines.append(f"статических проблем: {len(sp)}")
    lines.extend(f"  - {p}" for p in sp)
    lines.append("")
    lines.extend(f"  {n}" for n in notes)
    lines.append("")
    if sp or not ok:
        lines.append("## FAIL (хардкод остался / резолвер не подключён / fail-closed сломан)")
        verdict, code = "КРАСНЫЙ", 1
    else:
        lines.append("## PASS (все 5 через резолвер, fail-closed работает)")
        verdict, code = "ЗЕЛЁНЫЙ", 0
    lines += [
        "",
        f"вердикт: {verdict}",
        "",
        "## Что это не доказывает",
        "",
        "- что Lean-доказательства собраны: Lean на хосте не вызывается, проверяется разрешение путей;",
        "- что N4 закрыт как proof-вопрос: статическая проверка путей ≠ сборка Proofs;",
        "- что прибор ловит произвольный дефект путей: он ловит регрессию ЭТОГО хардкода + fail-closed.",
    ]
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())