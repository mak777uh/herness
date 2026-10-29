"""Живой провайдер для цикла: модель с одним инструментом `shell`.

Отличие от mock: здесь модель настоящая, поэтому цикл обязан вести историю сообщений и возвращать
наблюдение обратно модели. Всё остальное — как в mock: вызов → журнал → артефакт → результат → ответ.

Провайдер не «умный»: он не решает, нужен ли инструмент. Он передаёт модели ту же схему инструмента
и возвращает её решение. Решение принимает модель — и оно попадает в журнал как есть.
"""

from __future__ import annotations

import json

from .loop import Step
from .provider import ModelReply

TOOL_SPEC = [{
    "type": "function",
    "function": {
        "name": "shell",
        "description": "Выполнить команду оболочки и получить её вывод (stdout+stderr).",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "команда целиком"}},
            "required": ["command"],
        },
    },
}]

SYSTEM = (
    "Ты — исполнитель в харнессе. Среда: Windows, команды идут в cmd.exe (bash-конструкции "
    "вроде ls/find/wc недоступны). У тебя есть один инструмент: shell. "
    "Если для ответа нужен факт из среды — вызови его. Если не нужен — ответь текстом. "
    "Не выдумывай вывод команд: если не вызывал, не утверждай, что видел результат. "
    "Точный подсчёт строк в выводе делай сам, а не конструкциями оболочки: find /c капризен. "
)


class LiveProvider:
    """Обёртка над сетевым провайдером, совместимая с циклом (метод next)."""

    def __init__(self, client, task: str, max_steps: int = 8):
        self.client = client
        self.max_steps = max_steps
        self.messages: list[dict] = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": task},
        ]
        self.last: ModelReply | None = None
        self.calls = 0

    def next(self) -> Step:
        self.calls += 1
        result = self.client.complete(self.messages, tools=TOOL_SPEC, stream=False)
        reply = getattr(result, "reply", result)
        self.last = reply

        if reply.tool_calls:
            call = reply.tool_calls[0]
            self.messages.append({
                "role": "assistant",
                "content": reply.text or "",
                "tool_calls": [{
                    "id": call.id or "call",
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments or "{}"},
                }],
            })
            try:
                args = json.loads(call.arguments or "{}")
            except json.JSONDecodeError:
                args = {"command": ""}
            return Step(tool={"name": call.name, "args": args})

        self.messages.append({"role": "assistant", "content": reply.text})
        return Step(text=reply.text)

    def observe(self, output: str, ok: bool) -> None:
        """Возвращает модели результат вызова инструмента."""
        self.messages.append({
            "role": "tool",
            "tool_call_id": "call",
            "content": ("exit=0\n" if ok else "exit!=0\n") + output[:8000],
        })


