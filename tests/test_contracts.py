"""Тесты контрактов. Без pytest: stdlib-only (ADR-0005).

Запуск: python tests/test_contracts.py
Правило: на каждый запрет — посаженное нарушение. Иначе запрет декоративен (P10).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.contracts import Artifact, Claim, ContractError, Event, Report, verdict  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


@case("валидное наблюдение проходит", False)
def _():
    Claim(
        id="C-0001",
        text="холодный старт headless p50 = 0,46 с",
        type="observation",
        origin="observed",
        evidence=("runs/bench-1/meta.json",),
        not_claimed=("что так же на другой машине",),
    ).validate()


@case("«доказано» при observation отбивается (P3)", True)
def _():
    Claim(
        id="C-0002",
        text="это доказано прогоном",
        type="observation",
        origin="observed",
        evidence=("runs/x",),
        not_claimed=("ничего",),
    ).validate()


@case("утверждение без границы отбивается (P5)", True)
def _():
    Claim(id="C-0003", text="файл записан", type="observation", origin="observed", evidence=("a",)).validate()


@case("тип test без свидетельства отбивается (P2)", True)
def _():
    Claim(id="C-0004", text="тест прошёл", type="test", origin="observed",
          not_claimed=("ничего",)).validate()


@case("origin=model не может быть proof (P16)", True)
def _():
    Claim(id="C-0005", text="теорема верна", type="proof", origin="model",
          evidence=("lemma.md",), not_claimed=("формализация",)).validate()


@case("плохой sha артефакта отбивается", True)
def _():
    Artifact(sha256="deadbeef", path="a.txt", bytes=3).validate()


@case("событие без домена в типе отбивается", True)
def _():
    Event(seq=1, run_id="r1", type="step", payload={}).validate()


@case("отчёт без границы не создаётся (P5)", True)
def _():
    Report(run_id="r1", task="проверить", claims=(), boundaries=()).validate()


@case("вердикт в закрытом словаре (P6)", False)
def _():
    text = verdict("кодировку", "корпус", "R-2026-10", 91.5)
    assert "покрытие 91.5%" in text, text


@case("вердикт с покрытием вне диапазона отбивается", True)
def _():
    verdict("кодировку", "корпус", "R", 120)


def main() -> int:
    failed = 0
    for name, should_raise, fn in CASES:
        try:
            fn()
            raised = False
        except ContractError:
            raised = True
        ok = raised == should_raise
        failed += 0 if ok else 1
        mark = "ok" if ok else "FAIL"
        print(f"[{mark}] {name}")
    print(f"\nконтракты: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
