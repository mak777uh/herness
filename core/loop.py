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

from dataclasses import dataclass, field

from .journal import Journal


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


def run(task: str, provider: MockProvider, tool, journal: Journal, max_steps: int = 16) -> dict:
    journal.run_start(task, model="mock")
    steps = 0
    status = "budget"
    try:
        while steps < max_steps:
            steps += 1
            step = provider.next()

            if step.tool:
                call_id = f"call-{steps}"
                journal.tool_call(call_id, step.tool.get("name", "?"), step.tool.get("args", {}))
                out = tool.run(step.tool.get("args", {}).get("command", ""))
                ref = journal.put_artifact(out.text.encode("utf-8"))
                journal.tool_result(call_id, ref, ok=out.ok, preview=out.text[:400])
                continue

            journal.assistant_message(step.text)
            status = "done"
            break
    finally:
        journal.run_end(status)
        journal.close()

    return {"steps": steps, "status": status}
