"""Долг по рецензиям: утверждения, у которых последняя рецензия не upheld.

Показывает, что именно рецензент счёл недоказанным, и почему. Не блокирует гейты: решение о правке
утверждения — отдельное действие, а не автоматика.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / "lab" / "reviews"


def latest_by_claim() -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for path in sorted(REVIEWS.glob("*.md")):
        if path.name == "README.md":
            continue
        data = {}
        reasons = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("  - "):
                reasons.append(line[4:].strip())
            elif ":" in line and not line.startswith(" "):
                key, _, value = line.partition(":")
                data[key.strip()] = value.strip()
        data["reasons"] = reasons
        claim_id = data.get("id")
        if not claim_id:
            continue
        if claim_id not in latest or data.get("date", "") >= latest[claim_id].get("date", ""):
            latest[claim_id] = data
    return latest


def main() -> int:
    latest = latest_by_claim()
    debt = [item for item in latest.values() if item.get("verdict") != "upheld"]

    claims = [line for line in (ROOT / "CLAIMS.md").read_text(encoding="utf-8").splitlines()
              if line.startswith("| C-")]
    total = len(claims)
    reviewed = len(latest)
    unreviewed = max(0, total - reviewed)
    print(f"утверждений: {total} | прошли рецензию: {reviewed} | не проходили: {unreviewed} "
          f"| с вердиктом не upheld: {len(debt)}")
    if unreviewed:
        print(f"долг: {unreviewed} утверждений без враждебной проверки — это тоже долг, а не ноль")
    for item in sorted(debt, key=lambda row: row.get("id", "")):
        print(f"\n{item.get('id')}: {item.get('verdict')}")
        print(f"  утверждение: {item.get('claim', '')[:110]}")
        for reason in item.get("reasons", [])[:2]:
            print(f"  - {reason[:150]}")
    out = ROOT / "research" / "review-debt.json"
    out.write_text(json.dumps({"total": len(latest), "debt": len(debt),
                               "items": [{key: item.get(key) for key in
                                          ("id", "verdict", "claim", "reasons")} for item in debt]},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nзаписано: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
