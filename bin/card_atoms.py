"""card_atoms — карточка инструмента, сведённая в хоффельдовские атомы.

Зачем (DESIGN-0002 §3, части харнеса). Инструмент у нас уже описывается атомами: право/обязанность,
кто, перед кем, какое действие над каким ресурсом (`lab/tools/contracts.json`). Это же форма модуля
в nomos и предмет проверки lexspec — «якорь или отказ». Карточка пока несёт только замыкание,
входы и примеры; атомы из неё выводятся, и их можно сверить с правилами политики.

Три режима:
  --derive  напечатать атомы, выведенные из карточки (черновик для contracts.json);
  --gaps    показать атомы без правил в policy.json (что генератору осталось заполнить);
  --check   упасть, если карточка и политика противоречат друг другу или право карточки
            не покрыто разрешением политики.

    python bin/card_atoms.py --derive lab/tools/archive/head_legacy.json
    python bin/card_atoms.py --gaps   lab/tools/archive/head_legacy.json
    python bin/card_atoms.py --check  lab/tools/archive/head_legacy.json

Границы v0:
  * tool-card-v1 не конвертируется в v0: автоконверсия обязательств запрещена явно;
  * пустой массив — это «эффекта нет», а не wildcard; отсутствующее обязательное поле — ошибка;
  * из карточки не синтезируется ни один путь, которого в ней нет;
  * проверка двусторонняя: policy allow против запрета карточки и policy deny против права
    карточки; лишнее разрешение политики (orphan grant) — тоже конфликт;
  * `--check` возвращает 0 только когда все права карточки покрыты allow-правилами и нет
    ни одного конфликта. `uncovered` — не «зелёный», rc=3;
  * сравнение областей консервативное: если вложенность/непересечение не удалось доказать,
    это не «ok», а конфликт или uncovered. Объединение нескольких allow-правил в одно
    покрытие v0 не вычисляет.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "lab" / "tools" / "policy.json"


class CardShapeError(ValueError):
    """Карточка не даёт достаточной и однозначной информации для атомов."""


@dataclass(frozen=True)
class Scope:
    """Область ресурсов: file/dir/net, с необязательным дополнением `!`."""

    kind: str
    negated: bool
    mode: str  # universal | prefix | exact | unknown
    value: str
    text: str


def _list_of_strings(mapping: dict, key: str, where: str) -> list[str]:
    if not isinstance(mapping, dict) or key not in mapping:
        raise CardShapeError(f"{where}: нет обязательного поля")
    value = mapping[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CardShapeError(f"{where}: ожидался список строк")
    return value


def _closure(card: dict) -> tuple[list[str], list[str], list[str], int, list[str]]:
    closure = card.get("closure")
    if not isinstance(closure, dict):
        raise CardShapeError("closure: нет обязательного объекта")
    fs = closure.get("fs")
    if not isinstance(fs, dict):
        raise CardShapeError("closure.fs: нет обязательного объекта")
    read = _list_of_strings(fs, "read", "closure.fs.read")
    write = _list_of_strings(fs, "write", "closure.fs.write")
    net = _list_of_strings(closure, "net", "closure.net")
    output_bytes = closure.get("output_bytes")
    if isinstance(output_bytes, bool) or not isinstance(output_bytes, int) or output_bytes < 0:
        raise CardShapeError("closure.output_bytes: ожидалось целое >= 0")
    refusals = _list_of_strings(card, "refusals", "refusals")
    return read, write, net, output_bytes, refusals


def atoms(card: dict) -> list[dict]:
    """Вывести атомы только из явно объявленных эффектов legacy v0 карточки."""
    if not isinstance(card, dict):
        raise CardShapeError("карточка: ожидался JSON-объект")
    if "schema_version" in card:
        version = card["schema_version"]
        raise CardShapeError(
            f"schema_version={version!r}: автоконверсия {version}→v0 запрещена; "
            "сначала нужен явный IR-перевод, а не потеря обязательств tool-card-v1"
        )
    read, write, net, output_bytes, refusals = _closure(card)
    out: list[dict] = []
    index = 0

    def add(relation: str, bearer: str, counterparty: str, action: dict,
            conditions: list[str], why: str, negated: bool = False) -> None:
        nonlocal index
        index += 1
        atom = {
            "id": f"a{index}",
            "relation": relation,
            "bearer": bearer,
            "counterparty": counterparty,
            "action": action,
            "conditions": conditions,
            "why": why,
        }
        if negated:
            atom["negated"] = True
        out.append(atom)

    for scope in read:
        add("right", "agent", "harness", {"verb": "read", "object": "file", "scope": scope},
            ["path_inside_room"], "без этого инструмент бесполезен")
    for scope in write:
        add("right", "agent", "harness", {"verb": "write", "object": "file", "scope": scope},
            ["path_inside_room"], "запись объявлена явно")
    for scope in net:
        add("right", "agent", "harness", {"verb": "net", "object": "endpoint", "scope": scope},
            ["endpoint_from_registry"], "сеть объявлена явно")

    add("duty", "harness", "agent",
        {"verb": "limit", "object": "output", "quantity": f"{output_bytes}B"},
        ["output_is_capped"], "контекст модели — бюджет, а не бесплатный ресурс")
    add("duty", "agent", "harness",
        {"verb": "refuse", "object": "request", "scope": ", ".join(refusals)},
        ["reason_from_vocabulary"], "отказ — штатный исход с кодом причины, а не молчание")

    if not write:
        add("duty", "agent", "harness", {"verb": "write", "object": "file", "scope": "**"},
            ["declared_closure"], "запись не объявлена — значит её нет", negated=True)
    if not net:
        add("duty", "agent", "harness", {"verb": "net", "object": "endpoint", "scope": "**"},
            ["declared_closure"], "сеть не объявлена — значит её нет", negated=True)
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


def _kind_for_verb(verb: str) -> str:
    if verb in {"read", "write", "seal"}:
        return "file"
    if verb == "list":
        return "dir"
    if verb == "net":
        return "net"
    return "any"


def _parse_scope(kind: str, raw: str, where: str) -> Scope:
    text = str(raw)
    if not text:
        raise CardShapeError(f"{where}: пустая область ресурса")
    negated = text.startswith("!")
    body = text[1:] if negated else text
    if not body:
        raise CardShapeError(f"{where}: пустая область после '!'")
    if body in {"**", "any"}:
        return Scope(kind=kind, negated=negated, mode="universal", value="**", text=text)
    if body.endswith("/**"):
        root = body[:-3].rstrip("/")
        if not root:
            return Scope(kind=kind, negated=negated, mode="universal", value="**", text=text)
        if any(ch in root for ch in "*?["):
            return Scope(kind=kind, negated=negated, mode="unknown", value=root, text=text)
        return Scope(kind=kind, negated=negated, mode="prefix", value=root, text=text)
    if any(ch in body for ch in "*?["):
        return Scope(kind=kind, negated=negated, mode="unknown", value=body, text=text)
    return Scope(kind=kind, negated=negated, mode="exact", value=body, text=text)


def _policy_scope(rule: dict) -> Scope:
    action = str(rule.get("action") or "")
    kind = _kind_for_verb(action)
    resource = rule.get("resource")
    if resource is None or str(resource) == "":
        # Без ресурса правило не названо; для проверки это универсальная область,
        # но лишнее разрешение всё равно будет поймано как orphan grant.
        return Scope(kind=kind, negated=False, mode="universal", value="**", text="**")
    text = str(resource)
    prefix, sep, rest = text.partition(":")
    if sep and prefix in {"file", "dir", "net"}:
        return _parse_scope(prefix, rest, f"policy.resource:{text}")
    return _parse_scope(kind, text, f"policy.resource:{text}")


def _atom_scope(atom: dict) -> Scope | None:
    action = atom.get("action") or {}
    verb = str(action.get("verb") or "")
    raw = action.get("scope")
    if raw is None:
        return None
    return _parse_scope(_kind_for_verb(verb), str(raw), f"atom:{atom.get('id')}")


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _positive_subset(a: Scope, b: Scope) -> bool | None:
    if a.kind != b.kind:
        return False
    if a.mode == "unknown" or b.mode == "unknown":
        return None
    if b.mode == "universal":
        return True
    if a.mode == "universal":
        return False
    if b.mode == "prefix":
        return _under(a.value, b.value)
    if b.mode == "exact":
        return a.mode == "exact" and a.value == b.value
    return None


def _positive_disjoint(a: Scope, b: Scope) -> bool | None:
    if a.kind != b.kind:
        return True
    if a.mode == "unknown" or b.mode == "unknown":
        return None
    if a.mode == "universal" or b.mode == "universal":
        # Пустых областей в v0 нет: universal пересекается с любой названной.
        return False
    if a.mode == "prefix" and b.mode == "prefix":
        return not (_under(a.value, b.value) or _under(b.value, a.value))
    if a.mode == "prefix":
        return not _under(b.value, a.value)
    if b.mode == "prefix":
        return not _under(a.value, b.value)
    return a.value != b.value


def _without_negation(scope: Scope) -> Scope:
    return replace(scope, negated=False)


def _is_subset(a: Scope, b: Scope) -> bool | None:
    """Доказано ли `a ⊆ b`; None — не удалось доказать."""
    if a.kind != b.kind:
        return False
    if a.mode == "unknown" or b.mode == "unknown":
        return None
    if a.negated and b.negated:
        # !A ⊆ !B  <=>  B ⊆ A
        return _positive_subset(_without_negation(b), _without_negation(a))
    if a.negated:
        return b.mode == "universal" and not b.negated
    if b.negated:
        disjoint = _positive_disjoint(a, _without_negation(b))
        return None if disjoint is None else disjoint
    return _positive_subset(a, b)


def _is_disjoint(a: Scope, b: Scope) -> bool | None:
    """Доказано ли `a ∩ b = ∅`; None — не удалось доказать."""
    if a.kind != b.kind:
        return True
    if a.mode == "unknown" or b.mode == "unknown":
        return None
    if a.negated and b.negated:
        # !A ∩ !B пусто только если A ∪ B универсально.
        if a.mode == "universal" or b.mode == "universal":
            return True
        return None
    if a.negated:
        return _positive_subset(b, _without_negation(a))
    if b.negated:
        return _positive_subset(a, _without_negation(b))
    return _positive_disjoint(a, b)


def _intersects(a: Scope, b: Scope) -> bool | None:
    disjoint = _is_disjoint(a, b)
    return None if disjoint is None else not disjoint


def _same_verb(atom: dict, rule: dict) -> bool:
    return str((atom.get("action") or {}).get("verb") or "") == str(rule.get("action") or "")


def _rights(card: dict) -> list[dict]:
    return [a for a in atoms(card)
            if a.get("relation") == "right" and not a.get("negated")]


def _denials(card: dict) -> list[dict]:
    return [a for a in atoms(card) if a.get("negated")]


def conflicts(card: dict, rules: list[dict] | None = None) -> list[str]:
    """Двусторонние противоречия карточки и политики (S4_POLICY_CONFLICT).

    Ловим три вещи:
      1. policy allow пересекает запрет карточки;
      2. policy deny пересекает право карточки;
      3. policy allow не покрыт ни одним правом карточки (скрытое разрешение).
    """
    rules = load_policy() if rules is None else rules
    tool = card.get("id")
    mine = [rule for rule in rules if rule.get("tool") == tool]
    rights = _rights(card)
    denials = _denials(card)
    out: list[str] = []

    for rule in mine:
        effect = str(rule.get("effect") or "")
        scope = _policy_scope(rule)
        rule_id = rule.get("id", "?")
        verb = str(rule.get("action") or "")
        if effect == "allow":
            conflict = False
            for atom in denials:
                if not _same_verb(atom, rule):
                    continue
                forbidden = _atom_scope(atom)
                if forbidden is None:
                    continue
                hit = _intersects(forbidden, scope)
                if hit is not False:
                    conflict = True
                    out.append(
                        f"S4_POLICY_CONFLICT: {rule_id} разрешает {verb} {scope.text}, "
                        f"а карточка {tool} это запрещает ({atom.get('id')}: {forbidden.text})"
                    )
            if conflict:
                continue
            covered = False
            for atom in rights:
                if not _same_verb(atom, rule):
                    continue
                right = _atom_scope(atom)
                if right is not None and _is_subset(scope, right) is True:
                    covered = True
                    break
            if not covered:
                out.append(
                    f"S4_POLICY_CONFLICT: {rule_id} разрешает {verb} {scope.text}, "
                    f"но карточка {tool} не объявляет такое право (скрытое разрешение)"
                )
        elif effect == "deny":
            for atom in rights:
                if not _same_verb(atom, rule):
                    continue
                right = _atom_scope(atom)
                if right is None:
                    continue
                hit = _intersects(right, scope)
                if hit is not False:
                    out.append(
                        f"S4_POLICY_CONFLICT: {rule_id} запрещает {verb} {scope.text}, "
                        f"а карточка {tool} объявляет это право ({atom.get('id')}: {right.text})"
                    )
    return out


def uncovered(card: dict, rules: list[dict] | None = None) -> list[str]:
    """Права карточки, для которых политика не даёт покрывающего allow."""
    rules = load_policy() if rules is None else rules
    tool = card.get("id")
    mine = [rule for rule in rules
            if rule.get("tool") == tool and rule.get("effect") == "allow"]
    out: list[str] = []
    for atom in _rights(card):
        right = _atom_scope(atom)
        if right is None:
            continue
        covered = False
        for rule in mine:
            if not _same_verb(atom, rule):
                continue
            allow = _policy_scope(rule)
            if _is_subset(right, allow) is True:
                covered = True
                break
        if not covered:
            out.append(
                f"uncovered: {atom.get('id')} {right.text} у инструмента {tool} "
                f"нет покрывающего allow-правила"
            )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="карточка → атомы и сверка с политикой")
    parser.add_argument("--derive", metavar="CARD")
    parser.add_argument("--gaps", metavar="CARD")
    parser.add_argument("--check", metavar="CARD")
    parser.add_argument("--policy", metavar="PATH", default=str(POLICY),
                        help="policy.json (по умолчанию lab/tools/policy.json)")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    target = args.derive or args.gaps or args.check
    if not target:
        parser.print_help()
        return 2
    path = Path(target)
    if not path.exists():
        print(f"[FAIL] нет файла: {path}", file=sys.stderr)
        return 2
    try:
        card = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] S1_SCHEMA: {path}: {exc}", file=sys.stderr)
        return 2
    policy_path = Path(args.policy)
    try:
        rules = load_policy(policy_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] S1_SCHEMA: policy {policy_path}: {exc}", file=sys.stderr)
        return 2

    try:
        if args.derive:
            print(json.dumps({"id": card.get("id"), "atoms": atoms(card)},
                             ensure_ascii=False, indent=1))
            return 0

        if args.gaps:
            items = gaps(card, rules)
            for item in items:
                print(f"[gap] {item}")
            print(f"пробелов: {len(items)}")
            return 0

        bad = conflicts(card, rules)
        missing = uncovered(card, rules)
    except CardShapeError as exc:
        print(f"[FAIL] S1_SCHEMA: {exc}", file=sys.stderr)
        return 2

    for item in bad:
        print(f"[FAIL] {item}")
    for item in missing:
        print(f"[uncovered] {item}")
    if not bad and not missing:
        print(f"[ok] карточка {card.get('id')} покрыта политикой, конфликтов нет "
              f"(правил у инструмента: {len([r for r in rules if r.get('tool') == card.get('id')])})")
        return 0
    return 1 if bad else 3


if __name__ == "__main__":
    raise SystemExit(main())
