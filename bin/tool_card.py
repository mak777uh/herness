"""tool_card — карточка инструмента: то, что модель пишет вместо Rust.

Зачем (DESIGN-0002). Сейчас инструмент — это пять артефактов в четырёх форматах: атомы контракта,
правила политики, запись реестра, тело в `loopmod.rs` и проба. Модели так работать дорого: она
должна знать внутренности цикла. Карточка сводит вход к одному JSON, из которого генератор делает
остальное.

Проверки разделены по schema_version:
  - tool-card-v1: обязательный jsonschema.Draft202012Validator против pinned схемы, затем
    смысловые проверки refusals/purpose/kind/template/effects/exemplars/provenance;
  - legacy v0 (без schema_version): старый валидатор только для исторического validate;
  - activation: отдельный gate, superseded и legacy карточки не активируются.

Автоконверсии v1→v0 нет ни здесь, ни в card_atoms.

    python bin/tool_card.py --check card.json
    python bin/tool_card.py --render card.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODES = ROOT / "lab" / "refusal-codes.json"
SCHEMA = ROOT / "lab" / "tools" / "tool-card-v1.schema.json"
ID = re.compile(r"^[a-z][a-z0-9_]{1,20}$")
ALLOWED_READ = ("/mnt/",)
ALLOWED_WRITE = ("/mnt/work/",)
BANNED = ("быстро", "удобно", "мощно", "просто", "легко", "эффективно")
REQUIRED = ("id", "purpose", "inputs", "outputs", "closure", "refusals", "examples")
PROVENANCE_SOURCES = {
    "lawset_digest": ROOT / "docs" / "CONSTITUTION-v0-2026-11-16.md",
    "policy_digest": ROOT / "lab" / "tools" / "policy.json",
    "room_profile_digest": ROOT / "lab" / "tools" / "room-profile-v0.json",
    "schema_digest": SCHEMA,
}
HEAD_READ_EFFECT = [{"root_ref": "room:input", "segments": ["fixtures"]}]


def refusal_codes(path: Path = CODES) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["code"] for item in data.get("codes", [])}


def _inside(paths, allowed: tuple[str, ...]) -> bool:
    return all(any(item.startswith(prefix) for prefix in allowed) for item in paths)


def _validate_legacy(card: dict, codes: set[str] | None = None) -> list[str]:
    """Исторический v0: сохраняет прежние проверки, но не служит activation gate."""
    codes = refusal_codes() if codes is None else codes
    problems: list[str] = []

    missing = [field for field in REQUIRED if not card.get(field)]
    if missing:
        return [f"нет полей: {', '.join(missing)}"]

    if not ID.match(str(card["id"])):
        problems.append(f"id {card['id']!r}: ожидался [a-z][a-z0-9_]{{1,20}}")

    purpose = str(card["purpose"]).strip()
    if not purpose.endswith("."):
        problems.append("purpose: одно предложение с точкой на конце")
    lowered = purpose.lower()
    for word in BANNED:
        if word in lowered:
            problems.append(f"purpose: непроверяемое слово «{word}» — заменить на проверяемое")

    if not isinstance(card.get("inputs"), dict) or not card["inputs"]:
        problems.append("inputs: нужен непустой объект")
    if not isinstance(card.get("outputs"), dict) or not card["outputs"]:
        problems.append("outputs: нужен непустой объект")

    closure = card.get("closure") or {}
    fs = closure.get("fs") or {}
    read = list(fs.get("read") or [])
    write = list(fs.get("write") or [])
    if not read:
        problems.append("closure.fs.read: пусто — инструмент ничего не прочитает")
    if read and not _inside(read, ALLOWED_READ):
        problems.append(f"closure.fs.read {read}: за пределы комнаты ({ALLOWED_READ[0]}) нельзя")
    if write and not _inside(write, ALLOWED_WRITE):
        problems.append(f"closure.fs.write {write}: запись только внутрь {ALLOWED_WRITE[0]}")
    if closure.get("net"):
        problems.append("closure.net: сеть в этой версии карточки не объявляется")
    for field in ("time_ms", "memory_mb", "output_bytes"):
        value = closure.get(field)
        if not isinstance(value, int) or value <= 0:
            problems.append(f"closure.{field}: нужно целое больше нуля")

    refusals = card.get("refusals") or []
    unknown = [code for code in refusals if code not in codes]
    if unknown:
        problems.append(f"refusals: кодов нет в словаре — {', '.join(unknown)}")

    examples = card.get("examples") or []
    if len(examples) < 3:
        problems.append(f"examples: нужно минимум 3 (норма, граница, отказ), есть {len(examples)}")
    refusal_examples = [e for e in examples if "отказ" in str(e.get("expect", "")).lower()]
    if refusals and not refusal_examples:
        problems.append("examples: нет примера с отказом — карточка не показывает границу")
    if refusal_examples and refusals:
        mentioned = any(any(code in str(e.get("expect", "")) for code in refusals) for e in refusal_examples)
        if not mentioned:
            problems.append("examples: отказ не назван кодом из refusals")
    if not any("отказ" not in str(e.get("expect", "")).lower() for e in examples):
        problems.append("examples: нет ни одного успешного примера")
    for index, example in enumerate(examples, start=1):
        if not example.get("args") and example.get("args") != {}:
            problems.append(f"examples[{index}]: нет args")
        if not example.get("expect"):
            problems.append(f"examples[{index}]: нет expect")
    return problems


def _v1_validator():
    """Загрузить обязательный Draft202012Validator; required-only fallback запрещён."""
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        return None, [f"jsonschema: обязательная зависимость для tool-card-v1 не установлена: {exc}"]
    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"jsonschema: не читается pinned schema {SCHEMA}: {exc}"]
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # noqa: BLE001
        return None, [f"jsonschema: pinned schema некорректна: {exc}"]
    return Draft202012Validator(schema), []


def _validate_effects(card: dict) -> list[str]:
    problems: list[str] = []
    effects = card.get("effects") or {}
    kind = card.get("kind")

    for field in ("fs_read", "fs_list", "fs_write"):
        for index, scope in enumerate(effects.get(field) or []):
            root_ref = scope.get("root_ref")
            segments = scope.get("segments") or []
            if not isinstance(root_ref, str) or not root_ref.startswith("room:"):
                problems.append(f"effects.{field}[{index}]: root_ref должен быть внутри room")
            unsafe = [segment for segment in segments
                      if segment in (".", "..") or any(char in segment for char in ("/", "\\", "\0"))]
            if unsafe:
                problems.append(f"effects.{field}[{index}]: небезопасные segments {unsafe}")

    if kind == "file_read":
        if not effects.get("fs_read"):
            problems.append("effects.fs_read: kind=file_read требует непустой read effect")
        for field in ("fs_list", "fs_write", "bridges"):
            if effects.get(field):
                problems.append(f"effects.{field}: kind=file_read не разрешает {field}")
        if effects.get("process_spawn") is not False:
            problems.append("effects.process_spawn: kind=file_read требует false")
    if card.get("id") == "head":
        if kind != "file_read":
            problems.append("kind: canonical head требует kind=file_read")
        if effects.get("fs_read") != HEAD_READ_EFFECT:
            problems.append(f"effects.fs_read: head требует только {HEAD_READ_EFFECT}")
        for field in ("fs_list", "fs_write", "bridges"):
            if effects.get(field):
                problems.append(f"effects.{field}: canonical head требует пустой {field}")
    return problems


def _validate_v1(card: dict, codes: set[str] | None = None) -> list[str]:
    validator, problems = _v1_validator()
    if validator is None:
        return problems

    errors = sorted(validator.iter_errors(card), key=lambda error: (str(list(error.absolute_path)), error.message))
    for error in errors:
        path = "/".join(str(part) for part in error.absolute_path) or "$"
        problems.append(f"jsonschema {path}: {error.message}")
    if errors:
        return problems

    codes = refusal_codes() if codes is None else codes
    if not codes:
        problems.append("refusals: словарь lab/refusal-codes.json пуст или отсутствует")
    unknown = sorted(set(card["refusals"]) - codes)
    if unknown:
        problems.append(f"refusals: кодов нет в закрытом словаря — {', '.join(unknown)}")

    purpose = card["purpose"].strip()
    if not purpose.endswith("."):
        problems.append("purpose: одно предложение с точкой на конце")
    lowered = purpose.lower()
    for word in BANNED:
        if word in lowered:
            problems.append(f"purpose: непроверяемое слово «{word}» — заменить на проверяемое")

    if card["kind"] == "file_read" and card["template"].get("id") != "file_read_stream":
        problems.append("template.id: kind=file_read требует template=file_read_stream")

    problems += _validate_effects(card)

    examples = card["examples"]
    outcomes = [example["expected"].get("outcome") for example in examples]
    if "ok" not in outcomes:
        problems.append("examples: нет ни одного успешного примера")
    refusal_examples = [example for example in examples if example["expected"].get("outcome") == "refusal"]
    if card["refusals"] and not refusal_examples:
        problems.append("examples: нет примера с отказом — карточка не показывает границу")
    for index, example in enumerate(examples, start=1):
        expected = example["expected"]
        code = expected.get("refusal")
        if expected.get("outcome") == "refusal":
            if code not in card["refusals"]:
                problems.append(f"examples[{index}]: refusal {code!r} не объявлен в refusals")
        elif code is not None:
            problems.append(f"examples[{index}]: успешный пример не должен содержать refusal")

    for name, path in PROVENANCE_SOURCES.items():
        try:
            actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            problems.append(f"provenance {name}: не читается {path}: {exc}")
            continue
        declared = card["provenance"].get(name)
        if declared != actual:
            problems.append(f"provenance {name} не совпадает с {path.name}: {declared} != {actual}")
    return problems


def validate(card: dict, codes: set[str] | None = None) -> list[str]:
    """Dispatch по schema_version; v1 никогда не падает в legacy required-only путь."""
    if not isinstance(card, dict):
        return ["карточка: ожидался JSON-объект"]
    if "schema_version" not in card:
        return _validate_legacy(card, codes)
    version = card["schema_version"]
    if version == "tool-card-v1":
        return _validate_v1(card, codes)
    return [f"schema_version {version!r}: неподдерживаемая версия; автоконверсия в v0 запрещена"]


def validate_activation(card: dict, codes: set[str] | None = None) -> list[str]:
    """Активация строже исторического validate: архивная карточка не получает допуск."""
    if not isinstance(card, dict):
        return validate(card, codes)
    problems = validate(card, codes)
    if card.get("status") == "superseded" or card.get("superseded_by"):
        problems.append("activation: status=superseded/superseded_by — архивную карточку активировать нельзя")
    if not problems and card.get("schema_version") != "tool-card-v1":
        problems.append("activation: нужна tool-card-v1; legacy v0 допускается только для исторического validate")
    return problems


def _field_text(fields) -> str:
    if isinstance(fields, dict):
        return "; ".join(f"{key}: {value}" for key, value in fields.items())
    return "; ".join(f"{field.get('name')}:{field.get('type')}" for field in fields or [])


def render(card: dict) -> str:
    closure = card.get("closure") or {}
    limits = card.get("limits") or {}
    fs = closure.get("fs") or {}
    effects = card.get("effects") or {}
    read_paths = list(fs.get("read") or [])
    write_paths = list(fs.get("write") or [])
    if card.get("schema_version") == "tool-card-v1":
        read_paths = [f"{scope['root_ref']}/{'/'.join(scope['segments'])}"
                      for scope in effects.get("fs_read") or []]
        write_paths = [f"{scope['root_ref']}/{'/'.join(scope['segments'])}"
                       for scope in effects.get("fs_write") or []]
    wall_ms = closure.get("time_ms", limits.get("wall_ms"))
    memory_mb = closure.get("memory_mb", limits.get("memory_bytes", 0) // (1024 * 1024))
    output_bytes = closure.get("output_bytes", limits.get("output_bytes"))
    lines = [
        f"TOOL {card['id']} — {card['purpose']}",
        "вход: " + (_field_text(card.get("inputs")) or "—"),
        "выход: " + (_field_text(card.get("outputs")) or "—"),
        "замыкание: чтение " + (", ".join(read_paths) or "—")
        + "; запись " + (", ".join(write_paths) or "нет")
        + f"; время {wall_ms} мс; память {memory_mb} МБ"
        + f"; выдача {output_bytes} Б",
        "отказы: " + (", ".join(card.get("refusals") or []) or "—"),
    ]
    for example in card.get("examples") or []:
        args = json.dumps(example.get("args") or {}, ensure_ascii=False)
        expected = example.get("expected")
        if isinstance(expected, dict):
            if expected.get("outcome") == "refusal":
                outcome = f"отказ {expected.get('refusal')}"
            else:
                outcome = "; ".join(expected.get("assertions") or ["ok"])
        else:
            outcome = str(example.get("expect") or expected or "")
        lines.append(f"  пример: {args} → {outcome}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="карточка инструмента: проверка и рендер")
    parser.add_argument("--check", metavar="FILE", help="проверить карточку")
    parser.add_argument("--render", metavar="FILE", help="напечатать карточку для модели")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if not (args.check or args.render):
        parser.print_help()
        return 2
    target = Path(args.check or args.render)
    if not target.exists():
        print(f"[FAIL] нет файла: {target}", file=sys.stderr)
        return 2
    try:
        card = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] S1_SCHEMA: {exc}", file=sys.stderr)
        return 2
    problems = validate(card)
    if args.check:
        for problem in problems:
            print(f"[FAIL] {problem}")
        if not problems:
            print(f"[ok] карточка {card['id']} полна: замыкание в комнате, отказы из словаря, примеров {len(card['examples'])}")
        return 0 if not problems else 1
    if problems:
        for problem in problems:
            print(f"[FAIL] {problem}", file=sys.stderr)
        print("next: python bin/tool_card.py --check <файл>", file=sys.stderr)
        return 1
    print(render(card))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
