"""Провайдеры моделей. Шаг M2-1: контракт ответа и разбор потока, без сети.

Почему без сети: разбор SSE — чистая функция, её можно проверить прогоном. Сетевой вызов —
нельзя проверить без провайдера, поэтому он подключается позже и отдельно.

Главное: ответ модели — это событие, которое обязано лечь в журнал целиком (текст, вызовы
инструментов, использование токенов), иначе свидетельство неполно.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str = ""


@dataclass
class ModelReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    finish_reason: str | None = None

    def to_event(self) -> dict:
        return {
            "text": self.text,
            "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in self.tool_calls],
            "usage": self.usage,
            "finish_reason": self.finish_reason,
        }


class StreamError(ValueError):
    """Поток не соответствует ожидаемому формату — это отказ, а не «попробуем ещё»."""


def parse_sse(lines) -> list[dict]:
    """Разбирает SSE-поток в список JSON-объектов. [DONE] завершает поток.

    Поддерживает: несколько строк data у одного события, комментарии (строки с ':').
    Не поддерживает: повторную сборку битых кадров — битый кадр это отказ.
    """
    events: list[dict] = []
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal data_lines
        if not data_lines:
            return
        payload = "\n".join(data_lines).strip()
        data_lines = []
        if not payload or payload == "[DONE]":
            return
        try:
            events.append(json.loads(payload))
        except json.JSONDecodeError as exc:
            raise StreamError(f"не JSON в потоке: {payload[:120]}") from exc

    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line:
            flush()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    flush()
    return events


def assemble(chunks: list[dict]) -> ModelReply:
    """Собирает ответ из чанков OpenAI-совместимого потока."""
    reply = ModelReply()
    calls: dict[int, ToolCall] = {}

    for chunk in chunks:
        if "usage" in chunk and chunk["usage"]:
            reply.usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                reply.text += delta["content"]
            for item in delta.get("tool_calls") or []:
                index = item.get("index", 0)
                call = calls.setdefault(index, ToolCall(id="", name=""))
                if item.get("id"):
                    call.id = item["id"]
                fn = item.get("function") or {}
                if fn.get("name"):
                    call.name = fn["name"]
                if fn.get("arguments"):
                    call.arguments += fn["arguments"]
            if choice.get("finish_reason"):
                reply.finish_reason = choice["finish_reason"]

    reply.tool_calls = [calls[i] for i in sorted(calls)]
    return reply


class MockProvider:
    """Провайдер без сети: отдаёт заранее заданные ответы по шагам."""

    name = "mock"

    def __init__(self, replies: list[ModelReply]):
        self.replies = replies
        self.index = 0

    def complete(self, messages, tools=None) -> ModelReply:
        if self.index >= len(self.replies):
            return ModelReply(text="(сценарий исчерпан)", finish_reason="stop")
        reply = self.replies[self.index]
        self.index += 1
        return reply
