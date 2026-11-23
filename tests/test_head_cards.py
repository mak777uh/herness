"""Единственная нормативная карточка `head` — canonical tool-card-v1.

Legacy `head_legacy` хранится только в archive: исторический validate разрешён,
activation — нет. Черновики не являются вторым источником закона.

    python tests/test_head_cards.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import card_atoms, tool_card  # noqa: E402

TOOLS = ROOT / "lab" / "tools"
CANONICAL = TOOLS / "cards" / "head.json"
LEGACY = TOOLS / "archive" / "head_legacy.json"
DRAFTS = TOOLS / "drafts"
SCHEMA = TOOLS / "tool-card-v1.schema.json"
POLICY = TOOLS / "policy.json"
CARD_SHA256 = "361ad2ecd421fae57f7ec3ae4c5e7e5bc8befd4d6d21b68573c23a70e699fe97"
LEGACY_SHA256 = "e3ac2bc7331a4735807cd404ba88acffb2a4585e6c6ac9eeeb42cc38640e2110"

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def activation_issues(card: dict) -> list[str]:
    validator = getattr(tool_card, "validate_activation", None)
    if not callable(validator):
        return ["activation API отсутствует"]
    return validator(card)


def main() -> int:
    canonical = load(CANONICAL)
    legacy = load(LEGACY)
    policy = load(POLICY)
    cards = sorted((TOOLS / "cards").glob("*.json"))
    drafts = sorted(DRAFTS.glob("*"))
    schemas = sorted(TOOLS.glob("*schema*.json"))

    check(CANONICAL.is_file(), "canonical cards/head.json существует")
    check(canonical.get("id") == "head", f"canonical id=head, получено {canonical.get('id')!r}")
    check(canonical.get("schema_version") == "tool-card-v1",
          f"canonical schema_version=tool-card-v1, получено {canonical.get('schema_version')!r}")
    issues = tool_card.validate(canonical) if canonical else ["canonical не читается"]
    check(issues == [], f"canonical validate ok: {issues}")

    raw = CANONICAL.read_bytes() if CANONICAL.is_file() else b""
    digest = hashlib.sha256(raw).hexdigest()
    crlf = raw.count(b"\r\n")
    check(digest == CARD_SHA256 and len(raw) == 5832 and crlf == 313,
          f"canonical точные байты: sha256={digest}, bytes={len(raw)}, CRLF={crlf}")

    parsed_cards = [(path, load(path)) for path in cards]
    v1_heads = [str(path.relative_to(ROOT)).replace("\\", "/")
                for path, data in parsed_cards
                if data.get("id") == "head" and data.get("schema_version") == "tool-card-v1"]
    v1_cards = [path for path, data in parsed_cards if data.get("schema_version") == "tool-card-v1"]
    check(v1_heads == ["lab/tools/cards/head.json"] and len(v1_cards) == 1,
          f"canonical — единственная tool-card-v1 head: {v1_heads}")
    check(drafts == [], f"drafts пуст: {[str(path) for path in drafts]}")
    check(schemas == [SCHEMA], f"schema единственная: {[str(path) for path in schemas]}")

    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for path, data in parsed_cards:
        card_id = data.get("id")
        if not isinstance(card_id, str):
            continue
        if card_id in seen:
            duplicates.append(f"{seen[card_id]} и {path}")
        seen[card_id] = str(path)
    check(duplicates == [], f"id в cards не дублируются: {duplicates}")

    legacy_raw = LEGACY.read_bytes() if LEGACY.is_file() else b""
    legacy_digest = hashlib.sha256(legacy_raw).hexdigest()
    check(LEGACY.is_file() and legacy_digest == LEGACY_SHA256 and len(legacy_raw) == 1041,
          f"legacy сохранён байт-в-байт: sha256={legacy_digest}, bytes={len(legacy_raw)}")
    check(legacy.get("id") == "head_legacy"
          and legacy.get("status") == "superseded"
          and legacy.get("superseded_by") == "head",
          f"legacy archive status/superseded_by: id={legacy.get('id')!r}, "
          f"status={legacy.get('status')!r}, superseded_by={legacy.get('superseded_by')!r}")
    legacy_issues = tool_card.validate(legacy) if legacy else ["legacy archive не читается"]
    check(legacy_issues == [], f"legacy historical validate ok: {legacy_issues}")

    refused = activation_issues(legacy)
    check(bool(refused) and any("superseded" in issue for issue in refused),
          f"legacy activation отказ: {refused}")
    allowed = activation_issues(canonical)
    check(allowed == [], f"canonical activation ok: {allowed}")

    rules = policy.get("rules") or []
    head_rules = [rule for rule in rules if rule.get("tool") == "head"]
    legacy_rules = [rule for rule in rules if rule.get("tool") == "head_legacy"]
    check(bool(head_rules), f"policy содержит head: {len(head_rules)}")
    check(legacy_rules == [], f"policy не содержит head_legacy: {legacy_rules}")

    if canonical.get("schema_version") == "tool-card-v1":
        try:
            card_atoms.atoms(canonical)
        except card_atoms.CardShapeError as exc:
            message = str(exc).lower()
            check("v1" in message and ("автоконвер" in message or "конвер" in message),
                  f"card_atoms явно запрещает v1→v0: {exc}")
        else:
            check(False, "card_atoms неявно сконвертировал tool-card-v1")
    else:
        check(False, "canonical не tool-card-v1: запрет авто-конверсии не проверен")

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"проверок: {len(RESULTS)}, провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
