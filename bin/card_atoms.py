"""card_atoms — карточка инструмента, сведённая в хоффельдовские атомы.

Зачем (DESIGN-0002 §3, части харнеса). Инструмент у нас уже описывается атомами: право/обязанность,
кто, перед кем, какое действие над каким ресурсом (`lab/tools/contracts.json`). Это же форма модуля
в nomos и предмет проверки lexspec — «якорь или отказ». Карточка пока несёт только замыкание,
входы и примеры; атомы из неё выводятся, и их можно сверить с правилами политики.

Три режима:
  --derive  напечатать атомы, выведенные из карточки (черновик для contracts.json);
  --gaps    показать атомы без правил в policy.json (что генератору осталось заполнить);
  --check   упасть, если карточка и политика противоречат друг другу (S4_POLICY_CONFLICT).

    python bin/card_atoms.py --derive lab/tools/cards/head.json
    python bin/card_atoms.py --gaps   lab/tools/cards/head.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "lab" / "tools" / "policy.json"


def atoms(card: dict) -> list[dict]:
    closure = card.get("closure") or {}
    fs = closure.get("fs") or {}
    read = list(fs.get("read") or [])
    write = list(fs.get("write") or [])
    out: list[dict] = []
    index = 0

    for scope in read or ["/mnt/**"]:
        index += 1
        out.append({
            "id": f"a{index}",
            "relation": "right",
            "bearer": "agent",
            "counterparty": "harness",
            "action": {"verb": "read", "object": "file", "scope": scope},
            "conditions": ["path_inside_room"],
            "why": "без этого инструмент бесполезен",
        })

    index += 1
    out.append({
        "id": f"a{index}",
        "relation": "duty",
        "bearer": "harness",
        "counterparty": "agent",
        "action": {"verb": "limit", "object": "output", "quantity": f"{closure.get('output_bytes')}B"},
        "conditions": ["output_is_capped"],
        "why": "контекст модели — бюджет, а не бесплатный ресурс",
    })

    index += 1
    out.append({
        "id": f"a{index}",
        "relation": "duty",
        "bearer": "agent",
        "counterparty": "harness",
        "action": {"verb": "refuse", "object": "request", "scope": ", ".join(card.get("refusals") or [])},
        "conditions": ["reason_from_vocabulary"],
        "why": "отказ — штатный исход с кодом причины, а не молчание",
    })

    if not write:
        index += 1
        out.append({
            "id": f"a{index}",
            "relation": "duty",
            "bearer": "agent",
            "counterparty": "harness",
            "action": {"verb": "write", "object": "file", "scope": "!/mnt/work/**"},
            "negated": True,
            "conditions": ["declared_closure"],
            "why": "запись не объявлена — значит её нет",
        })

    if not closure.get("net"):
        index += 1
        out.append({
            "id": f"a{index}",
            "relation": "duty",
            "bearer": "agent",
            "counterparty": "harness",
            "action": {"verb": "net", "object": "endpoint", "scope": "!any"},
            "negated": True,
            "conditions": ["declared_closure"],
            "why": "сеть не объявлена — значит её нет",
        })
    return out


def load_policy(path: Path = POLICY) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("rules", [])


def _verbs_of(atom: dict) -> set[str]:
    verb = str((atom.get("action") or {}).get("verb", ""))
    return {verb} | ({"net"} if verb == "net" else set())


def gaps(card: dict, rules: list[dict] | None = None) -> list[str]:
    """Атомы, для которых в политике нет правила этого инструмента."""
    rules = load_policy() if rules is None else rules
    tool = card.get("id")
    mine = [rule for rule in rules if rule.get("tool") == tool]
    out = []
    for atom in atoms(card):
        verbs = _verbs_of(atom)
        if not any(rule.get("action") in verbs for rule in mine):
            out.append(f"{atom['id']}: {atom['relation']} {sorted(verbs)} у инструмента {tool} нет правила")
    return out


def conflicts(card: dict, rules: list[dict] | None = None) -> list[str]:
    """Противоречия: политика разрешает то, что карточка объявила запретом (S4_POLICY_CONFLICT)."""
    rules = load_policy() if rules is None else rules
    tool = card.get("id")
    mine = [rule for rule in rules if rule.get("tool") == tool]
    denied = {str((a.get("action") or {}).get("verb")) for a in atoms(card) if a.get("negated")}
    out = []
    for rule in mine:
        if rule.get("effect") == "allow" and rule.get("action") in denied:
            out.append(
                f"S4_POLICY_CONFLICT: {rule.get('id')} разрешает {rule.get('action')}, "
                f"а карточка {tool} это запрещает"
            )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="карточка → атомы и сверка с политикой")
    parser.add_argument("--derive", metavar="CARD")
    parser.add_argument("--gaps", metavar="CARD")
    parser.add_argument("--check", metavar="CARD")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    target = args.derive or args.gaps or args.check
    if not target:
        parser.print_help()
        return 2
    path = Path(target)
    if not path.exists():
        print(f"[FAIL] нет файла: {path}", file=sys.stderr)
        return 2
    card = json.loads(path.read_text(encoding="utf-8"))

    if args.derive:
        print(json.dumps({"id": card["id"], "atoms": atoms(card)}, ensure_ascii=False, indent=1))
        return 0

    if args.gaps:
        items = gaps(card)
        for item in items:
            print(f"[gap] {item}")
        print(f"пробелов: {len(items)}")
        return 0

    bad = conflicts(card)
    for item in bad:
        print(f"[FAIL] {item}")
    if not bad:
        print(f"[ok] карточка {card['id']} не противоречит политике (правил у инструмента: "
              f"{len([r for r in load_policy() if r.get('tool') == card['id']])})")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
