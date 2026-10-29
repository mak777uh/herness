"""Инструменты цикла: оболочка, чтение файла и маршрутизатор по имени.

Зачем читалка: на живом прогоне модель потратила все шаги на борьбу с кавычками в `findstr`
и `python -c`, вместо того чтобы читать документ. Инструмент должен соответствовать задаче,
иначе модель тратит шаги на сантехнику.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

IS_WIN = __import__("sys").platform == "win32"


@dataclass
class ToolOutput:
    stdout: bytes
    stderr: bytes
    exit_code: int

    @property
    def text(self) -> str:
        out = self.stdout.decode("utf-8", "replace")
        err = self.stderr.decode("utf-8", "replace")
        return out + (("\n[stderr]\n" + err) if err.strip() else "")

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


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


class ReadTool:
    """Чтение файла с номерами строк: без кавычек, без оболочки, без сюрпризов."""

    name = "read_file"

    def __init__(self, root: Path, max_lines: int = 400):
        self.root = Path(root)
        self.max_lines = max_lines

    def run(self, path: str, offset: int = 1, limit: int = 0) -> ToolOutput:
        target = (self.root / path).resolve()
        if not str(target).startswith(str(self.root.resolve())):
            return ToolOutput(b"", b"path escapes root", 126)
        if not target.exists() or not target.is_file():
            return ToolOutput(b"", f"нет файла: {path}".encode(), 2)
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(offset - 1, 0)
        count = limit or self.max_lines
        chunk = lines[start:start + count]
        body = "\n".join(f"{start + i + 1}: {line}" for i, line in enumerate(chunk))
        tail = ""
        if start + count < len(lines):
            tail = f"\n... (всего строк {len(lines)}, показано до {start + count})"
        return ToolOutput((body + tail).encode("utf-8"), b"", 0)


class ToolRouter:
    """Маршрутизация вызова по имени инструмента: цикл отдаёт имя и аргументы."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.shell = ShellTool(self.root)
        self.reader = ReadTool(self.root)

    def run(self, command: str) -> ToolOutput:
        """Совместимость с mock-циклом: без имени — это оболочка."""
        return self.shell.run(command)

    def dispatch(self, name: str, args: dict) -> ToolOutput:
        if name == "read_file":
            return self.reader.run(args.get("path", ""), int(args.get("offset", 1) or 1),
                                   int(args.get("limit", 0) or 0))
        return self.shell.run(str(args.get("command", "")))
