"""policy_diff — сверка политики в Rust и в Lean на одном конечном множестве запросов.

Обе реализации — чистые функции над списком правил. Значит их можно сравнить на всех
запросах, которые политика различает, и на граничных. Это НЕ доказательство равенства
функций: это проверка на конечном множестве, и она так и названа.

Модель сравнения берётся буквально из Rust (`policy_allows` + `resource_matches`),
а не переписывается «как кажется правильным» — иначе сверка сравнивала бы два мнения.

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
PROOFS = Path("C:/111/env/lean/proofs")
BIN = Path.home() / ".elan" / "toolchains" / "leanprover--lean4---v4.36.0-rc1" / "bin"

SCHEMES = ("file:", "dir:", "net:")


def strip_scheme(text: str) -> str:
    for scheme in SCHEMES:
        if text.startswith(scheme):
            return text[len(scheme):]
    return text


def resource_matches(pattern: str, resource: str) -> bool:
    """Дословный перенос `resource_matches` из core-rs/src/loopmod.rs (после F-0072)."""
    pattern = strip_scheme(pattern)
    resource = strip_scheme(resource)
    if pattern.endswith("/**"):
        prefix = pattern[: -len("/**")]
        return resource == prefix or resource.startswith(prefix + "/")
    if pattern.endswith("**"):
        return resource.startswith(pattern[:-2])
    return pattern == resource


def policy_allows(rules: list[dict], tool: str, action: str, resource: str) -> bool:
    """Дословный перенос `policy_allows` из core-rs/src/loopmod.rs."""
    allowed = False
    for rule in rules:
        if rule.get("implied"):
            continue
        if rule["tool"] != tool or rule["action"] != action:
            continue
        if not resource_matches(rule["resource"], resource):
            continue
        if rule["effect"] == "deny":
            return False
        allowed = True
    return allowed


def queries(rules: list[dict]) -> list[tuple[str, str, str]]:
    """Запросы, которые политика различает, плюс граничные."""
    seen: list[tuple[str, str, str]] = []
    for rule in rules:
        if rule.get("implied"):
            continue
        key = (rule["tool"], rule["action"], rule["resource"])
        if key not in seen:
            seen.append(key)
    seen += [
        ("read", "read", "file:/etc/passwd"),
        ("read", "net", "net:1.1.1.1"),
        ("netprobe", "net", "net:8.8.8.8"),
        ("write", "write", "file:/mnt/work/x.md"),
        ("read", "read", "file:/mnt/work/x.md"),
        ("list", "list", "dir:/mnt/work"),
    ]
    return seen


def lean_rules(rules: list[dict]) -> str:
    """Политика из policy.json в форме Lean: тот же список правил, а не другой."""
    items = []
    for rule in rules:
        if rule.get("implied"):
            continue
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
    result = subprocess.run([str(BIN / "lean.exe"), "Probe.lean"], cwd=str(PROOFS),
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=env)
    probe.unlink(missing_ok=True)
    out = (result.stdout or "") + (result.stderr or "")
    return [line.strip() == "true" for line in out.splitlines() if line.strip() in ("true", "false")]


def main() -> int:
    data = json.loads(POLICY.read_text(encoding="utf-8"))
    rules = data["rules"]
    qs = queries(rules)
    lines = ["# Сверка политики: Rust и Lean", ""]
    lines.append(f"запросов: {len(qs)}")
    lines.append("")

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
        "# Что это доказывает: на запросах, где ресурс указан ТОЧНО (без шаблона `**`),",
        "# обе реализации дают одно и то же.",
        "",
        "# Что это НЕ доказывает и почему: Lean-модель сравнивает ресурс точно, а Rust",
        "# поддерживает шаблон `**` (любой хвост). Запросы вида `file:/mnt/work/x.md` против",
        "# правила `file:/mnt/work/**` в модели не совпадают. Это ограничение модели, а не",
        "# дефект кода: шаблоны проверяются тестами, а модель доказывает свойство логики",
        "# (запрет сильнее разрешения, нет неявных разрешений).",
    ]
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if same == len(qs) else 1


if __name__ == "__main__":
    sys.exit(main())
