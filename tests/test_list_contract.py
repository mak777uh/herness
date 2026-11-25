"""W12 list: contract и registry описывают ту же семантику, что и Rust runtime.

Запуск: python tests/test_list_contract.py
Ровно 8 checks; baseline до implementation обязан быть RED.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import registry_state  # noqa: E402

RESULTS: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok))
    suffix = f" — {detail}" if detail else ""
    print(f"[{'ok' if ok else 'FAIL'}] {name}{suffix}")


def main() -> int:
    contracts = json.loads((ROOT / "lab" / "tools" / "contracts.json").read_text(encoding="utf-8"))
    # Genesis snapshot заморожен. Актуальное описание выводится из append-only события;
    # отсутствие resolver/description — RED, а не повод переписать snapshot.
    registry = registry_state.computed_state()["tools"]["list"].get("description", {})
    atoms = contracts["list"]["atoms"]
    by_id = {atom["id"]: atom for atom in atoms}

    limit = next((atom for atom in atoms if atom.get("action", {}).get("verb") == "limit"), None)
    check("contract: list limit 100", bool(limit and limit["action"].get("quantity") == "100"))

    order = next((atom for atom in atoms if atom.get("action", {}).get("verb") == "order"), None)
    check(
        "contract: deterministic dirs-first order",
        bool(order and order["action"].get("object") == "entries"
             and order["action"].get("value") == "directories_first_then_files_by_name"),
    )

    remainder = next((atom for atom in atoms if atom.get("action", {}).get("verb") == "report"), None)
    check(
        "contract: exact remainder duty",
        bool(remainder and remainder["action"].get("object") == "remainder"
             and remainder["action"].get("quantity") == "total_minus_shown"),
    )

    missing_escape_atoms = [escape.get("atom") for escape in contracts["list"].get("escapes", [])
                            if escape.get("atom") not in by_id]
    check("contract: escape anchors exist", not missing_escape_atoms, str(missing_escape_atoms))

    check("registry: list version 4", registry.get("version") == 4)
    check("registry: output limit 100", registry.get("output", {}).get("limit") == 100)

    semantics = str(registry.get("semantics", "")).lower()
    check(
        "registry: deterministic order and exact remainder",
        "детерминирован" in semantics and "остат" in semantics,
    )
    expected_marker = "… (обрезано: показано {limit}, осталось {remainder})"
    check("registry: exact truncation marker", registry.get("output", {}).get("truncated") == expected_marker)

    failed = sum(not ok for _, ok in RESULTS)
    print(f"\nlist contract: {len(RESULTS) - failed}/{len(RESULTS)} checks, failures: {failed}")
    return 0 if failed == 0 and len(RESULTS) == 8 else 1


if __name__ == "__main__":
    sys.exit(main())
