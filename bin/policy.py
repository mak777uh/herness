"""policy — политика в проверяемой форме (уровень A из flowguard-spec).

Политика отвечает на вопрос: кто, какое действие, над каким ресурсом, при каком условии.
И отвечает так, чтобы это можно было ПРОВЕРИТЬ, а не прочитать.

Четыре проверки:
  1. противоречия — один атом разрешает, другой запрещает то же самое;
  2. неявные разрешения — «разрешено всё, кроме…» запрещено;
  3. циклы делегирования — A разрешает B, B разрешает A;
  4. запрет сильнее разрешения — при конфликте побеждает deny.

    python bin/policy.py --build      # собрать политику из договоров
    python bin/policy.py --check      # проверить
    python bin/policy.py --show read  # показать правила инструмента
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "lab" / "tools" / "policy.json"

# Политика: субъект, действие, ресурс, эффект, уровень.
# Уровень A — доказуемо (политика), B — доказуемо для кода, C — только измеримо.
POLICY_DATA = {
    "version": 1,
    "principle": "запрет сильнее разрешения; неявных разрешений нет; кто не назван — тот не может",
    "rules": [
        # read
        {"id": "read-allow", "tool": "read", "subject": "agent", "action": "read",
         "resource": "file:/mnt/**", "effect": "allow", "level": "A",
         "why": "без чтения инструмент бесполезен"},
        {"id": "read-deny-write", "tool": "read", "subject": "agent", "action": "write",
         "resource": "file:/mnt/**", "effect": "deny", "level": "A",
         "why": "чтение не должно менять то, что читает"},
        {"id": "read-deny-outside", "tool": "read", "subject": "agent", "action": "read",
         "resource": "file:!/mnt/**", "effect": "deny", "level": "A",
         "why": "замыкание объявлено — за его пределами отказ"},
        {"id": "read-deny-net", "tool": "read", "subject": "agent", "action": "net",
         "resource": "net:**", "effect": "deny", "level": "A",
         "why": "чтение файла не требует сети"},
        # search
        {"id": "search-allow", "tool": "search", "subject": "agent", "action": "read",
         "resource": "file:/mnt/**", "effect": "allow", "level": "A",
         "why": "поиск — основной способ найти ответ"},
        {"id": "search-deny-write", "tool": "search", "subject": "agent", "action": "write",
         "resource": "file:/mnt/**", "effect": "deny", "level": "A",
         "why": "поиск ничего не меняет"},
        {"id": "search-deny-net", "tool": "search", "subject": "agent", "action": "net",
         "resource": "net:**", "effect": "deny", "level": "A",
         "why": "поиск не требует сети"},
        # list
        {"id": "list-allow", "tool": "list", "subject": "agent", "action": "list",
         "resource": "dir:/mnt/**", "effect": "allow", "level": "A",
         "why": "без этого агент не знает, что есть"},
        {"id": "list-deny-write", "tool": "list", "subject": "agent", "action": "write",
         "resource": "file:/mnt/**", "effect": "deny", "level": "A",
         "why": "просмотр каталога ничего не меняет"},
        # write
        {"id": "write-allow", "tool": "write", "subject": "agent", "action": "write",
         "resource": "file:/mnt/work/**", "effect": "allow", "level": "A",
         "why": "без этого агент не может оставить результат"},
        {"id": "write-deny-outside", "tool": "write", "subject": "agent", "action": "write",
         "resource": "file:!/mnt/work/**", "effect": "deny", "level": "A",
         "why": "запись вне рабочего каталога — отказ"},
        {"id": "write-deny-net", "tool": "write", "subject": "agent", "action": "net",
         "resource": "net:**", "effect": "deny", "level": "A",
         "why": "запись файла не требует сети"},
        # seal
        {"id": "seal-allow", "tool": "seal", "subject": "agent", "action": "seal",
         "resource": "file:/mnt/work/**", "effect": "allow", "level": "A",
         "why": "отпечаток — способ зафиксировать"},
        {"id": "seal-deny-outside", "tool": "seal", "subject": "agent", "action": "seal",
         "resource": "file:!/mnt/work/**", "effect": "deny", "level": "A",
         "why": "запечатывать можно только своё"},
        # netprobe
        {"id": "netprobe-allow", "tool": "netprobe", "subject": "agent", "action": "net",
         "resource": "net:10.0.2.2:8790", "effect": "allow", "level": "A",
         "why": "единственный разрешённый адрес — мост"},
        {"id": "netprobe-deny-other", "tool": "netprobe", "subject": "agent", "action": "net",
         "resource": "net:!10.0.2.2:8790", "effect": "deny", "level": "A",
         "why": "сеть за мостом — отказ"},
        {"id": "netprobe-deny-fs", "tool": "netprobe", "subject": "agent", "action": "read",
         "resource": "file:/mnt/**", "effect": "deny", "level": "A",
         "why": "проверка сети не читает файлы"},
    ],
    "delegation": [],
}


def load() -> dict:
    if POLICY.exists():
        return json.loads(POLICY.read_text(encoding="utf-8"))
    return POLICY_DATA


def key(rule: dict) -> tuple[str, str, str, str]:
    """Ключ правила включает инструмент: инструменты не пересекаются по ресурсам."""
    return (rule["tool"], rule["subject"], rule["action"], rule["resource"])


def check(policy: dict) -> list[str]:
    """Четыре проверки политики."""
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


def show(tool: str) -> int:
    policy = load()
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="политика инструментов")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--show", metavar="ИНСТРУМЕНТ")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.build:
        POLICY.parent.mkdir(parents=True, exist_ok=True)
        POLICY.write_text(json.dumps(POLICY_DATA, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"записано: {POLICY.relative_to(ROOT)}; правил {len(POLICY_DATA['rules'])}")
        return 0
    if args.show:
        return show(args.show)
    if args.check:
        found = check(load())
        if found:
            print("ПРОБЛЕМЫ:")
            for item in found:
                print("  -", item)
            return 1
        print(f"[ok] политика согласована: {len(load()['rules'])} правил")
        return 0
    print("укажи --build, --check или --show <инструмент>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
