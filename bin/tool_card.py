"""tool_card — карточка инструмента: то, что модель пишет вместо Rust.

Зачем (DESIGN-0002). Сейчас инструмент — это пять артефактов в четырёх форматах: атомы контракта,
правила политики, запись реестра, тело в `loopmod.rs` и проба. Модели так работать дорого: она
должна знать внутренности цикла. Карточка сводит вход к одному JSON, из которого генератор делает
остальное.

Правила проверяются, а не подразумеваются:
  - замыкание не шире комнаты (`/mnt/**` на чтение, `/mnt/work/**` на запись), сети нет;
  - минимум три примера: норма, граница и отказ (пример без отказа — карточка не принимается);
  - коды отказа — только из закрытого словаря `lab/refusal-codes.json`;
  - `purpose` — одно предложение без непроверяемых слов («быстро», «удобно», «мощно»).

    python bin/tool_card.py --check card.json
    python bin/tool_card.py --render card.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODES = ROOT / "lab" / "refusal-codes.json"
ID = re.compile(r"^[a-z][a-z0-9_]{1,20}$")
ALLOWED_READ = ("/mnt/",)
ALLOWED_WRITE = ("/mnt/work/",)
BANNED = ("быстро", "удобно", "мощно", "просто", "легко", "эффективно")
REQUIRED = ("id", "purpose", "inputs", "outputs", "closure", "refusals", "examples")


def refusal_codes(path: Path = CODES) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["code"] for item in data.get("codes", [])}


def _inside(paths, allowed: tuple[str, ...]) -> bool:
    return all(any(item.startswith(prefix) for prefix in allowed) for item in paths)


def validate(card: dict, codes: set[str] | None = None) -> list[str]:
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


def render(card: dict) -> str:
    closure = card.get("closure") or {}
    fs = closure.get("fs") or {}
    lines = [
        f"TOOL {card['id']} — {card['purpose']}",
        "вход: " + "; ".join(f"{k}: {v}" for k, v in (card.get("inputs") or {}).items()),
        "выход: " + "; ".join(f"{k}: {v}" for k, v in (card.get("outputs") or {}).items()),
        "замыкание: чтение " + (", ".join(fs.get("read") or []) or "—")
        + "; запись " + (", ".join(fs.get("write") or []) or "нет")
        + f"; время {closure.get('time_ms')} мс; память {closure.get('memory_mb')} МБ"
        + f"; выдача {closure.get('output_bytes')} Б",
        "отказы: " + (", ".join(card.get("refusals") or []) or "—"),
    ]
    for example in card.get("examples") or []:
        args = json.dumps(example.get("args") or {}, ensure_ascii=False)
        lines.append(f"  пример: {args} → {example.get('expect')}")
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
    card = json.loads(target.read_text(encoding="utf-8"))
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
