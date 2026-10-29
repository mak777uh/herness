"""self_audit — факты о репозитории для честного саморазбора."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STDLIB = {"json", "os", "sys", "re", "time", "pathlib", "subprocess", "hashlib", "dataclasses",
          "datetime", "typing", "collections", "argparse", "shutil", "tempfile", "urllib",
          "random", "math", "unittest", "functools", "itertools", "textwrap", "statistics",
          "dataclasses", "concurrent", "threading", "io", "csv"}


def main() -> int:
    claims = [line for line in (ROOT / "CLAIMS.md").read_text(encoding="utf-8").splitlines()
              if re.match(r"^\|\s*C-\d+", line)]
    kinds = {"команда": 0, "свидетельство": 0, "проза": 0}
    for line in claims:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        command, artifact = cells[3].strip("`"), cells[4]
        if re.search(r"\b(python|pytest|git|bash|pwsh|node)\b", command):
            kinds["команда"] += 1
        elif artifact and artifact not in ("—", "") and not artifact.startswith("вывод"):
            kinds["свидетельство"] += 1
        else:
            kinds["проза"] += 1
    print("утверждения по носителю:", kinds)

    criteria = [line for line in (ROOT / "docs" / "CRITERIA.md").read_text(encoding="utf-8").splitlines()
                if re.match(r"^\|\s*K\d+", line)]
    by_method: dict[str, int] = {}
    for line in criteria:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        method = cells[2] if len(cells) > 2 else "?"
        by_method[method] = by_method.get(method, 0) + 1
    print("критерии по способу:", by_method)
    print("критериев всего:", len(criteria))

    external: list[str] = []
    for path in list((ROOT / "core").rglob("*.py")) + list((ROOT / "bin").rglob("*.py")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"\s*(?:import|from)\s+([A-Za-z_][\w]*)", line)
            if match and match.group(1) not in STDLIB and match.group(1) != "core":
                external.append(match.group(1))
    print("импорты вне stdlib:", sorted(set(external)))

    adrs = sorted((ROOT / "docs").glob("ADR-*.md"))
    formal = [p.name for p in adrs if "предложено" in p.read_text(encoding="utf-8")[:400]]
    print("ADR:", len(adrs), "| из них со статусом «предложено»:", len(formal))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
