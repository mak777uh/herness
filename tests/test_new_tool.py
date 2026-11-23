"""Генератор кандидатов: детерминизм, границы записи и отсутствие активации.

Проверяется без Rust-компиляции: спецификации валидны, 20 кандидатов совпадают
с повторной генерацией, карточки проходят схему, а активная policy/registry не
содержат кандидатов. Исполнение сгенерированного кода — `bin/pilot_generator.py`.

    python tests/test_new_tool.py
"""

from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bin"))

import new_tool  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((flag, message))


def main() -> int:
    authored = sorted((ROOT / "lab" / "pilot" / "specs" / "authored").glob("*.json"))
    heldout = sorted((ROOT / "lab" / "pilot" / "specs" / "heldout").glob("*.json"))
    check(len(authored) == 12, f"authored спецификаций: {len(authored)}")
    check(len(heldout) == 8, f"held-out спецификаций: {len(heldout)}")

    specs = new_tool.collect_specs(ROOT / "lab" / "pilot" / "specs")
    invalid = {spec.get("id"): new_tool.validate_spec(spec) for spec in specs}
    invalid = {key: value for key, value in invalid.items() if value}
    check(not invalid, f"все спецификации валидны: {sorted(invalid)[:3]}")

    first_a = new_tool.load_spec(authored[0])
    left = new_tool.candidate_bytes(first_a)
    right = new_tool.candidate_bytes(first_a)
    check(left == right, "генерация одного spec байт-идентична при повторе")

    missing = [spec["id"] for spec in specs
               if new_tool.check_candidate(spec, new_tool.OUT_ROOT)]
    check(not missing, f"кандидаты совпадают с генерацией: {len(missing)} проблем")

    for spec in specs[:3]:
        card = json.loads((new_tool.OUT_ROOT / spec["id"] / "card.json").read_text(encoding="utf-8"))
        problems = new_tool.card_schema_check(card)
        check(not problems, f"карточка {spec['id']} проходит схему: {problems[:2]}")
        fragment = json.loads((new_tool.OUT_ROOT / spec["id"] / "policy.fragment.json")
                              .read_text(encoding="utf-8"))
        check(fragment.get("merged") is False and fragment.get("tool") == card["id"],
              f"policy fragment {spec['id']} не влит")

    real_import = builtins.__import__

    def without_jsonschema(name, *args, **kwargs):
        if name == "jsonschema" or name.startswith("jsonschema."):
            raise ImportError("controlled missing jsonschema")
        return real_import(name, *args, **kwargs)

    valid_card = json.loads((new_tool.OUT_ROOT / specs[0]["id"] / "card.json").read_text(encoding="utf-8"))
    with patch("builtins.__import__", side_effect=without_jsonschema):
        dependency_problems = new_tool.card_schema_check(valid_card)
    check(len(dependency_problems) == 1 and "обязательная зависимость" in dependency_problems[0],
          f"генератор без jsonschema отвергает карточку без required-only fallback: {dependency_problems}")

    policy = (ROOT / "lab" / "tools" / "policy.json").read_text(encoding="utf-8")
    check("head_cand_" not in policy, "активная policy не содержит кандидатов")
    state = json.loads((ROOT / "lab" / "tools" / "registry.state.json").read_text(encoding="utf-8"))
    check(state.get("active") == [], "registry.active пуст: кандидаты не активированы")

    outside = ROOT / "lab" / "tools"
    code = new_tool.main(["--all", str(ROOT / "lab" / "pilot" / "specs"), "--out", str(outside)])
    check(code == 2, f"запись вне lab/candidates отвергнута: rc={code}")
    check(not (outside / authored[0].stem).exists(), "защищённый путь не изменён")

    mutants = json.loads((ROOT / "lab" / "pilot" / "mutants.json").read_text(encoding="utf-8"))["mutants"]
    critical = sum(1 for item in mutants if item["class"] == "critical")
    functional = sum(1 for item in mutants if item["class"] == "functional")
    check(len(mutants) == 24 and critical == 16 and functional == 8,
          f"мутанты: {len(mutants)} = {critical} critical + {functional} functional")

    prereg = json.loads((ROOT / "lab" / "prereg" / "PILOT-GENERATOR-R1.json")
                        .read_text(encoding="utf-8"))
    check(prereg.get("closed") is True and prereg.get("result", {}).get("evidence"),
          "пилот закрыт и ссылается на evidence")
    check((ROOT / prereg["result"]["evidence"]).exists(), "evidence пилота существует")

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
