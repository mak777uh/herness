"""audit_facts — сухие факты о репозитории для аудита (без оценок).

Печатает счётчики и списки, на которые опирается план изменений: утверждения, отказы, критерии,
журналы, артефакты, следы незавершённости, артефакты без ссылок в CLAIMS.md.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    claims_text = read(ROOT / "CLAIMS.md")
    claims = re.findall(r"\| (C-\d{4}) \|", claims_text)
    cited = set(re.findall(r"(research/outputs/[A-Za-z0-9._\-]+|docs/[A-Za-z0-9._\-]+\.md|lab/[A-Za-z0-9._/\-]+)", claims_text))

    failures = sorted(path.stem for path in (ROOT / "lab" / "failures").glob("F-*.md"))
    adrs = sorted(path.stem for path in (ROOT / "docs").glob("ADR-*.md"))
    criteria = sorted(path.stem for path in (ROOT / "accept").glob("*.json"))
    journals = sorted(path.name for path in (ROOT / "runs" / "accept").glob("*.bin"))
    outputs = sorted(path.name for path in (ROOT / "research" / "outputs").glob("*"))

    todo = Counter()
    for path in list((ROOT / "bin").glob("*.py")) + list((ROOT / "core-rs" / "src").glob("*.rs")) + list((ROOT / "docs").glob("*.md")):
        text = read(path)
        for word in ("TODO", "FIXME", "XXX", "не реализовано", "не сделано"):
            todo[word] += len(re.findall(word, text, re.IGNORECASE))

    ledger = json.loads(read(ROOT / "lab" / "adoptions.json") or "[]")
    adopted = [entry["id"] for entry in ledger if entry.get("status") == "adopted"]
    planned = [entry["id"] for entry in ledger if entry.get("status") == "planned"]
    rejected = [entry["id"] for entry in ledger if entry.get("status") == "rejected"]

    gates_path = ROOT / "bin" / "hs.py"
    gates = re.findall(r'\("([^"]+)", gate_[a-z_]+\)', read(gates_path))
    negative = []
    for name in gates:
        probe = (ROOT / "bin" / f"check_{name}.py")
        if probe.exists() and "--self-test" in read(probe):
            negative.append(name)
    if "autonomy" in " ".join(gates):
        negative.append("автономия(check_autonomy self-test)" if (ROOT / "bin/check_autonomy.py").exists() else "—")

    uncited = [name for name in outputs if f"research/outputs/{name}" not in cited]

    print("== утверждения")
    print("всего:", len(claims), "| уникальных:", len(set(claims)), "| повторов:", len(claims) - len(set(claims)))
    print("== артефакты")
    print("в research/outputs:", len(outputs), "| не упомянуты в CLAIMS.md:", len(uncited))
    for name in uncited[:15]:
        print("   ", name)
    print("== отказы:", len(failures), "| ADR:", len(adrs), "| критерии:", len(criteria), "| журналы:", len(journals))
    print("== гейты:", len(gates))
    print("с отрицательным контролем (self-test):", ", ".join(sorted(set(negative))) or "нет")
    print("== склад решений")
    print("внедрено:", len(adopted), "| отложено:", len(planned), "| отклонено:", len(rejected))
    print("== следы незавершённости")
    for word, count in todo.most_common():
        if count:
            print(f"   {word}: {count}")
    print("== размер репозитория")
    total = sum(1 for _ in ROOT.rglob("*") if _.is_file())
    print("файлов:", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
