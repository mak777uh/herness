"""Тесты привязки частей запроса: привязка к тексту, к инструменту, согласованность."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin.anchor import check, load_capabilities  # noqa: E402

CAPS = load_capabilities()
CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


def field(request: str, parts: list[dict]):
    return check({"request": request, "parts": parts}, CAPS)


@case("полная привязка даёт ANCHORED", False)
def _():
    result = field("проверь страницу openSUSE", [
        {"id": "p1", "text": "проверь страницу openSUSE", "modality": "requires",
         "action": "проверить", "object": "страница", "anchor": "fetch"}])
    assert result.verdict == "ANCHORED" and result.coverage == 1.0, result


@case("противоположные модальности дают REFUSED и S3_OPPOSITE", False)
def _():
    result = field("не используй сеть, но проверь страницу", [
        {"id": "p1", "text": "не используй сеть", "modality": "prohibits",
         "action": "проверить", "object": "страница", "anchor": "fetch"},
        {"id": "p2", "text": "проверь страницу", "modality": "requires",
         "action": "проверить", "object": "страница", "anchor": "fetch"}])
    assert result.verdict == "REFUSED" and "S3_OPPOSITE" in result.codes, result


@case("часть без привязки даёт S2_NO_ANCHOR", False)
def _():
    result = field("сделай что-нибудь", [
        {"id": "p1", "text": "сделай что-нибудь", "modality": "requires",
         "action": "сделать", "object": "что-то", "anchor": ""}])
    assert "S2_NO_ANCHOR" in result.codes and result.verdict == "REFUSED"


@case("привязка на несуществующий шаг даёт S2_UNKNOWN_TOOL", False)
def _():
    result = field("сверь текст", [
        {"id": "p1", "text": "сверь текст", "modality": "requires",
         "action": "проверить", "object": "текст", "anchor": "WF-NOPE"}])
    assert "S2_UNKNOWN_TOOL" in result.codes


@case("фрагмент не из запроса даёт S1_TEXT_NOT_FOUND", False)
def _():
    result = field("проверь страницу", [
        {"id": "p1", "text": "проверь базу", "modality": "requires",
         "action": "проверить", "object": "страница", "anchor": "fetch"}])
    assert "S1_TEXT_NOT_FOUND" in result.codes


@case("инструмент не умеет действие даёт S2_OBJECT_MISMATCH", False)
def _():
    result = field("удали страницу", [
        {"id": "p1", "text": "удали страницу", "modality": "requires",
         "action": "удалить", "object": "страница", "anchor": "fetch"}])
    assert "S2_OBJECT_MISMATCH" in result.codes


@case("периодическое с таймером и проверялкой даёт ANCHORED", False)
def _():
    result = field("следи за изменениями и регулярно проверяй файл", [
        {"id": "p1", "text": "следи за изменениями", "modality": "periodic",
         "action": "следить", "object": "изменения", "anchor": "schedule"},
        {"id": "p2", "text": "регулярно проверяй файл", "modality": "periodic",
         "action": "проверить", "object": "файл", "anchor": "grep"}])
    assert result.verdict == "ANCHORED", result


@case("периодическое без проверялки даёт S4_NO_CHECKER", False)
def _():
    result = field("следи за изменениями", [
        {"id": "p1", "text": "следи за изменениями", "modality": "periodic",
         "action": "следить", "object": "изменения", "anchor": "schedule"}])
    assert "S4_NO_CHECKER" in result.codes and result.verdict == "REFUSED", result


@case("неопределённое без канала даёт S5_UNCERTAIN_NO_CHANNEL", False)
def _():
    result = field("можно ли доверять данным", [
        {"id": "p1", "text": "можно ли доверять данным", "modality": "asks",
         "action": "решить", "object": "вариант", "anchor": "WF-DECIDE",
         "precision": "uncertain", "channel": ""}])
    assert "S5_UNCERTAIN_NO_CHANNEL" in result.codes, result


@case("неопределённое с каналом проходит", False)
def _():
    result = field("можно ли доверять данным", [
        {"id": "p1", "text": "можно ли доверять данным", "modality": "asks",
         "action": "решить", "object": "вариант", "anchor": "WF-DECIDE",
         "precision": "uncertain", "channel": "experiment"}])
    assert result.verdict == "ANCHORED", result


def main() -> int:
    failed = 0
    for name, should_raise, fn in CASES:
        try:
            fn()
            raised = False
        except AssertionError:
            raised = True
        ok = raised == should_raise
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {name}")
    print(f"\nпривязка: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
