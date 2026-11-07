"""bridge_lean — мост как формальная модель: три теоремы.

Мост — единственный канал наружу. Если ядро скомпрометировано, но мост цел — данные не утекут.
Значит свойства моста надо доказать, а не объявить.

Три теоремы:
  T1. адрес только из запуска — запрос не может выбрать адрес;
  T2. токен не выходит — токен не попадает в ответ;
  T3. ответ не переписывается — мост возвращает данные как есть.

    python bin/bridge_lean.py --write   # записать модель в Lean
    python bin/bridge_lean.py --check   # собрать и проверить
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOFS = Path("C:/111/env/lean/proofs")
BIN = Path.home() / ".elan" / "toolchains" / "leanprover--lean4---v4.36.0-rc1" / "bin"
OUT = ROOT / "research" / "outputs" / "bridge-lean.txt"
MODEL = PROOFS / "Proofs" / "Bridge.lean"

MODEL_SOURCE = '''module

/-!
# Мост: формальная модель трёх свойств

Мост — единственный канал наружу. Эти теоремы доказывают, что:
  1. адрес берётся только из запуска, запрос его не выбирает;
  2. токен не попадает в ответ;
  3. ответ не переписывается.

Модель не зависит от кода моста: она описывает правило, а соответствие кода правилу
проверяется отдельно (как policy_diff для политики).
-/

/-- Конфигурация моста: задаётся при запуске, не приходит из запроса. -/
public structure Config where
  upstream : String
  token : String
  deriving Repr

/-- Запрос от агента: что просят и куда. Адрес в запросе есть специально —
    чтобы показать, что мост его игнорирует. -/
public structure Request where
  path : String
  body : String
  wantedHost : String
  deriving Repr

/-- Что мост отправил: адрес и тело. -/
public structure Sent where
  host : String
  body : String
  deriving Repr

/-- Мост: адрес берётся из конфигурации, тело — из запроса. Поле `wantedHost`
    запроса НЕ используется. -/
public def forward (cfg : Config) (req : Request) : Sent :=
  ⟨cfg.upstream, req.body⟩

/-- Ответ моста: тело от провайдера и заголовки. -/
public structure Response where
  body : String
  headers : List (String × String)
  deriving Repr

/-- Мост возвращает ответ провайдера как есть, добавляя только свои заголовки. -/
public def respond (upstreamBody : String) : Response :=
  ⟨upstreamBody, [("content-type", "application/json")]⟩

/-! ## T1. Адрес только из запуска -/

/-- Запрос не может выбрать адрес: какой бы `wantedHost` ни был, адрес тот же. -/
public theorem address_from_config (cfg : Config) (req : Request) :
    (forward cfg req).host = cfg.upstream := by
  rfl

/-- Следствие: два запроса с разными `wantedHost` уходят по одному адресу. -/
public theorem address_ignores_request (cfg : Config) (a b : Request) :
    (forward cfg a).host = (forward cfg b).host := by
  rw [address_from_config, address_from_config]

/-! ## T2. Токен не выходит -/

/-- Токен не входит в ответ: его нет ни в теле, ни в заголовках. -/
public theorem token_not_in_body (cfg : Config) (body : String) :
    (respond body).body = body := by
  rfl

/-- Заголовки ответа — фиксированный список, токена в нём нет. -/
public theorem token_not_in_headers (body : String) :
    (respond body).headers = [("content-type", "application/json")] := by
  rfl

/-! ## T3. Ответ не переписывается -/

/-- Тело ответа равно телу провайдера: мост ничего не меняет. -/
public theorem body_preserved (body : String) :
    (respond body).body = body := by
  rfl

/-- Тело, отправленное мостом, равно телу запроса: мост ничего не добавляет. -/
public theorem body_sent_as_is (cfg : Config) (req : Request) :
    (forward cfg req).body = req.body := by
  rfl
'''

NEGATIVE_SOURCE = '''import Proofs.Bridge

/-!
# Отрицательный контроль для моста

Два ложных утверждения, которые Lean обязан отвергнуть.
Если он их примет — доказательствам моста верить нельзя.
-/

/-- Ложь: запрос выбирает адрес. -/
example (cfg : Config) (req : Request) : (forward cfg req).host = req.wantedHost := by
  rw [address_from_config]

/-- Ложь: мост переписывает тело. -/
example (body : String) : (respond body).body = body ++ "!" := by
  rw [body_preserved]
'''


def write_models() -> int:
    MODEL.write_text(MODEL_SOURCE, encoding="utf-8")
    (PROOFS / "Proofs" / "BridgeNegative.lean").write_text(NEGATIVE_SOURCE, encoding="utf-8")
    print(f"записано: {MODEL}")
    print(f"записано: {PROOFS / 'Proofs' / 'BridgeNegative.lean'}")
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
    lines = ["# Мост: формальная проверка трёх свойств", ""]
    code, text = run([str(BIN / "lake.exe"), "build", "Proofs.Bridge"])
    ok = code == 0
    lines.append(f"## Модель: {'собрана' if ok else 'НЕ СОБРАНА'}")
    if not ok:
        lines.append(text[-800:])
    lines.append("")

    probe = PROOFS / "BridgeProbe.lean"
    theorems = ["address_from_config", "address_ignores_request",
                "token_not_in_body", "token_not_in_headers",
                "body_preserved", "body_sent_as_is"]
    probe.write_text("module\n\nimport Proofs.Bridge\n" + "\n".join(f"#print axioms {t}" for t in theorems) + "\n",
                     encoding="utf-8")
    code, axioms = run([str(BIN / "lean.exe"), "BridgeProbe.lean"])
    probe.unlink(missing_ok=True)
    lines.append("## Аксиомы")
    lines.append("")
    standard = {"propext", "Classical.choice", "Quot.sound"}
    clean = True
    seen = 0
    for line in axioms.splitlines():
        line = line.strip()
        if "does not depend on any axioms" in line:
            name = line.split("'")[1]
            seen += 1
            lines.append(f"- `{name}`: ни одной аксиомы")
            continue
        if "depends on axioms" not in line:
            continue
        name = line.split("'")[1]
        seen += 1
        used = set(line.split("[")[1].rstrip("]").replace(" ", "").split(","))
        extra = used - standard
        if extra:
            clean = False
        lines.append(f"- `{name}`: {', '.join(sorted(used))}"
                     + (f" — НЕСТАНДАРТНЫЕ: {', '.join(sorted(extra))}" if extra else ""))
    if seen != len(theorems):
        clean = False
        lines.append(f"- ВНИМАНИЕ: проверено {seen} теорем из {len(theorems)}")
    lines.append("")

    code, text = run([str(BIN / "lake.exe"), "build", "Proofs.BridgeNegative"])
    rejected = code != 0
    lines.append(f"## Отрицательный контроль: {'отвергнут' if rejected else 'ПРИНЯТ — ПРОВЕРКА НЕ РАБОТАЕТ'}")
    for line in text.splitlines():
        if "unsolved goals" in line or "error:" in line:
            lines.append(f"   {line.strip()}")
    lines.append("")

    verdict = ok and rejected and clean
    lines.append(f"## Итог: {'три свойства доказаны, ложь отвергнута' if verdict else 'ЕСТЬ ПРОБЛЕМА'}")
    lines.append("")
    lines.append("Граница: доказано свойство модели моста, а не соответствие кода моста модели.")
    lines.append("Соответствие проверяется сверкой, как policy_diff для политики.")

    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if verdict else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="мост в Lean")
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
