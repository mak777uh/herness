"""Провайдер OpenAI-совместимого API: сетевой вызов поверх разбора потока.

Сеть здесь отделена от разбора: `parse_sse`/`assemble` проверяются прогоном без сети,
а транспорт — отдельный класс, который можно заменить на реплей для тестов.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .provider import ModelReply, StreamError, ToolCall, assemble, parse_sse


@dataclass
class HttpResult:
    reply: ModelReply
    status: int
    latency_ms: int
    raw_chunks: int


class OpenAICompatProvider:
    """Вызов OpenAI-совместимого /chat/completions.

    Ключ берётся из переменной окружения по имени, а не из аргумента: значение не должно
    проходить через код и логи.
    """

    def __init__(self, base_url: str, model: str, api_key_env: str,
                 timeout: int = 120, extra_headers: dict | None = None,
                 max_tokens: int = 1024):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self.max_tokens = max_tokens

    def _key(self) -> str:
        """Ключ: окружение → локальный `.secrets/<имя>` → хранилище DSH (`store:ИМЯ`).

        Значение не печатается и не логируется: наружу выходит только отпечаток, если спросят.
        """
        name = self.api_key_env
        if name.startswith("store:"):
            target = name.split(":", 1)[1]
            path = Path.home() / ".dsh" / ".credentials.yaml"
            if not path.exists():
                return ""
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                match = re.match(r"^\s*" + re.escape(target) + r"\s*:\s*(.+)$", line)
                if match:
                    return match.group(1).strip().strip("\"'")
            return ""

        from_env = os.environ.get(name, "")
        if from_env:
            return from_env
        local = Path(__file__).resolve().parents[1] / ".secrets" / name.lower()
        if local.exists():
            return local.read_text(encoding="utf-8").strip()
        return ""

    def _headers(self) -> dict:
        key = self._key()
        headers = {"Content-Type": "application/json",
                   "Accept": "text/event-stream",
                   # без User-Agent Cloudflare отбивает запрос 403 и это выглядит как отказ провайдера
                   "User-Agent": "herness/1.0"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        headers.update(self.extra_headers)
        return headers

    def _opener(self):
        """Локальные адреса идут мимо системного прокси: иначе запрос к себе уходит в прокси-цепочку."""
        host = urllib.parse.urlparse(self.base_url).hostname or ""
        if host in {"127.0.0.1", "localhost", "::1"}:
            return urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return urllib.request.build_opener()

    def has_key(self) -> bool:
        return bool(self._key())

    def complete(self, messages, tools=None, stream: bool = True) -> HttpResult:
        payload = {"model": self.model, "messages": messages, "stream": stream,
                   "max_tokens": self.max_tokens}
        if tools:
            payload["tools"] = tools
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, headers=self._headers(), method="POST"
        )

        started = time.perf_counter()
        try:
            opener = self._opener()
            with opener.open(request, timeout=self.timeout) as response:
                status = response.status
                if stream:
                    chunks = parse_sse(line.decode("utf-8", errors="replace") for line in response)
                    reply = assemble(chunks)
                    count = len(chunks)
                else:
                    data = json.loads(response.read().decode("utf-8"))
                    choice = (data.get("choices") or [{}])[0]
                    message = choice.get("message") or {}
                    raw_calls = message.get("tool_calls") or []
                    reply = ModelReply(
                        text=message.get("content") or "",
                        tool_calls=[ToolCall(id=call.get("id", ""),
                                             name=(call.get("function") or {}).get("name", ""),
                                             arguments=(call.get("function") or {}).get("arguments", ""))
                                    for call in raw_calls],
                        usage=data.get("usage") or {},
                        finish_reason=choice.get("finish_reason"),
                    )
                    count = 0
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise StreamError(f"HTTP {exc.code} от провайдера: {detail}") from exc
        except urllib.error.URLError as exc:
            raise StreamError(f"сеть недоступна: {exc.reason}") from exc

        return HttpResult(reply=reply, status=status,
                          latency_ms=int((time.perf_counter() - started) * 1000),
                          raw_chunks=count)


def from_settings(base_url: str, model: str, key_env: str) -> OpenAICompatProvider:
    return OpenAICompatProvider(base_url=base_url, model=model, api_key_env=key_env)




