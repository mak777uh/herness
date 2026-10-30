"""MCP-клиент: JSON-RPC по stdio к серверу браузерных инструментов.

Протокол MCP: по одному JSON-объекту в строке, без заголовков Content-Length.
Нам нужен минимум: initialize, tools/list, tools/call.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass


@dataclass
class ToolInfo:
    name: str
    description: str
    schema: dict


class MCPClient:
    """Запускает MCP-сервер и общается с ним построчно."""

    def __init__(self, command: list[str], cwd: str | None = None, env: dict | None = None,
                 timeout: float = 60.0) -> None:
        self.command = command
        self.timeout = timeout
        self._next_id = 1
        self._lock = threading.Lock()
        self._responses: dict[int, dict] = {}
        self.stderr_tail: list[str] = []
        self.proc = subprocess.Popen(
            command, cwd=cwd, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        self._errors = threading.Thread(target=self._read_stderr, daemon=True)
        self._errors.start()

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and isinstance(message.get("id"), int):
                self._responses[message["id"]] = message

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self.stderr_tail.append(line.rstrip())
            if len(self.stderr_tail) > 40:
                self.stderr_tail.pop(0)

    def _send(self, message: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict | None = None) -> dict:
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if request_id in self._responses:
                response = self._responses.pop(request_id)
                if "error" in response:
                    raise RuntimeError(f"MCP error: {response['error']}")
                return response.get("result", {})
            time.sleep(0.02)
        raise TimeoutError(f"нет ответа на {method} за {self.timeout} с")

    def notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def initialize(self) -> dict:
        result = self.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "herness", "version": "0.1"},
        })
        self.notify("notifications/initialized")
        return result

    def tools(self) -> list[ToolInfo]:
        result = self.request("tools/list")
        return [ToolInfo(tool["name"], tool.get("description", ""), tool.get("inputSchema", {}))
                for tool in result.get("tools", [])]

    def call(self, name: str, arguments: dict) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def main() -> int:
    client = MCPClient(["node", r"C:\111\browser-mcp\node_modules\@playwright\mcp\cli.js",
                        "--browser", "chrome", "--headless"],
                       cwd=r"C:\111\browser-mcp")
    try:
        info = client.initialize()
        print("сервер:", json.dumps(info.get("serverInfo", {}), ensure_ascii=False))
        tools = client.tools()
        print(f"инструментов: {len(tools)}")
        for tool in tools[:12]:
            print(f"  - {tool.name}: {tool.description[:70]}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
