"""Одна нормативная карточка `head`, legacy помечена и не выдаёт допуск.

R7/R8: в репозитории лежали две карточки с `id="head"` в разных форматах. `card_atoms`
потреблял старую closure-карточку, а `tool-card-v1` — draft, и было неизвестно, какая закон.
Здесь проверяется, что id различаются, legacy — историческая, draft — единственная рабочая,
а словарь отказов и policy не расходятся с draft.

    python tests/test_head_cards.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import tool_card  # noqa: E402

LEGACY = ROOT / "lab" / "tools" / "cards" / "head.json"
DRAFT = ROOT / "lab" / "tools" / "drafts" / "head-v1.draft.json"
POLICY = ROOT / "lab" / "tools" / "policy.json"
CODES = ROOT / "lab" / "refusal-codes.json"

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((flag, message))


def main() -> int:
    legacy = json.loads(LEGACY.read_text(encoding="utf-8"))
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    codes = {item["code"] for item in json.loads(CODES.read_text(encoding="utf-8"))["codes"]}

    check(legacy["id"] != draft["id"], f"id различаются: {legacy['id']!r} != {draft['id']!r}")
    check(draft["id"] == "head", f"нормативная карточка называется head, получено {draft['id']!r}")
    check(legacy.get("status") == "superseded", "legacy помечена status=superseded")
    check(legacy.get("superseded_by") == "head", "legacy ссылается на superseded_by=head")
    check(tool_card.validate(legacy) == [], "legacy проходит старый валидатор как историческая")

    check(draft.get("schema_version") == "tool-card-v1", "draft использует tool-card-v1")
    check(draft.get("kind") == "file_read", "draft имеет kind=file_read")
    check(draft.get("template", {}).get("id") == "file_read_stream",
          "draft использует шаблон file_read_stream")
    unknown = sorted(set(draft.get("refusals") or []) - codes)
    check(unknown == [], f"draft не ссылается на коды вне словаря: {unknown}")

    # Ни одна пара карточек (cards + drafts) не делит id.
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for path in sorted((ROOT / "lab" / "tools" / "cards").glob("*.json")) + sorted(
        (ROOT / "lab" / "tools" / "drafts").glob("*.json")
    ):
        data = json.loads(path.read_text(encoding="utf-8"))
        card_id = data.get("id")
        if card_id in seen:
            duplicates.append(f"{seen[card_id]} и {path}")
        seen[card_id] = str(path)
    check(duplicates == [], f"в cards/drafts нет дублей id: {duplicates}")

    # Policy относится к новому head и только к fixtures; старый id не должен появляться.
    rules = json.loads(POLICY.read_text(encoding="utf-8"))["rules"]
    head_rules = [rule for rule in rules if rule.get("tool") == "head"]
    legacy_rules = [rule for rule in rules if rule.get("tool") == legacy["id"]]
    check(bool(head_rules), f"policy содержит правила head: {len(head_rules)}")
    check(legacy_rules == [], f"policy не содержит правил legacy id: {legacy_rules}")
    check(any(rule.get("effect") == "allow" and rule.get("resource") == "file:/mnt/fixtures/**"
              for rule in head_rules), "head разрешён только в fixtures")

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
