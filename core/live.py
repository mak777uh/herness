"""Живой провайдер для цикла: модель с одним инструментом `shell`.

Отличие от mock: здесь модель настоящая, поэтому цикл обязан вести историю сообщений и возвращать
наблюдение обратно модели. Всё остальное — как в mock: вызов → журнал → артефакт → результат → ответ.

Провайдер не «умный»: он не решает, нужен ли инструмент. Он передаёт модели ту же схему инструмента
и возвращает её решение. Решение принимает модель — и оно попадает в журнал как есть.
"""

from __future__ import annotations

import json
from pathlib import Path

from .loop import Step
from .provider import ModelReply

TOOL_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "fetch",
            "description": "Забрать страницу по URL (HTTP, без браузера). Не видит JS и капчу.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "адрес http/https"},
                    "max_bytes": {"type": "integer", "description": "лимит байтов"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Перечислить каталог или посчитать файлы по маске. Для подсчётов используй count=true.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "каталог от корня, например runs"},
                    "glob": {"type": "string", "description": "маска, например *-live"},
                    "count": {"type": "boolean", "description": "только число"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Найти строки по регулярному выражению. Возвращает путь:строка: текст.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "регулярное выражение"},
                    "glob": {"type": "string", "description": "маска файлов, например docs/*.md"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Прочитать текстовый файл с номерами строк. Без оболочки и кавычек.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "путь от корня проекта"},
                    "offset": {"type": "integer", "description": "с какой строки (1-based)"},
                    "limit": {"type": "integer", "description": "сколько строк"},
                },
                "required": ["path"],
            },
        },
    },
    {
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

SYSTEM_TOOLS = (
    "Ты — исполнитель в харнессе. Среда: Windows, команды идут в cmd.exe (bash-конструкции "
    "вроде ls/find/wc недоступны). У тебя четыре инструмента: shell, read_file, grep, list_dir. "
    "Для поиска по тексту используй grep, для подсчёта — list_dir с count=true, а не find /c. "
    "Если для ответа нужен факт из среды — вызови инструмент. Если не нужен — ответь текстом. "
    "Не выдумывай вывод команд: если не вызывал, не утверждай, что видел результат. "
    "Точный подсчёт строк в выводе делай сам, а не конструкциями оболочки: find /c капризен. "
    "Карта проекта: README.md, CLAIMS.md, AGENTS.md, docs/*.md (включая STATUS.md и ROADMAP.md), "
    "bin/*.py, core/*.py, tests/*.py, runs/. Пути в read_file — от корня проекта. "
)

def _brief() -> str:
    """Справка о проекте — из файла, а не из кода: одно место правки."""
    path = Path(__file__).resolve().parents[1] / "docs" / "BRIEF.md"
    if not path.exists():
        return ""
    body = path.read_text(encoding="utf-8").strip()
    return " ".join(body.split())[:1200]


BRIEF = _brief()

SYSTEM_PLAIN = (
    "Ты — аналитик в харнессе. Инструментов у тебя НЕТ: вызвать ничего нельзя, любые команды "
    "и чтения файлов недоступны. Отвечай тем, что дано в задаче или в справке ниже. "
    "Если данных не хватает — так и скажи, не выдумывай. "
    "Запрещено выдавать синтаксис вызова инструмента: его не существует. " + BRIEF
)


class LiveProvider:
    """Обёртка над сетевым провайдером, совместимая с циклом (метод next)."""

    def __init__(self, client, task: str, max_steps: int = 8, use_tools: bool = True):
        self.client = client
        self.max_steps = max_steps
        self.messages: list[dict] = [
            {"role": "system", "content": SYSTEM_TOOLS if use_tools else SYSTEM_PLAIN},
            {"role": "user", "content": task},
        ]
        self.last: ModelReply | None = None
        self.calls = 0
        self.use_tools = use_tools

    def next(self) -> Step:
        self.calls += 1
        result = self.client.complete(self.messages, tools=TOOL_SPEC if self.use_tools else None,
                                      stream=False)
        reply = getattr(result, "reply", result)
        if not (reply.text or "").strip() and (reply.finish_reason or "") == "length":
            # рассуждение съело лимит: один повтор с удвоенным бюджетом, без бесконечных попыток
            budget = min(getattr(self.client, "max_tokens", 8000) * 2, 32000)
            self.client.max_tokens = budget
            result = self.client.complete(self.messages, tools=TOOL_SPEC if self.use_tools else None,
                                          stream=False)
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

        text = reply.text or ""
        if not self.use_tools and ("<tool_call" in text.lower() or "invoke name=" in text.lower()):
            # без схемы инструментов модель изобретает вызов: это надо назвать, а не выдать за ответ
            text = "[ВЫДУМАННЫЙ ВЫЗОВ: инструментов не было, а модель выдала синтаксис вызова]\n" + text
        if not text.strip():
            usage = getattr(reply, "usage", {}) or {}
            text = ("(пустой ответ модели: finish={0}, completion_tokens={1}; "
                    "рассуждение считается в лимит max_tokens)".format(
                        getattr(reply, "finish_reason", "?"), usage.get("completion_tokens", "?")))
        self.messages.append({"role": "assistant", "content": text})
        return Step(text=text)

    def observe(self, output: str, ok: bool) -> None:
        """Возвращает модели результат вызова инструмента."""
        self.messages.append({
            "role": "tool",
            "tool_call_id": "call",
            "content": ("exit=0\n" if ok else "exit!=0\n") + output[:8000],
        })














