"""Привязка частей запроса: текст → модальность → инструмент/воркфлоу → вердикт.

Перенос схемы lexspec: утверждение состоит из типизированных позиций, каждая привязана к точному
фрагменту, а проверка отвечает на три вопроса — согласовано ли, привязано ли, какая часть закрыта.

Коды отказа (аналог S2/S3/S6 у lexspec):
  S1_TEXT_NOT_FOUND — текст части не найден в запросе (привязка к тексту неверна)
  S1_NO_MODALITY    — не указана модальность
  S2_NO_ANCHOR      — часть не привязана ни к инструменту, ни к шагу воркфлоу
  S2_UNKNOWN_TOOL   — привязка на несуществующий инструмент/шаг
  S2_OBJECT_MISMATCH— инструмент не умеет эту пару действие/объект
  S3_OPPOSITE       — две части требуют противоположного по одному действию/объекту
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES = ROOT / "capabilities.json"

OPPOSITES = {("requires", "prohibits"), ("prohibits", "requires"),
             ("permits", "prohibits"), ("prohibits", "permits")}


@dataclass
class Part:
    id: str
    text: str
    modality: str = ""
    action: str = ""
    obj: str = ""
    anchor: str = ""
    precision: str = "exact"      # exact | uncertain
    channel: str = ""             # для uncertain: user|experiment|search|peer|refuse
    error: str = ""
    closed: bool = False


@dataclass
class Assumption:
    id: str
    text: str
    basis: str = ""          # declared | measured
    evidence: str = ""
    error: str = ""


@dataclass
class Field:
    request: str
    parts: list[Part] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    coverage: float = 0.0
    verdict: str = "REFUSED"


def load_capabilities() -> dict:
    return json.loads(CAPABILITIES.read_text(encoding="utf-8"))


def _find_tool(caps: dict, anchor: str) -> dict | None:
    for group in ("tools", "workflow"):
        for item in caps[group]:
            if item["id"] == anchor:
                return item
    return None


def check(request: dict, caps: dict) -> Field:
    text = request.get("request", "")
    field_obj = Field(request=text)

    for raw in request.get("parts", []):
        part = Part(id=raw.get("id", "?"), text=raw.get("text", ""),
                    modality=raw.get("modality", ""), action=raw.get("action", ""),
                    obj=raw.get("object", ""), anchor=raw.get("anchor", ""),
                    precision=raw.get("precision", "exact"), channel=raw.get("channel", ""))

        # 1. привязка к тексту запроса: фрагмент должен в нём быть
        if part.text and part.text.lower() not in text.lower():
            part.error = "S1_TEXT_NOT_FOUND"
        elif part.precision == "uncertain" and part.channel not in ("user", "experiment", "search",
                                                                    "peer", "refuse"):
            part.error = "S5_UNCERTAIN_NO_CHANNEL"
        # 2. модальность объявлена
        elif part.modality not in caps["modalities"]:
            part.error = "S1_NO_MODALITY"
        # 3. привязка к инструменту или шагу воркфлоу
        elif not part.anchor:
            part.error = "S2_NO_ANCHOR"
        else:
            target = _find_tool(caps, part.anchor)
            if target is None:
                part.error = "S2_UNKNOWN_TOOL"
            else:
                actions = target.get("actions", [])
                objects = target.get("objects", [])
                if part.action and part.action.lower() not in actions:
                    part.error = "S2_OBJECT_MISMATCH"
                elif part.obj and part.obj.lower() not in objects and objects:
                    part.error = "S2_OBJECT_MISMATCH"

        part.closed = not part.error
        if part.error:
            field_obj.codes.append(part.error)
        field_obj.parts.append(part)

    # 3b. периодическая команда: нужен и сторож (таймер), и проверялка
    periodic = [part for part in field_obj.parts if part.modality == "periodic"]
    if periodic:
        has_timer = any(part.anchor in ("schedule", "WF-WATCH") for part in field_obj.parts)
        has_checker = any(part.anchor in ("fetch", "browser", "grep", "read_file", "shell")
                          for part in field_obj.parts)
        if not has_timer:
            field_obj.codes.append("S4_NO_TIMER")
            for part in periodic:
                part.closed = False
                part.error = part.error or "S4_NO_TIMER"
        if not has_checker:
            field_obj.codes.append("S4_NO_CHECKER")
            for part in periodic:
                part.closed = False
                part.error = part.error or "S4_NO_CHECKER"

    # 3c. допущения: у каждого основание; «измерено» требует свидетельства
    for raw in request.get("assumptions", []):
        item = Assumption(id=raw.get("id", "?"), text=raw.get("text", ""),
                          basis=raw.get("basis", ""), evidence=raw.get("evidence", ""))
        if item.basis not in ("declared", "measured"):
            item.error = "S6_ASSUMPTION_NO_BASIS"
        elif item.basis == "measured" and not item.evidence.strip():
            item.error = "S6_ASSUMPTION_NO_EVIDENCE"
        if item.error:
            field_obj.codes.append(item.error)
        field_obj.assumptions.append(item)

    # 4. согласованность: противоположные модальности на одном действии и объекте
    for i, first in enumerate(field_obj.parts):
        for second in field_obj.parts[i + 1:]:
            if (first.action.lower() == second.action.lower()
                    and first.obj.lower() == second.obj.lower()
                    and (first.modality, second.modality) in OPPOSITES):
                first.error = second.error = "S3_OPPOSITE"
                first.closed = second.closed = False
                field_obj.codes.append("S3_OPPOSITE")

    total = len(field_obj.parts)
    closed = sum(1 for part in field_obj.parts if part.closed)
    field_obj.coverage = closed / total if total else 0.0

    if total == 0:
        field_obj.verdict = "REFUSED"
    elif "S3_OPPOSITE" in field_obj.codes:
        field_obj.verdict = "REFUSED"
    elif any(code.startswith(("S4_", "S5_", "S6_")) for code in field_obj.codes):
        field_obj.verdict = "REFUSED"
    elif field_obj.coverage >= 1.0:
        field_obj.verdict = "ANCHORED"
    elif field_obj.coverage >= 0.8:
        field_obj.verdict = "PARTIAL"
    else:
        field_obj.verdict = "REFUSED"
    return field_obj


def main(argv: list[str]) -> int:
    path = Path(argv[0]) if argv else ROOT / "lab" / "anchor-demo" / "request.json"
    request = json.loads(path.read_text(encoding="utf-8"))
    caps = load_capabilities()
    field_obj = check(request, caps)

    print(f"запрос: {field_obj.request[:90]}")
    print(f"{'часть':<30}{'модальность':<12}{'привязка':<14}{'статус'}")
    for part in field_obj.parts:
        status = "closed" if part.closed else part.error
        print(f"{part.text[:29]:<30}{part.modality:<12}{part.anchor or '—':<14}{status}")
    print(f"\nпокрытие: {field_obj.coverage:.2f}; вердикт: {field_obj.verdict}")
    if field_obj.assumptions:
        print("допущения:")
        for item in field_obj.assumptions:
            print(f"  {item.id}: {item.text[:60]} [{item.basis or '—'}]"
                  + (f" — {item.error}" if item.error else ""))
    if field_obj.codes:
        print("коды:", ", ".join(sorted(set(field_obj.codes))))
    return 0 if field_obj.verdict == "ANCHORED" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
