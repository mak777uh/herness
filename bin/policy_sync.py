"""policy_sync — политика в коде и политика в файле обязаны совпадать.

Посредник читает политику из константы в loopmod.rs, а проверяется она по lab/tools/policy.json.
Если они разойдутся, проверка будет зелёной, а код — другим. Этот гейт ловит расхождение.

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

RULE = re.compile(
    r'Rule\s*\{\s*tool:\s*"([^"]+)",\s*action:\s*"([^"]+)",\s*resource:\s*"([^"]+)",\s*'
    r'effect:\s*Effect::(Allow|Deny)\s*\}'
)


def main() -> int:
    source = LOOP.read_text(encoding="utf-8")
    in_code = {(m.group(1), m.group(2), m.group(3), m.group(4).lower()) for m in RULE.finditer(source)}
    data = json.loads(POLICY.read_text(encoding="utf-8"))
    in_file = {(r["tool"], r["action"], r["resource"], r["effect"])
               for r in data["rules"] if not r.get("implied")}

    lines = ["# Политика в коде и в файле", ""]
    only_file = sorted(in_file - in_code)
    only_code = sorted(in_code - in_file)
    for item in only_file:
        lines.append(f"только в файле: {item}")
    for item in only_code:
        lines.append(f"только в коде: {item}")
    if not only_file and not only_code:
        lines.append(f"совпадает: {len(in_file)} правил в обоих местах")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if not only_file and not only_code else 1


if __name__ == "__main__":
    sys.exit(main())
