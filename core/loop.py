"""Цикл. В v0 — с mock-провайдером: без сети, без модели, без сюрпризов.

Порядок на каждом шаге:

    модель предложила вызов → журнал фиксирует вызов → инструмент исполняется
    → результат ложится артефактом на диск → журнал фиксирует результат (с проверкой дайджеста)
    → только теперь цикл может отдать управление модели

Из этого порядка следует M1-критерий (K17): артефакт существует раньше, чем о нём что-либо
сказано. Обратный порядок технически невозможен, потому что журнал отказывается писать
результат без проверенного артефакта.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .journal import Journal

SKIP_DIRS = {".git", "runs", "node_modules", "__pycache__", ".venv", "home", "refs-cache", ".secrets"}


def snapshot(root: Path) -> dict:
    """Список файлов с размерами: дешёвый снимок, по которому видно, что менялось."""
    entries = []
    for path in sorted(Path(root).rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            try:
                entries.append((str(path.relative_to(root)).replace("\\", "/"), path.stat().st_size))
            except OSError:
                continue
    body = json.dumps(entries, ensure_ascii=False).encode("utf-8")
    return {"files": len(entries), "sha256": hashlib.sha256(body).hexdigest(), "body": body}


@dataclass
class Step:
    """Что «модель» предлагает на шаге: либо вызов инструмента, либо финальный ответ."""
    text: str = ""
    tool: dict | None = None


@dataclass
class MockProvider:
    script: list[Step] = field(default_factory=list)
    index: int = 0

    def next(self) -> Step:
        if self.index >= len(self.script):
            return Step(text="(скрипт исчерпан)")
        step = self.script[self.index]
        self.index += 1
        return step


FAIL_STREAK_LIMIT = 3
SAME_CALL_LIMIT = 3


def run(task: str, provider: MockProvider, tool, journal: Journal, max_steps: int = 16,
        snapshot_root: Path | None = None) -> dict:
    journal.run_start(task, model="mock")
    if snapshot_root is not None:
        state = snapshot(Path(snapshot_root))
        ref = journal.put_artifact(state["body"], ext=".json")
        journal.event("run/snapshot", {"files": state["files"], "sha256": state["sha256"],
                                       "artifact": ref.path})
    steps = 0
    status = "budget"
    failed_streak = 0
    same_call_streak = 0
    last_call: tuple | None = None
    try:
        while steps < max_steps:
            steps += 1
            step = provider.next()

            if step.tool:
                call_id = f"call-{steps}"
                journal.tool_call(call_id, step.tool.get("name", "?"), step.tool.get("args", {}))
                if hasattr(tool, "dispatch"):
                    out = tool.dispatch(step.tool.get("name", "shell"), step.tool.get("args", {}))
                else:
                    out = tool.run(step.tool.get("args", {}).get("command", ""))
                ref = journal.put_artifact(out.text.encode("utf-8"))
                journal.tool_result(call_id, ref, ok=out.ok, preview=out.text[:400])
                if hasattr(provider, "observe"):
                    provider.observe(out.text, out.ok)

                # барахтание: подряд идут отказы или один и тот же вызов
                signature = (step.tool.get("name", "?"), str(step.tool.get("args", {})))
                same_call_streak = same_call_streak + 1 if signature == last_call else 1
                last_call = signature
                failed_streak = failed_streak + 1 if not out.ok else 0
                if failed_streak >= FAIL_STREAK_LIMIT:
                    journal.event("run/flail", {"reason": "три отказа подряд", "steps": steps})
                    status = "flail"
                    break
                if same_call_streak >= SAME_CALL_LIMIT:
                    journal.event("run/flail", {"reason": "три одинаковых вызова", "steps": steps})
                    status = "flail"
                    break
                continue

            journal.assistant_message(step.text)
            status = "done"
            break
    finally:
        if status == "budget":
            last = getattr(provider, "last", None)
            tail = (getattr(last, "text", "") or "").strip()
            journal.event("run/budget", {"steps": steps, "last_text": tail[:400]})
        journal.run_end(status)
        journal.close()

    return {"steps": steps, "status": status}


