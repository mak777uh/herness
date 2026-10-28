"""Контракты харнесса: схемы, которые нельзя обойти.

Принцип P3: формулировка не сильнее типа свидетельства.
Принцип P4: observed и inferred различаются полем, а не прозой.
Принцип P5: утверждение без границы — другое утверждение.

Модуль не зависит ни от чего, кроме стандартной библиотеки: это ядро (ADR-0005).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

EVIDENCE_TYPES = ("proof", "test", "statistics", "observation", "judgment")
ORIGINS = ("observed", "inferred", "model")

# Формулировки, допустимые только при типе proof (P3, P6).
STRONG_WORDS = re.compile(r"(?i)\b(доказан\w*|доказывает|гарантиру\w*|всегда|безопасн\w*|корректн\w*)\b")

# Закрытый словарь вердиктов (P6): «безопасно» нельзя, «проверено против X в редакции R» можно.
VERDICT_TEMPLATE = "проверено в {what} против {against} в редакции {revision}, покрытие {coverage}%"


class ContractError(ValueError):
    """Нарушение контракта: не стилистика, а отказ."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Artifact:
    """Тело свидетельства на диске. Имя — дайджест, а не пожелание."""
    sha256: str
    path: str
    bytes: int
    mime: str = "text/plain"
    created_at: str = field(default_factory=_now)

    def validate(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ContractError(f"artifact.sha256: ожидался sha256, получено {self.sha256!r}")
        if self.bytes < 0:
            raise ContractError("artifact.bytes: отрицательный размер")
        if not self.path:
            raise ContractError("artifact.path: пустой путь")


@dataclass(frozen=True)
class Event:
    """Событие журнала. Append-only: seq строго растёт, правка прошлого невозможна."""
    seq: int
    run_id: str
    type: str
    payload: dict
    ts: str = field(default_factory=_now)

    def validate(self) -> None:
        if self.seq < 0:
            raise ContractError("event.seq: отрицательный номер")
        if not self.run_id:
            raise ContractError("event.run_id: пустой")
        if not self.type or "/" not in self.type:
            raise ContractError(f"event.type: ожидался вид 'домен/действие', получено {self.type!r}")
        if not isinstance(self.payload, dict):
            raise ContractError("event.payload: ожидался объект")


@dataclass(frozen=True)
class Claim:
    """Утверждение: текст + тип + происхождение + свидетельства + граница."""
    id: str
    text: str
    type: str
    origin: str
    evidence: tuple[str, ...] = ()
    not_claimed: tuple[str, ...] = ()

    def validate(self) -> None:
        if not re.fullmatch(r"C-\d{4}", self.id):
            raise ContractError(f"claim.id: ожидался C-NNNN, получено {self.id!r}")
        if self.type not in EVIDENCE_TYPES:
            raise ContractError(f"claim.type: неизвестный тип {self.type!r}")
        if self.origin not in ORIGINS:
            raise ContractError(f"claim.origin: неизвестное происхождение {self.origin!r}")
        if not self.text.strip():
            raise ContractError("claim.text: пустое утверждение")
        # P3: сильная формулировка допустима только при proof.
        if self.type != "proof" and STRONG_WORDS.search(self.text):
            raise ContractError(
                f"claim {self.id}: формулировка сильнее типа {self.type!r} — "
                f"нужен тип proof или более слабая фраза"
            )
        # P5: граница обязательна.
        if not self.not_claimed:
            raise ContractError(f"claim {self.id}: нет границы (not_claimed) — это другое утверждение")
        # P2: свидетельство должно быть материальным.
        if self.type in ("proof", "test", "statistics") and not self.evidence:
            raise ContractError(f"claim {self.id}: тип {self.type} требует свидетельства")
        # P16: вывод модели не равен проверенному.
        if self.origin == "model" and self.type in ("proof", "test"):
            raise ContractError(
                f"claim {self.id}: origin=model не может быть типом {self.type} без внешней проверки"
            )


@dataclass(frozen=True)
class Report:
    """Отчёт прогона. Без границы не существует (P5)."""
    run_id: str
    task: str
    claims: tuple[Claim, ...]
    boundaries: tuple[str, ...]
    created_at: str = field(default_factory=_now)

    def validate(self) -> None:
        if not self.run_id:
            raise ContractError("report.run_id: пустой")
        if not self.task.strip():
            raise ContractError("report.task: пустая задача")
        if not self.boundaries:
            raise ContractError("report.boundaries: отчёт без «что это не доказывает» не создаётся")
        for claim in self.claims:
            claim.validate()


def verdict(what: str, against: str, revision: str, coverage: float) -> str:
    """Единственная допустимая форма сильного вывода (P6)."""
    if not what or not against or not revision:
        raise ContractError("verdict: нужны предмет, база сравнения и редакция")
    if not 0 <= coverage <= 100:
        raise ContractError("verdict: покрытие вне 0..100")
    return VERDICT_TEMPLATE.format(what=what, against=against, revision=revision, coverage=coverage)
