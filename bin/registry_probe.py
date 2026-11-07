"""registry_probe — отрицательный контроль реестра (E1 плана P33 + A-0042).

Проверяем, что реестр отвергает записи без хеша среды, без происхождения, без примеров вызова
и повтор (имя, версия). Годный реестр не должен давать находок.

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

    cases = [
        ("без хеша среды", [dict(rows[0], environment="")] + rows[1:]),
        ("без происхождения", [dict(rows[0], provenance="")] + rows[1:]),
        ("повтор имени и версии", rows + [rows[0]]),
        ("без примеров вызова", [dict(rows[0], examples=[])] + rows[1:]),
        ("шесть примеров", [dict(rows[0], examples=["a", "b", "c", "d", "e", "f"])] + rows[1:]),
        ("без семантики", [dict(rows[0], semantics="")] + rows[1:]),
    ]

    lines = ["# Отрицательный контроль реестра инструментов", ""]
    caught = 0
    for name, variant in cases:
        found = [item for item in reg.problems(variant) if item not in baseline]
        ok = bool(found)
        caught += 1 if ok else 0
        lines.append(f"{name:26} {'поймано' if ok else 'ПРОПУЩЕНО'}  {found[:1]}")

    clean = reg.problems(rows)
    lines.append(f"{'годный реестр':26} {'чисто' if not clean else 'ЛОЖНАЯ ТРЕВОГА'}  {clean[:1]}")
    lines += ["", f"поймано дефектов: {caught} из {len(cases)}"]
    text = "\n".join(lines) + "\n"
    (ROOT / "research" / "outputs" / "registry-check.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0 if caught == len(cases) and not clean else 1


if __name__ == "__main__":
    sys.exit(main())
