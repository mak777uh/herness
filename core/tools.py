"""Инструменты. В v0 — только оболочка: 80 % действий агента, по данным журналов.

Контракт: инструмент возвращает сырые байты результата и код возврата. Он не знает про модель,
не пишет в журнал и не решает, что считать результатом. Это делает цикл — чтобы правило
«сначала артефакт» было в одном месте, а не в каждом инструменте.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

IS_WIN = sys.platform == "win32"


@dataclass(frozen=True)
class ToolOutput:
    stdout: bytes
    stderr: bytes
    exit_code: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    @property
    def text(self) -> str:
        return (self.stdout + self.stderr).decode("utf-8", errors="replace")


class ShellTool:
    name = "shell"

    def __init__(self, cwd: Path, timeout: int = 120):
        self.cwd = Path(cwd)
        self.timeout = timeout

    def run(self, command: str) -> ToolOutput:
        argv = ["cmd", "/c", command] if IS_WIN else ["/bin/sh", "-c", command]
        try:
            proc = subprocess.run(
                argv, cwd=str(self.cwd), capture_output=True, timeout=self.timeout,
            )
            return ToolOutput(proc.stdout or b"", proc.stderr or b"", proc.returncode)
        except subprocess.TimeoutExpired:
            return ToolOutput(b"", f"timeout after {self.timeout}s".encode(), 124)
        except OSError as exc:
            return ToolOutput(b"", str(exc).encode(), 126)
