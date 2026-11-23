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

from bin import chain, chain_report  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((flag, message))


def codes(report: dict) -> list[str]:
    return [problem["code"] for problem in report.get("problems", [])]


AUTO = object()
OMIT = object()


def bridge(name: str, destinations: list[str], proven: object = AUTO,
           methods: list[str] | None = None) -> dict:
    # V1: allowed_methods обязателен; default ["GET"] — явный coverage-набор.
    # V6: AUTO заменяется proof-binding только после сборки всей цепочки.
    item = {"id": name, "allowed_destinations": destinations,
            "allowed_methods": ["GET"] if methods is None else methods}
    if proven is not OMIT:
        item["proven"] = proven
    return item


def bind_auto(decl: dict) -> dict:
    subject = chain.subject_sha256(decl)
    bridges = []
    if isinstance(decl.get("adjacent"), dict):
        bridges.append(decl["adjacent"])
    bridges.extend(bridge for bridge in decl.get("downstream", []) if isinstance(bridge, dict))
    for item in bridges:
        if item.get("proven") is AUTO:
            item["proven"] = chain.proof_object(subject)
    return decl


def chain_decl(*, adjacent: dict | None = None, downstream: list[dict] | None = None,
               steps: list[dict] | None = None) -> dict:
    return bind_auto({
        "id": "chain:test",
        "adjacent": adjacent if adjacent is not None else bridge("adjacent-1", ["allowed.local"]),
        "downstream": downstream if downstream is not None else [
            bridge("downstream-1", ["allowed.local"])
        ],
        "steps": steps if steps is not None else [
            {"id": "read-room", "reads": ["/room/public.txt"], "sends": []},
            {"id": "send", "reads": [], "sends": ["allowed.local"]},
        ],
    })


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

    # 9. V1: пустой downstream allowed_methods при непустом adjacent — отказ.
    report = chain.check_chain(chain_decl(
        adjacent=bridge("adjacent-1", ["allowed.local"], methods=["POST"]),
        downstream=[bridge("downstream-1", ["allowed.local"], methods=[])],
    ))
    check(report["ok"] is False and "K9_DOWNSTREAM_MISSING_METHOD" in codes(report),
          "пустой downstream methods при непустом adjacent отвергнут (V1, coverage)")

    # 10. V1: отсутствие allowed_methods — K9_SCHEMA.
    report = chain.check_chain(chain_decl(
        adjacent=bridge("adjacent-1", ["allowed.local"], methods=["GET"]),
        downstream=[{"id": "downstream-1",
                     "allowed_destinations": ["allowed.local"], "proven": True}],
    ))
    check(report["ok"] is False and "K9_SCHEMA" in codes(report),
          "отсутствующее allowed_methods отвергнуто (V1, K9_SCHEMA)")

    # 11. V1: пустой adjacent methods ничего не пересылает — покрытие тривиально.
    report = chain.check_chain(chain_decl(
        adjacent=bridge("adjacent-1", ["allowed.local"], methods=[]),
        downstream=[bridge("downstream-1", ["allowed.local"], methods=["GET"])],
    ))
    check(report["ok"] is True,
          "пустой adjacent methods — покрытие выполнено тривиально (V1)")

    # 12. V6: bare boolean больше не является proof-binding.
    report = chain.check_chain(chain_decl(downstream=[
        bridge("downstream-1", ["allowed.local"], proven=True)
    ]))
    check(report["ok"] is False and "K9_SCHEMA" in codes(report)
          and "K9_CHAIN_UNPROVEN" in codes(report),
          "boolean proven отвергнут схемой и umbrella-кодом (V6)")

    # 13. V6: отсутствие proof поля — отказ.
    report = chain.check_chain(chain_decl(downstream=[
        bridge("downstream-1", ["allowed.local"], proven=OMIT)
    ]))
    check(report["ok"] is False and "K9_CHAIN_UNPROVEN" in codes(report),
          "отсутствующий proof binding отвергнут (V6)")

    # 14. V6: закрытая форма proof object.
    malformed = chain_decl()
    malformed["downstream"][0]["proven"]["extra"] = "not-allowed"
    report = chain.check_chain(malformed)
    check(report["ok"] is False and "K9_PROVEN_BAD_FORMAT" in codes(report),
          "лишнее поле proof object отвергнуто (V6)")

    unknown_kind = chain_decl()
    unknown_kind["downstream"][0]["proven"]["kind"] = "self-declared"
    report = chain.check_chain(unknown_kind)
    check(report["ok"] is False and "K9_PROVEN_BAD_FORMAT" in codes(report),
          "неизвестный proof kind отвергнут (V6)")

    unhashable_kind = chain_decl()
    unhashable_kind["downstream"][0]["proven"]["kind"] = ["lean-instance"]
    report = chain.check_chain(unhashable_kind)
    check(report["ok"] is False and "K9_PROVEN_BAD_FORMAT" in codes(report),
          "нестроковый proof kind отвергнут без исключения (V6)")

    # 15. V6: путь к artifact проверяется до чтения.
    for bad_path in ("../outside.lean", "/etc/passwd", "..\\outside.lean", "a//b.lean"):
        decl = chain_decl()
        decl["downstream"][0]["proven"]["artifact"] = bad_path
        report = chain.check_chain(decl)
        check(report["ok"] is False and "K9_PROVEN_BAD_FORMAT" in codes(report),
              f"небезопасный artifact path отвергнут: {bad_path!r} (V6)")

    # 16. V6: artifact должен существовать.
    missing = chain_decl()
    missing["downstream"][0]["proven"]["artifact"] = "proofs/Proofs/DoesNotExist.lean"
    report = chain.check_chain(missing)
    check(report["ok"] is False and "K9_PROVEN_MISSING_ARTIFACT" in codes(report),
          "отсутствующий artifact отвергнут (V6)")

    # 17. V6: exact-byte hash и subject binding различаются.
    bad_hash = chain_decl()
    bad_hash["downstream"][0]["proven"]["sha256"] = "0" * 64
    report = chain.check_chain(bad_hash)
    check(report["ok"] is False and "K9_PROVEN_HASH_MISMATCH" in codes(report),
          "подмена artifact bytes отвергнута (V6)")

    bad_subject = chain_decl()
    bad_subject["downstream"][0]["proven"]["subject_sha256"] = "0" * 64
    report = chain.check_chain(bad_subject)
    check(report["ok"] is False and "K9_PROVEN_SUBJECT_MISMATCH" in codes(report),
          "подмена chain subject отвергнута (V6)")

    changed_policy = chain_decl()
    changed_policy["downstream"][0]["allowed_destinations"].append("other.local")
    report = chain.check_chain(changed_policy)
    check(report["ok"] is False and "K9_PROVEN_SUBJECT_MISMATCH" in codes(report),
          "изменение policy после привязки делает proof stale (V6)")

    # 18. V6: строгий CLI не принимает duplicate key, float, NaN и unsafe integer.
    with tempfile.TemporaryDirectory() as tmp:
        strict_cases = {
            "duplicate": '{"id":"x","id":"y"}',
            "float": '{"id":1.5}',
            "nan": '{"id":NaN}',
            "unsafe-int": '{"id":9007199254740992}',
        }
        for name, text in strict_cases.items():
            path = Path(tmp) / f"{name}.json"
            path.write_text(text, encoding="utf-8")
            proc = subprocess.run([sys.executable, str(ROOT / "bin" / "chain.py"), "check", str(path)],
                                  capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
            check(proc.returncode == 3 and "K9_SCHEMA" in proc.stdout,
                  f"strict CLI отвергает {name} (V6)")

    # 19. V6/V1: fixture-вердикты не меняются.
    fixture_expectations = {
        "allowed.json": (True, []),
        "taint.json": (False, ["K9_TAINT_ESCAPE"]),
        "methods-empty.json": (False, ["K9_DOWNSTREAM_MISSING_METHOD"]),
        "methods-absent.json": (False, ["K9_SCHEMA"]),
        "methods-ok.json": (True, []),
    }
    for name, (expected_ok, expected_codes) in fixture_expectations.items():
        decl = chain.load_json(ROOT / "lab" / "fixtures" / "chain" / name)
        report = chain.check_chain(decl)
        check(report["ok"] is expected_ok and codes(report) == expected_codes,
              f"fixture {name} сохраняет вердикт (V6/V1)")

    # 20. V6: machine report детерминирован и не устарел.
    first = chain_report.build_report()
    second = chain_report.build_report()
    check(first["ok"] is True and chain_report.render(first) == chain_report.render(second),
          "machine report детерминирован и отражает ожидаемые вердикты (V6)")
    proc = subprocess.run([sys.executable, str(ROOT / "bin" / "chain_report.py"), "--check"],
                          capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    check(proc.returncode == 0, "отслеживаемый machine report не устарел (V6)")

    for ok, message in RESULTS:
        print(f"[{'ok' if ok else 'FAIL'}] {message}")
    failed = sum(1 for ok, _ in RESULTS if not ok)
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
