"""Тесты живого провайдера без сети: поддельный клиент, настоящий цикл.

Проверяем именно стык, который ломался на живом прогоне: разбор вызова инструмента и возврат
наблюдения обратно модели.
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.http_provider import HttpResult  # noqa: E402
from core.journal import Journal  # noqa: E402
from core.live import LiveProvider  # noqa: E402
from core.loop import run as loop_run  # noqa: E402
from core.provider import ModelReply, ToolCall  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


@dataclass
class FakeClient:
    replies: list[ModelReply] = field(default_factory=list)
    seen_tools: bool = False
    index: int = 0
    messages_seen: list = field(default_factory=list)

    def complete(self, messages, tools=None, stream=True):
        self.seen_tools = self.seen_tools or bool(tools)
        self.messages_seen.append(list(messages))
        reply = self.replies[min(self.index, len(self.replies) - 1)]
        self.index += 1
        return HttpResult(reply=reply, status=200, latency_ms=1, raw_chunks=0)


@dataclass
class FakeTool:
    calls: list[str] = field(default_factory=list)

    def run(self, command: str):
        self.calls.append(command)

        @dataclass
        class Out:
            text: str
            ok: bool
            exit_code: int = 0

        return Out(text="15\n", ok=True)


@case("вызов инструмента доходит до цикла и исполняется", False)
def _():
    client = FakeClient(replies=[
        ModelReply(text="", tool_calls=[ToolCall(id="1", name="shell",
                                                 arguments=json.dumps({"command": "dir /b bin\\*.py"}))]),
        ModelReply(text="15 файлов"),
    ])
    provider = LiveProvider(client, "сколько .py в bin")
    tool = FakeTool()
    tmp = Path(tempfile.mkdtemp())
    result = loop_run("сколько .py в bin", provider, tool, Journal(tmp), max_steps=4)
    assert tool.calls == ["dir /b bin\\*.py"], tool.calls
    assert result["status"] == "done", result
    assert (tmp / "artifacts"), "артефакт не записан"


@case("наблюдение возвращается модели после вызова", False)
def _():
    client = FakeClient(replies=[ModelReply(text="готово")])
    provider = LiveProvider(client, "задача")
    provider.observe("15\n", True)
    last = client.messages_seen[0] if client.messages_seen else None
    provider.next()
    messages = client.messages_seen[-1]
    assert any(m.get("role") == "tool" for m in messages), messages


@case("схема инструмента передаётся модели", False)
def _():
    client = FakeClient(replies=[ModelReply(text="ок")])
    LiveProvider(client, "задача").next()
    assert client.seen_tools, "tools не переданы в клиент"


@case("текстовый ответ завершает цикл без вызова", False)
def _():
    client = FakeClient(replies=[ModelReply(text="ответ без инструмента")])
    provider = LiveProvider(client, "задача")
    step = provider.next()
    assert step.tool is None and step.text == "ответ без инструмента", step


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
    print(f"\nживой цикл: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
