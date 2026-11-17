"""policy_sync — политика обязана иметь ОДИН источник, и Rust обязан встраивать его.

История: до R8 правила жили дважды — 14 в `loopmod.rs` и 19 в `policy.json`. Этот прибор
сравнивал только правила без `implied`, то есть 14 из 19, и показывал «совпадает», пока
пять запретов (включая `file:!/mnt/**`) не проверялись. Это было ложное зелёное.

Теперь сравнивать нечего: источник один. Прибор проверяет, что это действительно так —
`include_str!` на месте, ручной копии `POLICY` нет, JSON разбирается и не содержит
неявных разрешений (`!` с allow).

    python bin/policy_sync.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOP = ROOT / "core-rs" / "src" / "loopmod.rs"
POLICY = ROOT / "lab" / "tools" / "policy.json"
OUT = ROOT / "research" / "outputs" / "policy-sync.txt"

INCLUDE = 'include_str!("../../lab/tools/policy.json")'


def main() -> int:
    source = LOOP.read_text(encoding="utf-8")
    data = json.loads(POLICY.read_text(encoding="utf-8"))
    rules = list(data["rules"])

    problems: list[str] = []
    if INCLUDE not in source:
        problems.append(f"Rust не встраивает policy.json: нет {INCLUDE}")
    if "pub const POLICY" in source:
        problems.append("в Rust осталась ручная копия POLICY — снова два источника")
    if re.search(r'Rule\s*\{\s*tool:\s*"', source):
        problems.append('в Rust есть литеральные Rule { tool: "..." } — это ручная копия')

    ids = [rule.get("id") for rule in rules]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        problems.append(f"повторяющиеся id: {duplicates}")
    for rule in rules:
        for field in ("id", "tool", "action", "resource", "effect", "level"):
            if field not in rule:
                problems.append(f"правило {rule.get('id', '?')}: нет поля {field}")
        if rule.get("effect") not in ("allow", "deny"):
            problems.append(f"правило {rule.get('id')}: эффект {rule.get('effect')!r}")
        path = str(rule.get("resource", ""))
        if path.startswith(("file:!", "dir:!", "net:!")) and rule.get("effect") == "allow":
            problems.append(f"правило {rule.get('id')}: `!` с allow — неявное разрешение")

    lines = ["# Политика: источник и встраивание", ""]
    lines.append(f"источник: {POLICY.relative_to(ROOT).as_posix()}")
    lines.append(f"встроен в Rust через include_str!: {'да' if INCLUDE in source else 'НЕТ'}")
    lines.append(f"ручная копия POLICY в Rust: {'есть' if 'pub const POLICY' in source else 'нет'}")
    lines.append(f"правил: {len(rules)}")
    if problems:
        lines.append("")
        lines.extend(f"[FAIL] {problem}" for problem in problems)
    else:
        lines.append("совпадает: один источник, Rust встраивает его при компиляции")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
