"""K9: композиция шагов и цепочка мостов.

Проверки:
- положительный контроль: допустимая цепочка проходит (ok=true, rc=0);
- downstream без доказательства отвергается (K9_CHAIN_UNPROVEN);
- downstream без адреса adjacent отвергается (K9_DOWNSTREAM_MISSING_DEST);
- downstream без метода adjacent отвергается (K9_DOWNSTREAM_MISSING_METHOD);
- утечка «секрет + сеть» отвергается (K9_TAINT_ESCAPE), хотя каждый шаг
  по отдельности не утекает — это контроль T2 из Lean-модели;
- цепочка без adjacent отвергается (K9_ADJACENT_REQUIRED);
- более широкий downstream не делает цепочку недопустимой: он просто недостижим;
- CLI возвращает 0 на допустимой и 3 на отвергнутой декларации.

    python tests/test_chain.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import chain  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((flag, message))


def codes(report: dict) -> list[str]:
    return [problem["code"] for problem in report.get("problems", [])]


def bridge(name: str, destinations: list[str], proven: bool = True,
           methods: list[str] | None = None) -> dict:
    item = {"id": name, "allowed_destinations": destinations, "proven": proven}
    if methods is not None:
        item["allowed_methods"] = methods
    return item


def chain_decl(*, adjacent: dict | None = None, downstream: list[dict] | None = None,
               steps: list[dict] | None = None) -> dict:
    return {
        "id": "chain:test",
        "adjacent": adjacent if adjacent is not None else bridge("adjacent-1", ["allowed.local"]),
        "downstream": downstream if downstream is not None else [
            bridge("downstream-1", ["allowed.local"])
        ],
        "steps": steps if steps is not None else [
            {"id": "read-room", "reads": ["/room/public.txt"], "sends": []},
            {"id": "send", "reads": [], "sends": ["allowed.local"]},
        ],
    }


def main() -> int:
    # 1. Положительный контроль: цепочка допустима.
    report = chain.check_chain(chain_decl())
    check(report["ok"] is True and codes(report) == [], "допустимая цепочка проходит")
    check(report["reachable_through_chain"] == ["allowed.local"],
          f"достижимый адрес назван (наблюдение {report['reachable_through_chain']})")
    check("policy-only" in report["caveat"], "граница проверки названа в отчёте")

    # 2. Downstream без доказательства — отказ.
    report = chain.check_chain(chain_decl(downstream=[
        bridge("downstream-1", ["allowed.local"], proven=False)
    ]))
    check(report["ok"] is False and "K9_CHAIN_UNPROVEN" in codes(report),
          "непроверенный downstream отвергнут (K9_CHAIN_UNPROVEN)")

    # 3. Downstream не пропускает адрес adjacent — отказ.
    report = chain.check_chain(chain_decl(
        adjacent=bridge("adjacent-1", ["allowed.local", "other.local"]),
        downstream=[bridge("downstream-1", ["allowed.local"])],
    ))
    check(report["ok"] is False and "K9_DOWNSTREAM_MISSING_DEST" in codes(report),
          "пропущенный адрес отвергнут (K9_DOWNSTREAM_MISSING_DEST)")

    # 4. Downstream не пропускает метод adjacent — отказ.
    report = chain.check_chain(chain_decl(
        adjacent=bridge("adjacent-1", ["allowed.local"], methods=["GET", "POST"]),
        downstream=[bridge("downstream-1", ["allowed.local"], methods=["GET"])],
    ))
    check(report["ok"] is False and "K9_DOWNSTREAM_MISSING_METHOD" in codes(report),
          "пропущенный метод отвергнут (K9_DOWNSTREAM_MISSING_METHOD)")

    # 5. Контроль T2: по отдельности шаги не утекают, вместе — утекают.
    secret_step = {"id": "read-secret", "reads": ["secret:key"], "sends": []}
    net_step = {"id": "send", "reads": [], "sends": ["allowed.local"]}
    check(chain.step_leaks(secret_step) is False and chain.step_leaks(net_step) is False,
          "по отдельности шаги не утекают (контроль T2)")
    report = chain.check_chain(chain_decl(steps=[secret_step, net_step]))
    check(report["ok"] is False and "K9_TAINT_ESCAPE" in codes(report),
          "композиция секрет+сеть отвергнута (K9_TAINT_ESCAPE)")
    check(report["per_step_leaks"] == [], "пошаговая проверка утечки пуста — глобальная ловит")

    # 6. Нет adjacent — отказ.
    report = chain.check_chain(chain_decl(adjacent={}))
    check(report["ok"] is False and "K9_ADJACENT_REQUIRED" in codes(report),
          "цепочка без adjacent отвергнута (K9_ADJACENT_REQUIRED)")

    # 7. Более широкий downstream не ломает допустимость: он недостижим.
    report = chain.check_chain(chain_decl(downstream=[
        bridge("downstream-1", ["allowed.local", "other.local"])
    ]))
    check(report["ok"] is True, "более широкий downstream не ломает допустимую цепочку")
    check(report["downstream_broader_unreachable"] == ["other.local"],
          "недостижимый адрес назван, а не скрыт")

    # 8. CLI: rc=0 на допустимой, rc=3 на отвергнутой.
    with tempfile.TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.json"
        bad = Path(tmp) / "bad.json"
        good.write_text(json.dumps(chain_decl(), ensure_ascii=False), encoding="utf-8")
        bad.write_text(json.dumps(chain_decl(downstream=[
            bridge("downstream-1", ["allowed.local"], proven=False)
        ]), ensure_ascii=False), encoding="utf-8")

        proc = subprocess.run([sys.executable, str(ROOT / "bin" / "chain.py"), "check", str(good)],
                              capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        check(proc.returncode == 0, f"CLI: допустимая цепочка rc=0 (наблюдение rc={proc.returncode})")
        check(json.loads(proc.stdout)["ok"] is True, "CLI: допустимая цепочка печатает ok=true")

        proc = subprocess.run([sys.executable, str(ROOT / "bin" / "chain.py"), "check", str(bad)],
                              capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        check(proc.returncode == 3, f"CLI: отказ rc=3 (наблюдение rc={proc.returncode})")
        check("K9_CHAIN_UNPROVEN" in proc.stdout, "CLI: код отказа назван")

    for ok, message in RESULTS:
        print(f"[{'ok' if ok else 'FAIL'}] {message}")
    failed = sum(1 for ok, _ in RESULTS if not ok)
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
