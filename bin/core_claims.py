"""core_claims — разделение утверждений на «ядро» и «учёт».

Зачем: «218 утверждений» — правдивое и вводящее в заблуждение число одновременно. Ядро — то, на чём
стоит продукт (журнал, хост, приёмка, метрики, отказы, склад решений). Остальное — учёт, который
тоже нужен, но не является знанием.

    python bin/core_claims.py            # core: N из M, список проблем
    python bin/core_claims.py --list     # показать ядро

Правило: ядро задаётся явным списком lab/core-claims.txt, а не подбором по ключевым словам. Список
ревьюится глазами; гейт проверяет, что каждый id существует и что ядро не меньше 15.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "lab" / "core-claims.txt"
CLAIMS = ROOT / "CLAIMS.md"
MIN_CORE = 15


def claims_ids() -> list[str]:
    text = CLAIMS.read_text(encoding="utf-8") if CLAIMS.exists() else ""
    return re.findall(r"\| (C-\d{4}) \|", text)


def core_ids() -> list[str]:
    if not CORE.exists():
        return []
    ids = []
    for line in CORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.append(line)
    return ids


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    known = claims_ids()
    core = core_ids()
    problems = []

    if not core:
        problems.append("нет lab/core-claims.txt или он пуст")
    duplicates = [ident for ident in set(core) if core.count(ident) > 1]
    if duplicates:
        problems.append(f"повторы в ядре: {duplicates}")
    missing = [ident for ident in core if ident not in known]
    if missing:
        problems.append(f"в ядре есть несуществующие утверждения: {missing}")
    if len(core) < MIN_CORE:
        problems.append(f"ядро меньше {MIN_CORE}: {len(core)}")

    if "--list" in args:
        print("# ядро")
        for ident in core:
            print(" ", ident)

    print(f"core: {len(core)} из {len(known)} (учётных: {len(known) - len(core)})")
    for problem in problems:
        print(f"[FAIL] {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
