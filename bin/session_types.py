"""session_types — протокол TOOL/DONE как конечный автомат, три теоремы в Lean.

Шаг 1 из каталога методов. У нас есть протокол TOOL / DONE / BLOCKED / NO-WORK.
Сейчас он проверяется разбором строки, но не проверяется ПОСЛЕДОВАТЕЛЬНОСТЬ.

Что доказываем:
  T1. DONE не может быть первым шагом (нечего завершать);
  T2. после DONE ничего не может быть (прогон закончен);
  T3. из любого состояния достижим DONE или BLOCKED (нет тупика).

    python bin/session_types.py --write
    python bin/session_types.py --check
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOFS = Path("C:/111/env/lean/proofs")
BIN = Path.home() / ".elan" / "toolchains" / "leanprover--lean4---v4.36.0-rc1" / "bin"
OUT = ROOT / "research" / "outputs" / "session-types.txt"
MODEL = PROOFS / "Proofs" / "Session.lean"

MODEL_SOURCE = '''module

/-!
# Протокол агента как конечный автомат

Протокол: `TOOL <имя> <аргумент>` / `DONE <итог>` / `BLOCKED <почему>` / `NO-WORK`.

Состояния: начало, работа, конец.
Переходы: из начала — только TOOL; из работы — TOOL, DONE, BLOCKED; из конца — ничего.

Три теоремы:
  T1. DONE не может быть первым шагом;
  T2. после конца ничего не происходит;
  T3. из любого состояния достижим конец.
-/

/-- Состояние прогона. -/
public inductive State where
  | start
  | working
  | finished
  deriving DecidableEq, Repr

/-- Шаг агента. -/
public inductive Step where
  | tool
  | done
  | blocked
  | noWork
  deriving DecidableEq, Repr

/-- Переход: из состояния по шагу. `none` — запрещённый переход. -/
public def transition (s : State) (step : Step) : Option State :=
  match s, step with
  | State.start, Step.tool => some State.working
  | State.working, Step.tool => some State.working
  | State.working, Step.done => some State.finished
  | State.working, Step.blocked => some State.finished
  | State.working, Step.noWork => some State.finished
  | _, _ => none

/-- Шаг разрешён в состоянии. -/
public def allowed (s : State) (step : Step) : Bool :=
  (transition s step).isSome

/-! ## T1. DONE не может быть первым шагом -/

/-- Из начала нельзя закончить: нечего завершать. -/
public theorem done_not_first : transition State.start Step.done = none := by
  rfl

/-- То же в форме «шаг не разрешён». -/
public theorem done_not_allowed_at_start : allowed State.start Step.done = false := by
  rfl

/-! ## T2. После конца ничего не происходит -/

/-- Из конца нет переходов: прогон закончен. -/
public theorem no_step_after_finish (step : Step) :
    transition State.finished step = none := by
  cases step <;> rfl

/-! ## T3. Из любого состояния достижим конец -/

/-- Из работы всегда можно закончить. -/
public theorem can_finish_from_working :
    transition State.working Step.done = some State.finished := by
  rfl

/-- Из начала можно дойти до конца за два шага. -/
public theorem reachable_from_start :
    transition State.start Step.tool >>= (fun s => transition s Step.done)
      = some State.finished := by
  rfl

/-! ## Примеры -/

/-- TOOL из начала разрешён. -/
example : allowed State.start Step.tool = true := by decide

/-- DONE из начала запрещён. -/
example : allowed State.start Step.done = false := by decide

/-- DONE из работы разрешён. -/
example : allowed State.working Step.done = true := by decide

/-- TOOL после конца запрещён. -/
example : allowed State.finished Step.tool = false := by decide
'''

NEGATIVE_SOURCE = '''import Proofs.Session

/-!
# Отрицательный контроль для протокола

Два ложных утверждения, которые Lean обязан отвергнуть.
-/

/-- Ложь: DONE разрешён из начала. -/
example : allowed State.start Step.done = true := by decide

/-- Ложь: после конца можно сделать шаг. -/
example : transition State.finished Step.tool = some State.working := by
  rw [no_step_after_finish]
  simp
'''


def write_models() -> int:
    MODEL.write_text(MODEL_SOURCE, encoding="utf-8")
    (PROOFS / "Proofs" / "SessionNegative.lean").write_text(NEGATIVE_SOURCE, encoding="utf-8")
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
    lines = ["# Протокол агента: формальная проверка", ""]
    code, text = run([str(BIN / "lake.exe"), "build", "Proofs.Session"])
    ok = code == 0
    lines.append(f"## Модель: {'собрана' if ok else 'НЕ СОБРАНА'}")
    if not ok:
        lines.append(text[-600:])
    lines.append("")

    probe = PROOFS / "SessionProbe.lean"
    theorems = ["done_not_first", "done_not_allowed_at_start",
                "no_step_after_finish", "can_finish_from_working", "reachable_from_start"]
    probe.write_text("module\n\nimport Proofs.Session\n" +
                     "\n".join(f"#print axioms {t}" for t in theorems) + "\n", encoding="utf-8")
    code, axioms = run([str(BIN / "lean.exe"), "SessionProbe.lean"])
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

    code, text = run([str(BIN / "lake.exe"), "build", "Proofs.SessionNegative"])
    rejected = code != 0
    lines.append(f"## Отрицательный контроль: {'отвергнут' if rejected else 'ПРИНЯТ — ПРОВЕРКА НЕ РАБОТАЕТ'}")
    for line in text.splitlines():
        if "error:" in line:
            lines.append(f"   {line.strip()}")
    lines.append("")

    verdict = ok and rejected and clean
    lines.append(f"## Итог: {'пять теорем доказаны, ложь отвергнута' if verdict else 'ЕСТЬ ПРОБЛЕМА'}")
    lines.append("")
    lines.append("Граница: доказан протокол, а не то, что содержимое DONE отвечает задаче.")

    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if verdict else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="протокол агента")
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
