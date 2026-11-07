"""lean_check — формальная проверка политики посредника в Lean.

Запускает сборку доказательств и отрицательного контроля, пишет артефакт.

    python bin/lean_check.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOFS = Path("C:/111/env/lean/proofs")
BIN = Path.home() / ".elan" / "toolchains" / "leanprover--lean4---v4.36.0-rc1" / "bin"
OUT = ROOT / "research" / "outputs" / "lean-check.txt"

THEOREMS = [
    "deny_beats_allow",
    "deny_means_not_allowed",
    "no_allow_means_denied",
    "empty_policy_denies",
    "mediator_refuses",
    "mediator_performs",
]


def run(args: list[str], env_extra: dict | None = None) -> tuple[int, str]:
    env = {"PATH": f"{BIN};C:/Program Files/Git/cmd;C:/Windows/System32;C:/Windows", "SYSTEMROOT": "C:/Windows",
           "TEMP": str(Path.home() / "AppData" / "Local" / "Temp"),
           "USERPROFILE": str(Path.home()), "HOMEDRIVE": "C:", "HOMEPATH": str(Path.home())[2:]}
    env["LEAN_PATH"] = str(PROOFS / ".lake" / "build" / "lib" / "lean")
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(args, cwd=str(PROOFS), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env=env)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def main() -> int:
    if not BIN.exists():
        print(f"нет Lean: {BIN}")
        return 2
    lines = ["# Формальная проверка политики в Lean", ""]

    code, text = run([str(BIN / "lake.exe"), "build", "Proofs.Policy"])
    ok_proof = code == 0
    lines.append(f"## Доказательства: {'собраны' if ok_proof else 'НЕ СОБРАНЫ'}")
    lines.append("")

    # Аксиомы: только три стандартные.
    probe = PROOFS / "Probe.lean"
    body = "import Proofs.Policy\n" + "\n".join(f"#print axioms {t}" for t in THEOREMS) + "\n"
    probe.write_text(body, encoding="utf-8")
    code, axioms = run([str(BIN / "lean.exe"), "Probe.lean"])
    probe.unlink(missing_ok=True)
    lines.append("## Аксиомы каждой теоремы")
    lines.append("")
    standard = {"propext", "Classical.choice", "Quot.sound"}
    clean = True
    for line in axioms.splitlines():
        line = line.strip()
        if "depends on axioms" not in line:
            continue
        name = line.split("'")[1]
        used = set(line.split("[")[1].rstrip("]").replace(" ", "").split(","))
        extra = used - standard
        if extra:
            clean = False
        lines.append(f"- `{name}`: {', '.join(sorted(used))}{' — НЕСТАНДАРТНЫЕ: ' + ', '.join(sorted(extra)) if extra else ''}")
    lines.append("")

    # Отрицательный контроль: обязан упасть.
    code, text = run([str(BIN / "lake.exe"), "build", "Proofs.Negative"])
    rejected = code != 0
    lines.append(f"## Отрицательный контроль: {'отвергнут' if rejected else 'ПРИНЯТ — ПРОВЕРКА НЕ РАБОТАЕТ'}")
    for line in text.splitlines():
        if "unsolved goals" in line:
            lines.append(f"   {line.strip()}")
    lines.append("")

    verdict = ok_proof and rejected and clean
    lines.append(f"## Итог: {'доказательства приняты, ложь отвергнута' if verdict else 'ЕСТЬ ПРОБЛЕМА'}")
    lines.append("")
    lines.append("Граница: доказано свойство модели политики, а не соответствие Rust-кода модели.")
    lines.append("Соответствие проверяется тестами и сверкой (policy_sync, closure_probe).")

    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
