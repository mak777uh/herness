"""Хохфельд для границ: проверка совместимости двух границ участников.

Идея из LexSpec: утверждение раскладывается на позиции, и часть проверок — комбинаторная,
без рассуждения о смысле. Здесь то же самое для границ: не «правильно ли», а «не противоречат ли
друг другу объявленные позиции».

Позиции берём из Хохфельда, но только те, что нужны для обмена:

  privilege(A, X)   — A может делать X
  duty_not(A, X)    — A не должен делать X
  right(B, X от A)  — B вправе требовать X от A
  no_right(B, X)    — B не вправе требовать X от A

Чего здесь нет: условий, сроков, исключений и ссылок на текст закона. Это следующий слой, и его
отсутствие надо называть, а не замалчивать.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoundaryView:
    """Граница в терминах позиций. `allow` — привилегии, `deny` — запреты, `expects` — права."""
    id: str
    allow: frozenset[str] = frozenset()
    deny: frozenset[str] = frozenset()
    expects: frozenset[str] = frozenset()

    def positions(self) -> dict[str, set[str]]:
        return {
            "privilege": set(self.allow),
            "duty_not": set(self.deny),
            "right": set(self.expects),
        }


@dataclass(frozen=True)
class Verdict:
    compatible: bool
    status: str          # совместимо / конфликт / пусто / неизвестно
    reasons: tuple[str, ...]

    def __str__(self) -> str:
        return self.status + (": " + "; ".join(self.reasons) if self.reasons else "")


def check(a: BoundaryView, b: BoundaryView) -> Verdict:
    """Проверяет пару границ на совместимость.

    Правила (комбинаторные, без рассуждения о смысле):

    1. A может X, а B запрещает X               → конфликт
    2. A запрещает X, а B вправе требовать X    → конфликт
    3. A может X, и B тоже может X              → совместимо
    4. A вправе требовать X, B не запрещает X   → совместимо
    5. пересечений нет                           → пусто (мостика нет)
    """
    reasons: list[str] = []
    conflicts: list[str] = []

    for action in sorted(a.allow & b.deny):
        conflicts.append(f"A может '{action}', а B это запрещает")
    for action in sorted(a.deny & b.expects):
        conflicts.append(f"B вправе требовать '{action}', а A это запрещает")
    for action in sorted(b.allow & a.deny):
        conflicts.append(f"B может '{action}', а A это запрещает")
    for action in sorted(b.deny & a.expects):
        conflicts.append(f"A вправе требовать '{action}', а B это запрещает")

    if conflicts:
        return Verdict(False, "конфликт", tuple(conflicts))

    shared = (a.allow & b.allow) | (a.expects & b.expects) | (a.allow & b.expects) | (a.expects & b.allow)
    if shared:
        reasons.append("общие действия: " + ", ".join(sorted(shared)))
        return Verdict(True, "совместимо", tuple(reasons))

    return Verdict(True, "пусто", ("пересечения действий нет — мостика не из чего строить",))


def self_consistency(view: BoundaryView) -> Verdict:
    """Граница не должна одновременно разрешать и запрещать одно и то же."""
    both = view.allow & view.deny
    if both:
        return Verdict(False, "конфликт", tuple(f"одновременно разрешено и запрещено: {x}" for x in sorted(both)))
    return Verdict(True, "совместимо", ())
