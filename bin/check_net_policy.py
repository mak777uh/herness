"""Проверить политику инструмента net: разрешён только мост, всё прочее — отказ.

Зачем отдельно от `check_policy_parity.py`: это смысловая проверка одного инструмента,
и её же использует инъекция дефекта (`inject_net_policy_defect.py`). Проверка читает
ровно тот же JSON, который встроен в Rust; ручной копии правил больше нет.

    python bin/check_net_policy.py
    python bin/check_net_policy.py --policy <другой.json>   # для инъекции дефекта
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUST = ROOT / "core-rs" / "src" / "loopmod.rs"
JSON_POLICY = ROOT / "lab" / "tools" / "policy.json"
INCLUDE = 'include_str!("../../lab/tools/policy.json")'

BRIDGE = "net:10.0.2.2:8790"

sys.path.insert(0, str(ROOT / "bin"))
from check_policy_parity import allows  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="net ходит только к мосту")
    parser.add_argument("--policy", type=pathlib.Path, default=JSON_POLICY)
    args = parser.parse_args(argv)

    checks: list[tuple[str, bool]] = []

    source = RUST.read_text(encoding="utf-8")
    checks.append(("Rust встраивает policy.json", INCLUDE in source))
    checks.append(("в Rust нет ручной копии POLICY", "pub const POLICY" not in source))

    data = json.loads(args.policy.read_text(encoding="utf-8"))
    rules = list(data["rules"])
    checks.append(("правила прочитаны", len(rules) > 0))

    net_rules = [r for r in rules if r.get("tool") == "net"]
    checks.append(("у net есть правила", len(net_rules) > 0))

    allow_bridge = any(
        rule.get("tool") == "net" and rule.get("action") == "net"
        and rule.get("resource") == BRIDGE and rule.get("effect") == "allow"
        for rule in rules
    )
    checks.append(("net разрешён к мосту", allow_bridge))

    # Главный контроль: политика обязана разрешать мост. Любой deny, который его
    # перекрывает (например, общий `net:**`), делает мост недоступным — это FAIL.
    checks.append(("запрет не перекрывает мост", allows(rules, "net", "net", BRIDGE)))
    checks.append(("сеть вне моста запрещена", not allows(rules, "net", "net", "net:1.1.1.1:53")))

    checks.append(("net не пишет в файлы", any(
        rule.get("tool") == "net" and rule.get("action") == "write"
        and rule.get("effect") == "deny" for rule in rules)))

    bad = 0
    for title, ok in checks:
        if not ok:
            bad += 1
        print(f"{'ok  ' if ok else 'FAIL'} {title}")
    print()
    if bad:
        print(f"[FAIL] провалено: {bad} из {len(checks)}")
        return 1
    print(f"[ok] пройдено: {len(checks)} из {len(checks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
