"""Проверить политику инструмента net: разрешён только мост, всё прочее — отказ.

Зачем отдельно: политика живёт в двух местах (Rust и lab/tools/policy.json),
и расхождение ловится гейтом. Здесь проверяется СМЫСЛ: net может ходить
только к мосту, и общего запрета, перекрывающего мост, быть не должно —
именно он сломал первый прогон (запрет сильнее разрешения).

    python bin/check_net_policy.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUST = ROOT / "core-rs" / "src" / "loopmod.rs"
JSON_POLICY = ROOT / "lab" / "tools" / "policy.json"

BRIDGE = "net:10.0.2.2:8790"


def rust_rules() -> list[tuple[str, str, str, str]]:
    text = RUST.read_text(encoding="utf-8")
    block = re.search(r"pub const POLICY: &\[Rule\] = &\[(.*?)\n\];", text, re.S)
    if not block:
        return []
    out = []
    for match in re.finditer(
        r'Rule \{ tool: "([^"]+)", action: "([^"]+)", resource: "([^"]+)", '
        r'effect: Effect::(\w+) \}',
        block.group(1),
    ):
        out.append(match.groups())
    return out


def main() -> int:
    checks: list[tuple[str, bool]] = []

    rules = rust_rules()
    checks.append(("политика в Rust найдена", len(rules) > 0))

    net_rules = [r for r in rules if r[0] == "net"]
    checks.append(("у net есть правила", len(net_rules) > 0))

    allow_bridge = any(
        tool == "net" and action == "net" and resource == BRIDGE and effect == "Allow"
        for tool, action, resource, effect in net_rules
    )
    checks.append(("net разрешён к мосту", allow_bridge))

    # Главный контроль: запрета, который перекрывает мост, быть не должно.
    blanket_deny = [
        r for tool, action, resource, effect in net_rules
        if action == "net" and effect == "Deny" and resource.rstrip("*").rstrip(":")
        and BRIDGE.startswith(resource.rstrip("*").rstrip(":"))
    ]
    checks.append(("общего запрета, перекрывающего мост, нет", not blanket_deny))

    # Запись в файлы для net запрещена.
    checks.append(("net не пишет в файлы", any(
        tool == "net" and action == "write" and effect == "Deny"
        for tool, action, resource, effect in net_rules)))

    # JSON-политика: тот же адрес разрешён.
    data = json.loads(JSON_POLICY.read_text(encoding="utf-8"))
    json_net = [r for r in data["rules"] if r.get("tool") == "net"]
    checks.append(("в JSON у net есть правила", len(json_net) > 0))
    checks.append(("в JSON net разрешён к мосту", any(
        r.get("action") == "net" and r.get("resource") == BRIDGE
        and r.get("effect") == "allow" for r in json_net)))
    checks.append(("в JSON нет запрета, перекрывающего мост", not any(
        r.get("action") == "net" and r.get("effect") == "deny"
        and r.get("resource", "").lstrip("net:!").startswith("10.0.2.2")
        for r in json_net)))

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
