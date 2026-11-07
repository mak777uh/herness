"""policy_probe — отрицательный контроль политики.

Проверяем, что проверка политики ловит четыре дефекта:
  1. противоречие (allow и deny на один ресурс);
  2. неявное разрешение («всё, кроме» с эффектом allow);
  3. цикл делегирования;
  4. правило без уровня.

    python bin/policy_probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import policy as pol  # noqa: E402


def main() -> int:
    base = pol.load()
    baseline = pol.check(base)

    cases = []
    # 1. противоречие: добавить allow на тот же ресурс, где уже deny
    contradiction = json.loads(json.dumps(base))
    contradiction["rules"].append(
        {"id": "fake-allow", "tool": "read", "subject": "agent", "action": "write",
         "resource": "file:/mnt/**", "effect": "allow", "level": "A", "why": "подложено"}
    )
    cases.append(("противоречие", contradiction))

    # 2. неявное разрешение: «всё, кроме» с allow
    implicit = json.loads(json.dumps(base))
    implicit["rules"].append(
        {"id": "fake-implicit", "tool": "read", "subject": "agent", "action": "read",
         "resource": "file:!/mnt/secret/**", "effect": "allow", "level": "A", "why": "подложено"}
    )
    cases.append(("неявное разрешение", implicit))

    # 3. цикл делегирования
    cycle = json.loads(json.dumps(base))
    cycle["delegation"] = [{"from": "agent", "to": "harness"}, {"from": "harness", "to": "agent"}]
    cases.append(("цикл делегирования", cycle))

    # 4. правило без уровня
    nolevel = json.loads(json.dumps(base))
    nolevel["rules"].append(
        {"id": "fake-nolevel", "tool": "read", "subject": "agent", "action": "list",
         "resource": "dir:/mnt/**", "effect": "deny", "why": "подложено"}
    )
    cases.append(("без уровня", nolevel))

    lines = ["# Отрицательный контроль политики", ""]
    caught = 0
    for name, variant in cases:
        found = [item for item in pol.check(variant) if item not in baseline]
        ok = bool(found)
        caught += 1 if ok else 0
        lines.append(f"{name:22} {'поймано' if ok else 'ПРОПУЩЕНО'}  {found[:1]}")

    clean = pol.check(base)
    lines.append(f"{'годная политика':22} {'чисто' if not clean else 'ЛОЖНАЯ ТРЕВОГА'}  {clean[:1]}")
    lines += ["", f"поймано дефектов: {caught} из {len(cases)}"]
    text = "\n".join(lines) + "\n"
    (ROOT / "research" / "outputs" / "policy-check.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0 if caught == len(cases) and not clean else 1


if __name__ == "__main__":
    sys.exit(main())
