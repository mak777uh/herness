"""Карточки: legacy v0 в archive, canonical v1, jsonschema и смысловые мутанты."""

from __future__ import annotations

import builtins
import copy
import json
import pathlib
import sys
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import check_policy_parity, tool_card  # noqa: E402

RESULTS: list[tuple[bool, str]] = []
LEGACY = json.loads((ROOT / "lab" / "tools" / "archive" / "head_legacy.json").read_text(encoding="utf-8"))
CARD = json.loads((ROOT / "lab" / "tools" / "cards" / "head.json").read_text(encoding="utf-8"))


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def broken(base: dict, mutator) -> dict:
    card = copy.deepcopy(base)
    mutator(card)
    return card


def rejects(base: dict, mutator, needle: str, message: str) -> None:
    issues = tool_card.validate(broken(base, mutator))
    check(any(needle in issue for issue in issues), f"{message}: {issues}")


def main() -> int:
    # Legacy v0 остаётся исторически валидным, но не активируемым.
    check(tool_card.validate(LEGACY) == [], "валидная архивная legacy карточка проходит historical validate")
    rejects(LEGACY, lambda c: c["closure"]["fs"].__setitem__("read", ["/etc/**"]),
            "за пределы комнаты", "legacy чтение вне /mnt отвергнуто")
    rejects(LEGACY, lambda c: c["closure"].__setitem__("net", ["https://example.com"]),
            "сеть", "legacy сеть отвергнута")
    rejects(LEGACY, lambda c: c.__setitem__(
        "examples", [e for e in c["examples"] if "отказ" not in e["expect"].lower()]),
        "нет примера с отказом", "legacy пример без отказа отвергнут")
    rejects(LEGACY, lambda c: c.__setitem__("refusals", ["NOPE_CODE"]),
            "нет в словаре", "legacy неизвестный код отвергнут")
    rejects(LEGACY, lambda c: c.__setitem__("purpose", "быстро вернуть первые строки файла."),
            "непроверяемое слово", "legacy «быстро» отвергнуто")
    rejects(LEGACY, lambda c: c["closure"]["fs"].__setitem__("write", ["/mnt/**"]),
            "запись только внутрь", "legacy запись вне /mnt/work отвергнута")
    legacy_text = tool_card.render(LEGACY)
    check(0 < len(legacy_text) <= 1600 and "S6_CLOSURE_BREACH" in legacy_text and "пример" in legacy_text,
          f"legacy рендер сохраняет отказы/примеры и лимит: {len(legacy_text)} символов")
    legacy_activation = tool_card.validate_activation(LEGACY)
    check(any("superseded" in issue for issue in legacy_activation),
          f"legacy activation отклонён: {legacy_activation}")

    # Canonical v1: pinned jsonschema + смысл + отдельный activation gate.
    check(tool_card.validate(CARD) == [], "валидная canonical tool-card-v1 проходит")
    check(tool_card.validate_activation(CARD) == [], "canonical tool-card-v1 activation ok")

    rejects(CARD, lambda c: c.__setitem__("unexpected", True),
            "unexpected", "jsonschema unknown field отвергнут")
    rejects(CARD, lambda c: c["limits"].__setitem__("wall_ms", "2000"),
            "jsonschema limits/wall_ms", "jsonschema wrong type отвергнут")
    rejects(CARD, lambda c: c["effects"].__setitem__("process_spawn", True),
            "jsonschema effects/process_spawn", "jsonschema wrong const отвергнут")
    rejects(CARD, lambda c: c["provenance"].__setitem__("policy_digest", "sha256:abc"),
            "jsonschema provenance/policy_digest", "jsonschema malformed digest отвергнут")
    rejects(CARD, lambda c: c["provenance"].__setitem__("policy_digest", "sha256:" + "0" * 64),
            "provenance policy_digest", "semantic bad digest отвергнут")
    rejects(CARD, lambda c: c["effects"].__setitem__(
        "fs_write", [{"root_ref": "room:work", "segments": ["x"]}]),
        "effects.fs_write", "semantic forbidden write effect отвергнут")
    rejects(CARD, lambda c: c["effects"]["fs_read"][0].__setitem__("segments", ["fixtures", ".."]),
            "небезопасные segments", "semantic traversal effect отвергнут")
    rejects(CARD, lambda c: c["template"].__setitem__("id", "directory_read_stream"),
            "template.id", "kind=file_read требует file_read_stream")
    rejects(CARD, lambda c: c.__setitem__("purpose", "Быстро прочитать файл."),
            "непроверяемое слово", "v1 «быстро» отвергнуто")
    rejects(CARD, lambda c: c["refusals"].__setitem__(0, "NOPE_CODE"),
            "jsonschema refusals/0", "v1 закрытый словарь refusals")

    def remove_refusal_examples(card: dict) -> None:
        for example in card["examples"]:
            example["expected"] = {"outcome": "ok", "assertions": ["synthetic"]}

    rejects(CARD, remove_refusal_examples,
            "нет примера с отказом", "v1 exemplars без refusal отвергнуты")
    rejects(CARD, lambda c: c["examples"][1]["expected"].__setitem__("refusal", "S14_ALREADY_EXISTS"),
            "не объявлен в refusals", "v1 refusal exemplar вне объявленных кодов отвергнут")
    rejects(CARD, lambda c: c.__setitem__("schema_version", "tool-card-v2"),
            "schema_version", "неизвестная schema_version не падает в legacy")

    # Принудительно убираем импорт jsonschema: required-only fallback недопустим.
    real_import = builtins.__import__

    def without_jsonschema(name, *args, **kwargs):
        if name == "jsonschema" or name.startswith("jsonschema."):
            raise ImportError("controlled missing jsonschema")
        return real_import(name, *args, **kwargs)

    no_schema_card = broken(CARD, lambda c: c.__setitem__("unexpected", True))
    with patch("builtins.__import__", side_effect=without_jsonschema):
        missing_dependency = tool_card.validate(no_schema_card)
    check(len(missing_dependency) == 1
          and "jsonschema" in missing_dependency[0]
          and "обязательная зависимость" in missing_dependency[0]
          and "нет полей" not in missing_dependency[0],
          f"отсутствие jsonschema — явная ошибка без required-only fallback: {missing_dependency}")

    with patch.object(tool_card, "validate", return_value=["controlled jsonschema rejection"]):
        parity_problems = check_policy_parity.check()
    check(any("controlled jsonschema rejection" in problem for problem in parity_problems),
          f"check_policy_parity проводит отказ общего v1 validator: {parity_problems}")

    text = tool_card.render(CARD)
    check("S6_CLOSURE_BREACH" in text and "пример" in text and "room:input/fixtures" in text,
          f"v1 рендер содержит effects, отказы и примеры: {len(text)} символов")

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"проверок: {len(RESULTS)}, провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
