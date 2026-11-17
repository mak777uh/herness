"""check_policy_parity — один источник политики и совпадение карточки с правилами.

До R8 политика жила дважды: 14 правил в `loopmod.rs` и 19 в `lab/tools/policy.json`, причём
`policy_sync.py` сравнивал только правила без `implied` — то есть 14 из 19. Пять запретов
(в том числе `file:!/mnt/**`) не проверялись вовсе. Теперь источник один: JSON встроен в
бинарь через `include_str!`, а этот гейт проверяет смысл:

  - в Rust нет ручной копии правил;
  - `!` используется только с deny (иначе это неявное разрешение);
  - обязательные запреты на месте (удаление запрета валит гейт);
  - эффекты карточки `head` не шире разрешённых правил;
  - известные запросы дают ожидаемый ответ.

    python bin/check_policy_parity.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOP = ROOT / "core-rs" / "src" / "loopmod.rs"
POLICY = ROOT / "lab" / "tools" / "policy.json"
DRAFT = ROOT / "lab" / "tools" / "drafts" / "head-v1.draft.json"
CODES = ROOT / "lab" / "refusal-codes.json"

INCLUDE = 'include_str!("../../lab/tools/policy.json")'

# Запреты, удаление которых обязано валить гейт: это не «пример», а граница.
REQUIRED_DENIES = {
    ("read", "read", "file:!/mnt/**"),
    ("write", "write", "file:!/mnt/work/**"),
    ("seal", "seal", "file:!/mnt/work/**"),
    ("netprobe", "net", "net:!10.0.2.2:8790"),
    ("head", "read", "file:!/mnt/fixtures/**"),
}


def load_policy(path: Path = POLICY) -> list[dict]:
    return list(json.loads(path.read_text(encoding="utf-8"))["rules"])


def split_scheme(text: str) -> tuple[str, str]:
    for scheme in ("file:", "dir:", "net:"):
        if text.startswith(scheme):
            return scheme, text[len(scheme):]
    return "", text


def resource_matches(pattern: str, resource: str) -> bool:
    p_scheme, p_path = split_scheme(pattern)
    r_scheme, r_path = split_scheme(resource)
    if p_scheme != r_scheme:
        return False
    if any(segment in (".", "..") for segment in r_path.split("/")):
        return False
    negated = p_path.startswith("!")
    if negated:
        p_path = p_path[1:]
    matched = glob(p_path.split("/"), r_path.split("/"))
    return not matched if negated else matched


def glob(pattern: list[str], resource: list[str]) -> bool:
    if not pattern:
        return not resource
    head, rest = pattern[0], pattern[1:]
    if head == "**":
        return glob(rest, resource) or (bool(resource) and glob(pattern, resource[1:]))
    if head == "*":
        return bool(resource) and resource[0] != "" and glob(rest, resource[1:])
    return bool(resource) and resource[0] == head and glob(rest, resource[1:])


def allows(rules: list[dict], tool: str, action: str, resource: str) -> bool:
    allowed = False
    for rule in rules:
        if rule["tool"] != tool or rule["action"] != action:
            continue
        if not resource_matches(rule["resource"], resource):
            continue
        if rule["effect"] == "deny":
            return False
        allowed = True
    return allowed


def check() -> list[str]:
    problems: list[str] = []
    source = LOOP.read_text(encoding="utf-8")
    if INCLUDE not in source:
        problems.append(f"loopmod.rs не встраивает policy.json через {INCLUDE}")
    if "pub const POLICY" in source:
        problems.append("в loopmod.rs осталась ручная копия POLICY: два источника политики")

    rules = load_policy()
    if len(rules) != 23:
        problems.append(f"правил {len(rules)}, ждали 23")
    ids = [rule.get("id") for rule in rules]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        problems.append(f"повторяющиеся id правил: {duplicates}")

    for rule in rules:
        for field in ("id", "tool", "action", "resource", "effect", "level"):
            if field not in rule:
                problems.append(f"правило {rule.get('id', '?')}: нет поля {field}")
        if rule.get("effect") not in ("allow", "deny"):
            problems.append(f"правило {rule.get('id')}: эффект {rule.get('effect')!r}")
        if rule.get("level") not in ("A", "B", "C"):
            problems.append(f"правило {rule.get('id')}: уровень {rule.get('level')!r}")
        path = split_scheme(str(rule.get("resource", "")))[1]
        if path.startswith("!") and rule.get("effect") == "allow":
            problems.append(f"правило {rule.get('id')}: `!` с allow — неявное разрешение")

    denies = {(rule["tool"], rule["action"], rule["resource"])
              for rule in rules if rule.get("effect") == "deny"}
    for missing in sorted(REQUIRED_DENIES - denies):
        problems.append(f"удалён обязательный запрет: {missing}")

    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    effects = draft["effects"]
    if effects["fs_read"] != [{"root_ref": "room:input", "segments": ["fixtures"]}]:
        problems.append(f"fs_read карточки head изменился: {effects['fs_read']}")
    for key in ("fs_list", "fs_write", "bridges"):
        if effects[key]:
            problems.append(f"у карточки head непустой {key}: {effects[key]}")
    if effects["process_spawn"] is not False:
        problems.append("у карточки head process_spawn не false")

    # Provenance — не украшение: digest'ы обязаны соответствовать точным байтам файлов.
    # Иначе карточка ссылается на другую политику/схему, чем та, что проверяется.
    provenance_sources = {
        "lawset_digest": ROOT / "docs" / "CONSTITUTION-v0-2026-11-16.md",
        "policy_digest": POLICY,
        "room_profile_digest": ROOT / "lab" / "tools" / "room-profile-v0.json",
        "schema_digest": ROOT / "lab" / "tools" / "tool-card-v1.schema.json",
    }
    for name, path in provenance_sources.items():
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if draft["provenance"].get(name) != actual:
            problems.append(f"provenance {name} не совпадает с {path.name}: "
                            f"{draft['provenance'].get(name)} != {actual}")

    # Разрешённое карточке должно быть разрешено политикой, и ничего сверх.
    if not allows(rules, "head", "read", "file:/mnt/fixtures/head-slice.txt"):
        problems.append("политика не разрешает head читать fixtures")
    for resource in ("file:/mnt/work/x", "file:/etc/passwd", "file:/mnt/fixtures/../work/x"):
        if allows(rules, "head", "read", resource):
            problems.append(f"head читает вне fixtures: {resource}")
    for action, resource in (("write", "file:/mnt/fixtures/x"),
                             ("write", "file:/mnt/work/x"),
                             ("net", "net:10.0.2.2:8790")):
        if allows(rules, "head", action, resource):
            problems.append(f"card с пустым {action} разрешён политикой: {resource}")

    # Известные ответы: положительные и отрицательные контроли вместе.
    cases = [
        (("read", "read", "file:/mnt/a.md"), True),
        (("read", "read", "file:/etc/passwd"), False),
        (("read", "read", "file:/mntx/a.md"), False),
        (("write", "write", "file:/mnt/work/new.md"), True),
        (("write", "write", "file:/mnt/work2/x"), False),
        (("write", "write", "file:/mnt/work/../work2/x"), False),
        (("list", "list", "dir:/mnt/work"), True),
        (("list", "list", "dir:/mntx"), False),
        (("net", "net", "net:10.0.2.2:8790"), True),
        (("net", "net", "net:1.1.1.1:53"), False),
        (("netprobe", "net", "net:10.0.2.2:8790"), True),
        (("netprobe", "net", "net:1.1.1.1:53"), False),
        (("head", "read", "file:/mnt/fixtures/head-slice.txt"), True),
        (("head", "read", "file:/mnt/fixtures/../work/x"), False),
    ]
    for (tool, action, resource), expected in cases:
        actual = allows(rules, tool, action, resource)
        if actual != expected:
            problems.append(f"{tool}/{action} {resource}: политика дала {actual}, ждали {expected}")

    codes = {item["code"] for item in json.loads(CODES.read_text(encoding="utf-8"))["codes"]}
    for code in ("S13_TOOL_INACTIVE", "S14_ALREADY_EXISTS"):
        if code not in codes:
            problems.append(f"словарь отказов без {code}")

    # Полномочие — тоже один источник: снимок описаний + события + производный state.
    # Если state.json отстал или в registry.jsonl появился status, гейт обязан это увидеть.
    sys.path.insert(0, str(ROOT))
    try:
        from bin import registry_state

        problems += registry_state.check_files()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"registry_state недоступен: {type(exc).__name__}: {exc}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="паритет политики, карточки и словаря")
    parser.add_argument("--check", action="store_true", help="проверить (по умолчанию)")
    parser.parse_args(argv)
    problems = check()
    for problem in problems:
        print(f"[FAIL] {problem}")
    if problems:
        print(f"\nпроблем: {len(problems)}")
        return 1
    print("[ok] политика: один источник, 23 правила, карточка head не шире политики")
    return 0


if __name__ == "__main__":
    sys.exit(main())
