"""probes_inventory — что ловит каждая проверка и есть ли дубли.

Шаг 2 плана: сократить проверки. Сначала — список: что ловит каждая и что уникального.

    python bin/probes_inventory.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin"
OUT = ROOT / "research" / "outputs" / "probes-inventory.txt"

# Проверки, которые входят в гейты (их трогать нельзя без причины).
IN_GATES = {
    "policy.py", "policy_sync.py", "closure_probe.py", "registry_probe.py",
    "gate_probe.py", "check_artifacts.py", "check_adoptions.py", "check_autonomy.py",
    "check_briefs.py", "verify_claims.py", "verify_journal.py", "readme_numbers.py",
    "kernel_audit.py", "security_audit.py", "lean_check.py", "bridge_lean.py",
    "policy_diff.py", "refusal_codes_probe.py", "claims_audit.py", "gate_audit.py",
    "contract_probe.py", "anchor_probe.py",
}


def docstring(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.match(r'^\s*"""(.*?)"""', text, re.DOTALL)
    if match:
        first = match.group(1).strip().splitlines()[0]
        return first[:100]
    return "(нет описания)"


def main() -> int:
    lines = ["# Проверки: что ловит каждая", ""]
    candidates = sorted(p for p in BIN.glob("*.py")
                        if re.search(r"probe|audit|check|verify", p.name))
    lines.append(f"всего проверок: {len(candidates)}")
    lines.append("")
    lines.append("| файл | в гейтах | что делает |")
    lines.append("|---|---|---|")
    for path in candidates:
        gate = "да" if path.name in IN_GATES else "нет"
        lines.append(f"| `{path.name}` | {gate} | {docstring(path)} |")

    lines.append("")
    lines.append("## Кандидаты на удаление (не в гейтах)")
    lines.append("")
    outside = [p.name for p in candidates if p.name not in IN_GATES]
    lines.append(f"Проверок вне гейтов: **{len(outside)}**. Каждая — либо разведка, либо дубль.")
    lines.append("")
    for name in outside:
        lines.append(f"- `{name}`")

    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print("\n".join(lines[:40]))
    print(f"\n... всего строк: {len(lines)}")
    print(f"записано: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
