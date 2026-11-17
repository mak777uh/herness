"""Тест сведения карточки в атомы: право, обязанности, запреты, пробелы и противоречия.

Отдельный регрессионный блок — ложное зелёное R5: пустой `fs.read` не должен превращаться
в право `read /mnt/**`, конфликт должен проверяться в обе стороны, а `uncovered` — не «ok».
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import card_atoms  # noqa: E402

RESULTS: list[tuple[bool, str]] = []
CARD = json.loads((ROOT / "lab" / "tools" / "cards" / "head.json").read_text(encoding="utf-8"))
NET_CARD = {
    "id": "netprobe-test",
    "closure": {
        "fs": {"read": [], "write": []},
        "net": ["10.0.2.2:8790"],
        "output_bytes": 256,
    },
    "refusals": ["S6_CLOSURE_BREACH"],
}


def check(flag: bool, message: str) -> None:
    RESULTS.append((flag, message))


def rule(rule_id: str, action: str, effect: str, resource: str) -> dict:
    return {"id": rule_id, "tool": "head", "action": action, "effect": effect, "resource": resource}


def main() -> int:
    derived = card_atoms.atoms(CARD)
    relations = [atom["relation"] for atom in derived]
    check(len(derived) == 5, f"атомов head выведено {len(derived)} (ожидалось 5)")
    check(relations.count("right") == 1, "одно право: чтение внутри комнаты")
    check(relations.count("duty") == 4, "четыре обязанности: лимит, отказ, запреты записи и сети")

    capped = [a for a in derived if (a.get("action") or {}).get("verb") == "limit"]
    check(bool(capped) and "8192B" in capped[0]["action"]["quantity"],
          f"лимит выдачи взят из замыкания: {capped[0]['action'] if capped else '—'}")
    check(bool(capped) and capped[0].get("bearer") == "harness"
          and capped[0].get("counterparty") == "agent",
          "обязанность лимита: harness перед agent, а не harness перед собой")
    refused = [a for a in derived if (a.get("action") or {}).get("verb") == "refuse"]
    check(bool(refused) and refused[0].get("bearer") == "agent"
          and refused[0].get("counterparty") == "harness",
          "обязанность отказа: agent перед harness")

    denied = [a for a in derived if a.get("negated")]
    check(any((a.get("action") or {}).get("verb") == "write" for a in denied),
          "запись не объявлена — атом-запрет есть")
    check(any((a.get("action") or {}).get("verb") == "net" for a in denied),
          "сеть не объявлена — атом-запрет есть")
    check(all((a.get("action") or {}).get("scope") == "**" for a in denied),
          "запрет отсутствующего эффекта — универсальный, а не «всё, кроме /mnt/work»")

    # У нового инструмента правил ещё нет: все атомы — пробелы.
    empty_rules: list[dict] = []
    items = card_atoms.gaps(CARD, empty_rules)
    check(len(items) == len(derived), f"без правил все {len(derived)} атомов — пробелы")

    # Правило появилось — пробелов меньше.
    rules = [rule("head-allow", "read", "allow", "file:/mnt/**")]
    check(len(card_atoms.gaps(CARD, rules)) == len(derived) - 1, "правило на чтение закрывает один пробел")

    # Противоречие: политика разрешает запись, а карточка её запрещает.
    wrong = [rule("head-write", "write", "allow", "file:/mnt/work/**")]
    issues = card_atoms.conflicts(CARD, wrong)
    check(any("S4_POLICY_CONFLICT" in issue for issue in issues),
          f"разрешение записи при запрете в карточке поймано: {issues}")
    check(card_atoms.conflicts(CARD, rules) == [], "правило на чтение противоречий не даёт")
    check(card_atoms.uncovered(CARD, rules) == [], "правило на чтение покрывает право карточки")

    # R5: пустой read не должен синтезировать право чтения.
    net_atoms = card_atoms.atoms(NET_CARD)
    read_atoms = [a for a in net_atoms if (a.get("action") or {}).get("verb") == "read"]
    check(read_atoms == [], "пустой fs.read не порождает право чтения")
    check(not any((a.get("action") or {}).get("scope") == "/mnt/**" for a in net_atoms),
          "в атомах нет синтезированного /mnt/**")
    net_rights = [a for a in net_atoms if a.get("relation") == "right"]
    check(len(net_rights) == 1 and (net_rights[0].get("action") or {}).get("verb") == "net",
          "объявленная сеть даёт ровно одно право net")

    # Политика запрещает чтение, которого карточка не объявляет: конфликта нет.
    deny_read = [{"id": "netprobe-deny-fs", "tool": "netprobe-test", "action": "read",
                  "effect": "deny", "resource": "file:/mnt/**"}]
    check(card_atoms.conflicts(NET_CARD, deny_read) == [],
          "policy deny на необъявленное чтение не даёт конфликта")
    check(len(card_atoms.uncovered(NET_CARD, deny_read)) == 1,
          "без allow на сеть право net остаётся uncovered")

    # С allow на точный endpoint карточка покрыта, а чтения по-прежнему нет.
    net_allow = deny_read + [{"id": "netprobe-allow", "tool": "netprobe-test", "action": "net",
                              "effect": "allow", "resource": "net:10.0.2.2:8790"}]
    check(card_atoms.conflicts(NET_CARD, net_allow) == [],
          "точный allow на endpoint не конфликтует и не создаёт скрытого чтения")
    check(card_atoms.uncovered(NET_CARD, net_allow) == [],
          "точный allow на endpoint покрывает право net")

    # Двусторонность: policy deny против права карточки.
    deny_card_read = [rule("head-deny-read", "read", "deny", "file:/mnt/**")]
    check(any("S4_POLICY_CONFLICT" in issue for issue in card_atoms.conflicts(CARD, deny_card_read)),
          "policy deny на чтение ловит право карточки")

    # policy allow, которого нет в карточке, — скрытое разрешение.
    orphan = [rule("head-allow-read", "read", "allow", "file:/mnt/**"),
              rule("head-allow-list", "list", "allow", "dir:/mnt/**")]
    check(any("скрытое разрешение" in issue for issue in card_atoms.conflicts(CARD, orphan)),
          "allow без права карточки назван скрытым разрешением")

    # /mnt2 не лежит под /mnt.
    outside = [rule("head-allow-outside", "read", "allow", "file:/mnt2/**")]
    check(any("скрытое разрешение" in issue for issue in card_atoms.conflicts(CARD, outside)),
          "/mnt2/** не считается покрытием /mnt/** (граница сегмента)")
    check(card_atoms.uncovered(CARD, outside) != [],
          "allow на /mnt2/** не покрывает право /mnt/**")

    # Отрицание ресурса: запрет вне /mnt не пересекает чтение внутри /mnt.
    outside_deny = [rule("head-allow-read", "read", "allow", "file:/mnt/**"),
                    rule("head-deny-outside", "read", "deny", "file:!/mnt/**")]
    check(card_atoms.conflicts(CARD, outside_deny) == [],
          "deny вне /mnt не конфликтует с allow внутри /mnt")

    # Пустой read + allow на чтение = скрытое разрешение.
    empty_read_card = {
        "id": "empty-read",
        "closure": {"fs": {"read": [], "write": []}, "net": [], "output_bytes": 1},
        "refusals": [],
    }
    empty_allow = [{"id": "empty-allow-read", "tool": "empty-read", "action": "read",
                    "effect": "allow", "resource": "file:/mnt/**"}]
    check(any("скрытое разрешение" in issue for issue in card_atoms.conflicts(empty_read_card, empty_allow)),
          "allow на чтение при пустом read — скрытое разрешение")

    # Отсутствующее обязательное поле — ошибка формы, а не пустой эффект.
    broken = {"id": "broken", "closure": {"fs": {"write": []}, "net": [], "output_bytes": 1},
              "refusals": []}
    try:
        card_atoms.atoms(broken)
        check(False, "отсутствующий fs.read не был отвергнут")
    except card_atoms.CardShapeError:
        check(True, "отсутствующий fs.read отвергнут как S1_SCHEMA")

    # CLI: legacy-карточка head с реальной политикой не «зелёная». Её право /mnt/**
    # конфликтует с head-deny-outside (только fixtures): это конфликт (rc=1), а не
    # покрытие. Карточка будет переименована при миграции реестра.
    rc = card_atoms.main(["--check", str(ROOT / "lab" / "tools" / "cards" / "head.json"),
                          "--policy", str(ROOT / "lab" / "tools" / "policy.json")])
    check(rc != 0, f"head с реальной политикой не «зелёный», получено rc={rc}")

    # CLI: синтетическая карточка + policy во временном каталоге.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        card_path = tmp_path / "card.json"
        policy_path = tmp_path / "policy.json"
        card_path.write_text(json.dumps(NET_CARD, ensure_ascii=False), encoding="utf-8")
        policy_path.write_text(json.dumps({"rules": net_allow}, ensure_ascii=False), encoding="utf-8")
        rc = card_atoms.main(["--check", str(card_path), "--policy", str(policy_path)])
        check(rc == 0, f"покрытая синтетическая карточка даёт rc=0, получено {rc}")

        policy_path.write_text(json.dumps({"rules": deny_read}, ensure_ascii=False), encoding="utf-8")
        rc = card_atoms.main(["--check", str(card_path), "--policy", str(policy_path)])
        check(rc == 3, f"непокрытая синтетическая карточка даёт rc=3, получено {rc}")

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
