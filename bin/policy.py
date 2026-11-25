"""policy — единственный читатель canonical lab/tools/policy.json.

Политика отвечает на вопрос: кто, какое действие, над каким ресурсом, при каком условии.
И отвечает так, чтобы это можно было ПРОВЕРИТЬ, а не прочитать.

Пять проверок:
  1. противоречия — один атом разрешает, другой запрещает то же самое;
  2. неявные разрешения — «разрешено всё, кроме…» запрещено;
  3. циклы делегирования — A разрешает B, B разрешает A;
  4. запрет сильнее разрешения — при конфликте побеждает deny;
  5. уровень каждого правила обязан быть A/B/C.

Canonical missing/malformed/empty/invalid — PolicyDataError. Embedded fallback и
build/overwrite пути отсутствуют: source of truth только lab/tools/policy.json.

    python bin/policy.py --root <checkout> --check
    python bin/policy.py --root <checkout> --show read
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "lab" / "tools" / "policy.json"


class PolicyDataError(Exception):
    """Canonical policy отсутствует, не читается или имеет неверную структуру."""


def _policy_path(root: Path | None) -> Path:
    if root is None:
        return POLICY
    return Path(root).resolve() / "lab" / "tools" / "policy.json"


def _invalid(detail: str) -> None:
    raise PolicyDataError(f"invalid canonical policy: {detail}")


def _validate_structure(data: object) -> dict:
    if not isinstance(data, dict):
        _invalid("top-level must be an object")

    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        _invalid(f"unsupported version {version!r}")

    principle = data.get("principle")
    if not isinstance(principle, str) or not principle.strip():
        _invalid("principle must be a non-empty string")

    rules = data.get("rules")
    if not isinstance(rules, list):
        _invalid("rules must be a list")
    if not rules:
        raise PolicyDataError("empty canonical policy: rules must not be empty")

    required = ("id", "tool", "subject", "action", "resource", "effect", "level", "why")
    seen_ids: set[str] = set()
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            _invalid(f"rule {index} must be an object")
        for field in required:
            value = rule.get(field)
            if not isinstance(value, str) or not value.strip():
                _invalid(f"rule {index} field {field!r} must be a non-empty string")
        rule_id = rule["id"]
        if rule_id in seen_ids:
            _invalid(f"duplicate rule id {rule_id!r}")
        seen_ids.add(rule_id)
        if rule["effect"] not in ("allow", "deny"):
            _invalid(f"rule {rule_id!r} has unknown effect {rule['effect']!r}")
        if rule["level"] not in ("A", "B", "C"):
            _invalid(f"rule {rule_id!r} has unknown level {rule['level']!r}")
        if "implied" in rule and not isinstance(rule["implied"], bool):
            _invalid(f"rule {rule_id!r} field 'implied' must be boolean")

    delegation = data.get("delegation")
    if not isinstance(delegation, list):
        _invalid("delegation must be a list")
    for index, edge in enumerate(delegation):
        if not isinstance(edge, dict):
            _invalid(f"delegation {index} must be an object")
        for field in ("from", "to"):
            value = edge.get(field)
            if not isinstance(value, str) or not value.strip():
                _invalid(f"delegation {index} field {field!r} must be a non-empty string")

    return data


def load(root: Path | None = None) -> dict:
    """Прочитать и структурно проверить canonical policy явно переданного root.

    Никакого embedded fallback: отсутствие файла, ошибка чтения/JSON или неверная
    структура дают PolicyDataError. Возвращённый dict далее проходит semantic check().
    """
    path = _policy_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PolicyDataError(f"missing canonical policy: {path}") from exc
    except (OSError, UnicodeError) as exc:
        raise PolicyDataError(f"unreadable canonical policy: {path}: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PolicyDataError(f"malformed canonical policy: {path}: {exc.msg}") from exc
    return _validate_structure(data)


def key(rule: dict) -> tuple[str, str, str, str]:
    """Ключ правила включает инструмент: инструменты не пересекаются по ресурсам."""
    return (rule["tool"], rule["subject"], rule["action"], rule["resource"])


def check(policy: dict) -> list[str]:
    """Пять проверок политики; структурная валидация выполняется в load()."""
    problems: list[str] = []
    rules = policy.get("rules") or []

    # 1. Противоречия: одинаковые (субъект, действие, ресурс) с разными эффектами.
    seen: dict[tuple[str, str, str], str] = {}
    for rule in rules:
        k = key(rule)
        effect = rule.get("effect")
        if effect not in ("allow", "deny"):
            problems.append(f"{rule.get('id')}: эффект {effect} не allow и не deny")
        if k in seen and seen[k] != effect:
            problems.append(f"{rule.get('id')}: противоречие с правилом на тот же ресурс ({seen[k]} против {effect})")
        seen[k] = effect

    # 2. Неявные разрешения: ресурс вида «всё, кроме» с эффектом allow.
    for rule in rules:
        resource = rule.get("resource", "")
        if "!" in resource and rule.get("effect") == "allow":
            problems.append(f"{rule.get('id')}: неявное разрешение — «всё, кроме» с эффектом allow")
        if resource.endswith("**") and resource.count("/") == 0 and rule.get("effect") == "allow":
            problems.append(f"{rule.get('id')}: слишком широкое разрешение {resource}")

    # 3. Циклы делегирования.
    edges = policy.get("delegation") or []
    graph: dict[str, set[str]] = {}
    for edge in edges:
        graph.setdefault(edge["from"], set()).add(edge["to"])
    for start in graph:
        stack, visited = [start], set()
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            for nxt in graph.get(node, ()):
                if nxt == start:
                    problems.append(f"цикл делегирования через {start}")
                    stack = []
                    break
                stack.append(nxt)

    # 4. Запрет сильнее разрешения: если на один ресурс есть и allow, и deny — deny обязан быть.
    by_resource: dict[tuple[str, str, str], set[str]] = {}
    for rule in rules:
        by_resource.setdefault(key(rule), set()).add(rule["effect"])
    for k, effects in by_resource.items():
        if "allow" in effects and "deny" in effects:
            problems.append(f"на {k} есть и allow, и deny — нужен явный приоритет")

    # 5. Уровень обязан быть указан.
    for rule in rules:
        if rule.get("level") not in ("A", "B", "C"):
            problems.append(f"{rule.get('id')}: уровень {rule.get('level')} не A/B/C")

    return problems


def show(tool: str, root: Path | None = None) -> int:
    try:
        policy = load(root)
    except PolicyDataError as exc:
        print(f"[FAIL] политика: {exc}", file=sys.stderr)
        return 1
    rules = [rule for rule in policy["rules"] if rule["tool"] == tool]
    if not rules:
        print(f"нет правил для {tool}", file=sys.stderr)
        return 2
    print(f"# Политика: {tool} (версия {policy['version']})")
    print(f"\n{policy['principle']}\n")
    print("| правило | субъект | действие | ресурс | эффект | уровень |")
    print("|---|---|---|---|---|---|")
    for rule in rules:
        print(f"| {rule['id']} | {rule['subject']} | {rule['action']} | {rule['resource']} | {rule['effect']} | {rule['level']} |")
    return 0


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="политика инструментов")
    parser.add_argument("--root", type=Path, default=root,
                        help="checkout с lab/tools/policy.json (по умолчанию этот репозиторий)")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--show", metavar="ИНСТРУМЕНТ")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.show:
        return show(args.show, args.root)
    if args.check:
        try:
            policy = load(args.root)
        except PolicyDataError as exc:
            print(f"[FAIL] политика: {exc}", file=sys.stderr)
            return 1
        found = check(policy)
        if found:
            print("ПРОБЛЕМЫ:")
            for item in found:
                print("  -", item)
            return 1
        print(f"[ok] политика согласована: {len(policy['rules'])} правил")
        return 0
    print("укажи --check или --show <инструмент>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
