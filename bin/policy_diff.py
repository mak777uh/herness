"""policy_diff — сверка политики в Rust и в Lean на конечном множестве запросов.

Обе реализации — чистые функции над списком правил. Значит их можно сравнить на
запросах, которые модель различает. Это НЕ доказательство равенства функций: Lean-модель
умеет только точное совпадение строк, поэтому в сверку берутся только литеральные правила
(без `*`, `**`, `!`). Шаблоны и дополнения проверяются `check_policy_parity.py` и
Rust-тестами; здесь они были бы сравнением разных моделей, а не кода.

Модель сравнения берётся буквально из Rust (`policy_allows` + `resource_matches`), а не
переписывается «как кажется правильным» — иначе сверка сравнивала бы два мнения.

    python bin/policy_diff.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "lab" / "tools" / "policy.json"
OUT = ROOT / "research" / "outputs" / "policy-diff.txt"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from bin.lean_paths import proofs_dir, lean_bin  # noqa: E402
PROOFS = proofs_dir()
BIN = lean_bin()

SCHEMES = ("file:", "dir:", "net:")


def split_scheme(text: str) -> tuple[str, str]:
    for scheme in SCHEMES:
        if text.startswith(scheme):
            return scheme, text[len(scheme):]
    return "", text


def resource_matches(pattern: str, resource: str) -> bool:
    """Дословный перенос `resource_matches` из core-rs/src/loopmod.rs (после R8)."""
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


def policy_allows(rules: list[dict], tool: str, action: str, resource: str) -> bool:
    """Дословный перенос `policy_allows` из core-rs/src/loopmod.rs."""
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


def exact_rules(rules: list[dict]) -> list[dict]:
    """Только правила, которые Lean-модель умеет сравнивать: точные строки."""
    out = []
    for rule in rules:
        if rule.get("implied"):
            continue
        path = split_scheme(rule["resource"])[1]
        if "*" in path or path.startswith("!"):
            continue
        out.append(rule)
    return out


def queries(rules: list[dict]) -> list[tuple[str, str, str]]:
    """Запросы к точным правилам плюс граничные, где обе модели обязаны отказать."""
    seen: list[tuple[str, str, str]] = []
    for rule in exact_rules(rules):
        key = (rule["tool"], rule["action"], rule["resource"])
        if key not in seen:
            seen.append(key)
    seen += [
        ("read", "read", "file:/etc/passwd"),
        ("net", "net", "net:10.0.2.2:8790"),
        ("net", "net", "net:1.1.1.1:53"),
        ("write", "write", "file:/mnt/work/x.md"),
        ("read", "read", "file:/mnt/work/x.md"),
        ("list", "list", "dir:/mnt/work"),
    ]
    return seen


def lean_rules(rules: list[dict]) -> str:
    """Политика из policy.json в форме Lean: только точные правила."""
    items = []
    for rule in exact_rules(rules):
        effect = "Effect.allow" if rule["effect"] == "allow" else "Effect.deny"
        items.append(
            f'  ⟨"{rule["tool"]}", "{rule["action"]}", "{rule["resource"]}", {effect}⟩'
        )
    return "def filePolicy : Policy :=\n  [\n" + ",\n".join(items) + "\n  ]\n"


def lean_values(rules: list[dict], queries_: list[tuple[str, str, str]]) -> list[bool]:
    """Спрашиваем Lean на тех же запросах и на той же политике через #eval."""
    lines = ["import Proofs.Policy", "", "open Proofs.Policy", "", lean_rules(rules)]
    for tool, action, resource in queries_:
        lines.append(f'#eval policyAllows filePolicy "{tool}" "{action}" "{resource}"')
    probe = PROOFS / "Probe.lean"
    probe.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env = {
        "PATH": f"{BIN};C:/Program Files/Git/cmd;C:/Windows/System32;C:/Windows",
        "SYSTEMROOT": "C:/Windows",
        "TEMP": str(Path.home() / "AppData" / "Local" / "Temp"),
        "USERPROFILE": str(Path.home()),
        "LEAN_PATH": str(PROOFS / ".lake" / "build" / "lib" / "lean"),
    }
    try:
        result = subprocess.run([str(BIN / "lean.exe"), "Probe.lean"], cwd=str(PROOFS),
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", env=env)
    finally:
        probe.unlink(missing_ok=True)
    out = (result.stdout or "") + (result.stderr or "")
    return [line.strip() == "true" for line in out.splitlines() if line.strip() in ("true", "false")]


def main() -> int:
    data = json.loads(POLICY.read_text(encoding="utf-8"))
    rules = data["rules"]
    qs = queries(rules)
    lines = ["# Сверка политики: Rust и Lean (только точные правила)", ""]
    lines.append(f"точных правил: {len(exact_rules(rules))} из {len(rules)}")
    lines.append(f"запросов: {len(qs)}")
    lines.append("")

    if not (BIN / "lean.exe").exists():
        lines.append(f"Lean недоступен: {BIN / 'lean.exe'} — сверка не сделана (это N/A, не зелёный)")
        OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 2

    values = lean_values(rules, qs)
    if len(values) != len(qs):
        lines.append(f"Lean вернул {len(values)} значений вместо {len(qs)} — сверка не сделана")
        OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 2

    lines.append("| инструмент | действие | ресурс | Rust | Lean | совпало |")
    lines.append("|---|---|---|---|---|---|")
    same = 0
    for (tool, action, resource), lean_value in zip(qs, values):
        rust_value = policy_allows(rules, tool, action, resource)
        match = rust_value == lean_value
        same += 1 if match else 0
        lines.append(f"| {tool} | {action} | {resource} | {rust_value} | {lean_value} | {'да' if match else 'НЕТ'} |")

    lines += [
        "",
        f"совпало: {same} из {len(qs)}",
        "",
        "# Что это доказывает: на точных (литеральных) правилах обе реализации дают одно",
        "# и то же на конечном множестве запросов.",
        "",
        "# Что это НЕ доказывает и почему: Lean-модель сравнивает ресурс точно и не умеет",
        "# `**`, `*` или `!`. Поэтому шаблонные правила сюда не входят, и это не доказательство",
        "# равенства функций. Шаблоны и дополнения проверяются Rust-тестами и",
        "# `bin/check_policy_parity.py`; теоремы Lean доказывают свойства логики",
        "# (запрет сильнее разрешения, нет неявных разрешений).",
    ]
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if same == len(qs) else 1


if __name__ == "__main__":
    sys.exit(main())
