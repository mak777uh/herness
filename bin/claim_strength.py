"""Общие предикаты силы утверждения (ADR-0058).

Одна реализация для coverage.py и claims_audit.py — чтобы мера «слабого ожидания» не
расходилась между прибором покрытия и аудитом ожиданий (как policy_sync для политики).
Предикаты ФОРМЫ, не смысла: ожидание проверяемо, если в нём число/путь/код — то, что можно
найти в артефакте, но нельзя придумать. Общее слово («ок», «done») подтверждает себя собой.

bin/check_coverage_verdict.py НАМЕРЕННО не импортирует этот модуль: независимая сверка
должна ловить расхождение реализаций, а не повторять одну логику.
"""

from __future__ import annotations

import re
from pathlib import Path


def looks_checkable(expect: str) -> bool:
    """Ожидание проверяемо по форме: число, путь или код — а не общее слово."""
    if re.search(r"\d", expect):
        return True
    if "/" in expect or ".md" in expect or ".txt" in expect or ".json" in expect:
        return True
    if re.search(r"[A-Z]-\d", expect):
        return True
    return False


def is_runnable(cmd: str) -> bool:
    """Команда исполняемая (не описание) — тот же словарь, что verify_claims.run_command."""
    return bool(re.search(r"\b(python|pytest|git|bash|pwsh|node)\b", cmd))


def artifact_resolves(artifact: str, root: Path) -> bool:
    """Артефакт — реальный путь/файл (glob непуст), а не описание «вывод команды»."""
    if not artifact or artifact == "—":
        return False
    return bool(list(root.glob(artifact)))