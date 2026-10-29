"""Тесты разбора потока провайдера. Без сети: проверяется чистая функция.

Запуск: python tests/test_provider.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.provider import StreamError, assemble, parse_sse  # noqa: E402

CASES: list[tuple[str, bool, callable]] = []


def case(name: str, should_raise: bool):
    def wrap(fn):
        CASES.append((name, should_raise, fn))
        return fn
    return wrap


TEXT_STREAM = [
    'data: {"choices":[{"delta":{"content":"При"}}]}\n',
    "\n",
    'data: {"choices":[{"delta":{"content":"вет"}}]}\n',
    "\n",
    "data: [DONE]\n",
    "\n",
]

TOOL_STREAM = [
    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"shell","arguments":"{\\"comm"}}]}}]}\n',
    "\n",
    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"and\\":\\"ls\\"}"}}]},"finish_reason":"tool_calls"}]}\n',
    "\n",
    "data: [DONE]\n",
]


@case("текстовые дельты собираются в один ответ", False)
def _():
    reply = assemble(parse_sse(TEXT_STREAM))
    assert reply.text == "Привет", reply.text
    assert reply.tool_calls == []


@case("аргументы вызова склеиваются из кусков", False)
def _():
    reply = assemble(parse_sse(TOOL_STREAM))
    assert len(reply.tool_calls) == 1, reply.tool_calls
    call = reply.tool_calls[0]
    assert call.id == "call_1" and call.name == "shell", call
    assert call.arguments == '{"command":"ls"}', call.arguments


@case("использование токенов читается из чанка", False)
def _():
    chunks = parse_sse(['data: {"usage":{"prompt_tokens":10,"completion_tokens":5},"choices":[]}\n'])
    reply = assemble(chunks)
    assert reply.usage["prompt_tokens"] == 10, reply.usage


@case("битый JSON — отказ, а не тихое продолжение", True)
def _():
    parse_sse(['data: {не json}\n', '\n'])


@case("[DONE] завершает поток и не попадает в чанки", False)
def _():
    chunks = parse_sse(TEXT_STREAM)
    assert len(chunks) == 2, chunks
    assert all(isinstance(c, dict) for c in chunks)


def main() -> int:
    failed = 0
    for name, should_raise, fn in CASES:
        try:
            fn()
            raised = False
        except (AssertionError, StreamError):
            raised = True
        ok = raised == should_raise
        failed += 0 if ok else 1
        print(f"[{'ok' if ok else 'FAIL'}] {name}")
    print(f"\nпровайдер: {len(CASES) - failed}/{len(CASES)} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
