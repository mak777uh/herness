"""registry_probe — отрицательный контроль реестра (эксперимент E1 плана P33).

Проверяем, что реестр отвергает записи без хеша среды и без происхождения, и что повтор
(имя, версия) ловится.

    python bin/registry_probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import build_registry as reg  # noqa: E402


def main() -> int:
    rows = [json.loads(line) for line in reg.REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    baseline = reg.problems(rows)

    cases = []
    # 1. запись без хеша среды
    broken_env = [dict(rows[0], environment="")] + rows[1:]
    cases.append(("без хеша среды", broken_env))
    # 2. запись без происхождения
    broken_prov = [dict(rows[0], provenance="")] + rows[1:]
    cases.append(("без происхождения", broken_prov))
    # 3. повтор (имя, версия)
    cases.append(("повтор имени и версии", rows + [rows[0]]))

    lines = ["# Отрицательный контроль реестра инструментов", ""]
    caught = 0
    for name, variant in cases:
        found = [item for item in reg.problems(variant) if item not in baseline]
        ok = bool(found)
        caught += 1 if ok else 0
        lines.append(f"{name:26} {'поймано' if ok else 'ПРОПУЩЕНО'}  {found[:1]}")

    # 4. годный реестр не должен давать находок
    clean = reg.problems(rows)
    lines.append(f"{'годный реестр':26} {'чисто' if not clean else 'ЛОЖНАЯ ТРЕВОГА'}  {clean[:1]}")
    lines += ["", f"поймано дефектов: {caught} из {len(cases)}"]
    text = "\n".join(lines) + "\n"
    (ROOT / "research" / "outputs" / "registry-check.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0 if caught == len(cases) and not clean else 1


if __name__ == "__main__":
    sys.exit(main())
