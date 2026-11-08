"""bridge_parts — мост между частями: формальная модель.

Шаг 4 плана. По видению владельца: части взаимозаменяемы, если отношения доказаны.
Мост между двумя ячейками не соединяется, если их пулы законов несовместимы.

Три теоремы:
  T1. несовместимые пулы не соединяются;
  T2. совместимые пулы соединяются;
  T3. соединение требует, чтобы пул принимающей стороны включал пул гостя.

    python bin/bridge_parts.py --write
    python bin/bridge_parts.py --check
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOFS = Path("C:/111/env/lean/proofs")
BIN = Path.home() / ".elan" / "toolchains" / "leanprover--lean4---v4.36.0-rc1" / "bin"
OUT = ROOT / "research" / "outputs" / "bridge-parts.txt"
MODEL = PROOFS / "Proofs" / "Parts.lean"

MODEL_SOURCE = '''module

/-!
# Мост между частями: формальная модель

По видению: части — атомарные ячейки, отношения между ними доказаны, поэтому части
взаимозаменяемы. Мост между двумя ячейками не соединяется, если их пулы законов
несовместимы — не «проверка при соединении», а невозможность соединения.
-/

/-- Ячейка: имя и пул законов (множество правил, которые она принимает). -/
public structure Cell where
  name : String
  laws : List String
  deriving Repr

/-- Пул законов ячейки содержит закон. -/
public def hasLaw (cell : Cell) (law : String) : Bool :=
  cell.laws.contains law

/-- Пул гостя включён в пул хозяина: всё, что принимает гость, принимает и хозяин. -/
public def poolIncluded (guest host : Cell) : Bool :=
  guest.laws.all (fun law => hasLaw host law)

/-- Мост: соединяет две ячейки, если пул гостя включён в пул хозяина.
    Иначе — не соединяет. Это не проверка при соединении, а условие существования моста. -/
public def bridge (guest host : Cell) : Option (String × String) :=
  if poolIncluded guest host then some (guest.name, host.name) else none

/-! ## T1. Несовместимые пулы не соединяются -/

/-- Если у гостя есть закон, которого нет у хозяина, моста нет. -/
public theorem incompatible_no_bridge (guest host : Cell) (law : String)
    (inGuest : hasLaw guest law = true) (notInHost : hasLaw host law = false) :
    bridge guest host = none := by
  unfold bridge
  have notIncluded : poolIncluded guest host = false := by
    unfold poolIncluded hasLaw at *
    apply List.all_eq_false.mpr
    refine ⟨law, ?_, ?_⟩
    · simpa using inGuest
    · simpa using notInHost
  rw [notIncluded]
  rfl

/-! ## T2. Совместимые пулы соединяются -/

/-- Если пул гостя включён в пул хозяина, мост есть. -/
public theorem compatible_bridge (guest host : Cell)
    (h : poolIncluded guest host = true) :
    bridge guest host = some (guest.name, host.name) := by
  unfold bridge
  rw [h]
  rfl

/-! ## T3. Соединение требует включения пула -/

/-- Мост существует только тогда, когда пул гостя включён в пул хозяина. -/
public theorem bridge_implies_inclusion (guest host : Cell)
    (h : bridge guest host ≠ none) :
    poolIncluded guest host = true := by
  unfold bridge at h
  by_cases included : poolIncluded guest host
  · exact included
  · rw [ite_eq_right (by simp [included])] at h
    exact absurd rfl h

/-! ## Пример: две ячейки -/

/-- Хозяин принимает законы A и B. -/
public def host : Cell := ⟨"host", ["A", "B"]⟩

/-- Гость принимает только A. -/
public def guestOk : Cell := ⟨"guest-ok", ["A"]⟩

/-- Гость принимает A и C. -/
public def guestBad : Cell := ⟨"guest-bad", ["A", "C"]⟩

/-- Совместимый гость соединяется. -/
example : bridge guestOk host = some ("guest-ok", "host") := by
  apply compatible_bridge
  unfold poolIncluded guestOk host hasLaw
  decide

/-- Несовместимый гость не соединяется. -/
example : bridge guestBad host = none := by
  apply incompatible_no_bridge guestBad host "C"
  · unfold hasLaw guestBad
    decide
  · unfold hasLaw host
    decide
'''

NEGATIVE_SOURCE = '''import Proofs.Parts

/-!
# Отрицательный контроль для моста частей

Два ложных утверждения, которые Lean обязан отвергнуть.
-/

/-- Ложь: несовместимый гость соединяется. -/
example : bridge guestBad host ≠ none := by
  rw [incompatible_no_bridge guestBad host "C" (by decide) (by decide)]
  simp

/-- Ложь: совместимый гость не соединяется. -/
example : bridge guestOk host = none := by
  rw [compatible_bridge guestOk host (by decide)]
  simp
'''


def write_models() -> int:
    MODEL.write_text(MODEL_SOURCE, encoding="utf-8")
    (PROOFS / "Proofs" / "PartsNegative.lean").write_text(NEGATIVE_SOURCE, encoding="utf-8")
    print(f"записано: {MODEL}")
    return 0


def run(args: list[str]) -> tuple[int, str]:
    env = {
        "PATH": f"{BIN};C:/Program Files/Git/cmd;C:/Windows/System32;C:/Windows",
        "SYSTEMROOT": "C:/Windows",
        "TEMP": str(Path.home() / "AppData" / "Local" / "Temp"),
        "USERPROFILE": str(Path.home()),
        "LEAN_PATH": str(PROOFS / ".lake" / "build" / "lib" / "lean"),
    }
    result = subprocess.run(args, cwd=str(PROOFS), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env=env)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def check() -> int:
    lines = ["# Мост между частями: формальная проверка", ""]
    code, text = run([str(BIN / "lake.exe"), "build", "Proofs.Parts"])
    ok = code == 0
    lines.append(f"## Модель: {'собрана' if ok else 'НЕ СОБРАНА'}")
    if not ok:
        lines.append(text[-800:])
    lines.append("")

    probe = PROOFS / "PartsProbe.lean"
    theorems = ["incompatible_no_bridge", "compatible_bridge", "bridge_implies_inclusion"]
    probe.write_text("module\n\nimport Proofs.Parts\n" +
                     "\n".join(f"#print axioms {t}" for t in theorems) + "\n", encoding="utf-8")
    code, axioms = run([str(BIN / "lean.exe"), "PartsProbe.lean"])
    probe.unlink(missing_ok=True)
    lines.append("## Аксиомы")
    lines.append("")
    standard = {"propext", "Classical.choice", "Quot.sound"}
    clean = True
    for line in axioms.splitlines():
        line = line.strip()
        if "does not depend on any axioms" in line:
            lines.append(f"- `{line.split(chr(39))[1]}`: ни одной аксиомы")
            continue
        if "depends on axioms" not in line:
            continue
        name = line.split("'")[1]
        used = set(line.split("[")[1].rstrip("]").replace(" ", "").split(","))
        extra = used - standard
        if extra:
            clean = False
        lines.append(f"- `{name}`: {', '.join(sorted(used))}"
                     + (f" — НЕСТАНДАРТНЫЕ: {', '.join(sorted(extra))}" if extra else ""))
    lines.append("")

    code, text = run([str(BIN / "lake.exe"), "build", "Proofs.PartsNegative"])
    rejected = code != 0
    lines.append(f"## Отрицательный контроль: {'отвергнут' if rejected else 'ПРИНЯТ — ПРОВЕРКА НЕ РАБОТАЕТ'}")
    for line in text.splitlines():
        if "error:" in line:
            lines.append(f"   {line.strip()}")
    lines.append("")

    verdict = ok and rejected and clean
    lines.append(f"## Итог: {'три теоремы доказаны, ложь отвергнута' if verdict else 'ЕСТЬ ПРОБЛЕМА'}")
    lines.append("")
    lines.append("Граница: доказано свойство модели моста между частями, а не соответствие кода модели.")

    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if verdict else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="мост между частями")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.write:
        return write_models()
    if args.check:
        return check()
    print("укажи --write или --check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
