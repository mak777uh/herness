"""Инструменты цикла: оболочка, чтение файла, поиск по шаблону и маршрутизатор.

Зачем читалка: на живом прогоне модель потратила все шаги на борьбу с кавычками в `findstr`
и `python -c`, вместо того чтобы читать документ.

Зачем поиск: сверка «где это сказано» — это регексп по файлам, а не оболочка. С `grep` модель
делает один вызов вместо трёх-четырёх попыток с кавычками.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

IS_WIN = __import__("sys").platform == "win32"

SKIP_DIRS = {".git", "runs", "refs-cache", "node_modules", "__pycache__", ".secrets", "home", ".venv"}


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


DENY_PARTS = {".secrets", ".git", ".ssh"}
DENY_SUFFIXES = {".pem", ".key", ".pfx", ".p12", ".kdbx"}
DENY_NAMES = {".env", "credentials.yaml", ".credentials.yaml", "id_rsa", "id_ed25519"}


def _denied(path: Path) -> bool:
    """Секреты не читаются инструментами даже внутри корня."""
    parts = {part.lower() for part in path.parts}
    if parts & DENY_PARTS:
        return True
    if path.suffix.lower() in DENY_SUFFIXES:
        return True
    return path.name.lower() in {name.lower() for name in DENY_NAMES}


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
        if not target.is_relative_to(self.root.resolve()):
            return ToolOutput(b"", b"path escapes root", 126)
        if _denied(target):
            return ToolOutput(b"", b"secret path denied", 126)
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


class GrepTool:
    """Поиск регекспа по файлам: выдаёт путь, номер строки и саму строку."""

    name = "grep"

    def __init__(self, root: Path, max_results: int = 120):
        self.root = Path(root)
        self.max_results = max_results

    def run(self, pattern: str, glob: str = "*.md", max_results: int = 0) -> ToolOutput:
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return ToolOutput(b"", f"плохой шаблон: {exc}".encode(), 2)

        limit = max_results or self.max_results
        hits: list[str] = []
        root = self.root.resolve()
        for path in sorted(self.root.rglob(glob)):
            if not path.resolve().is_relative_to(root):
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    rel = path.relative_to(self.root)
                    hits.append(f"{rel}:{number}: {line.strip()[:200]}")
                    if len(hits) >= limit:
                        break
            if len(hits) >= limit:
                break

        if not hits:
            return ToolOutput("(совпадений нет)".encode("utf-8"), b"", 0)
        return ToolOutput("\n".join(hits).encode("utf-8"), b"", 0)


class ListTool:
    """Перечисление каталога и подсчёт по маске: без оболочки и без кавычек."""

    name = "list_dir"

    def __init__(self, root: Path, limit: int = 200):
        self.root = Path(root)
        self.limit = limit

    def run(self, path: str = ".", glob: str = "*", count: bool = False) -> ToolOutput:
        base = (self.root / path).resolve()
        if not base.is_relative_to(self.root.resolve()):
            return ToolOutput(b"", b"path escapes root", 126)
        if _denied(base):
            return ToolOutput(b"", b"secret path denied", 126)
        if not base.exists() or not base.is_dir():
            return ToolOutput(b"", f"нет каталога: {path}".encode(), 2)
        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in base.glob(glob or "*"))
        if count:
            return ToolOutput(f"найдено {len(entries)}".encode("utf-8"), b"", 0)
        shown = entries[: self.limit]
        tail = "" if len(entries) <= self.limit else "... (всего " + str(len(entries)) + ")"
        return ToolOutput((chr(10).join(shown) + tail).encode("utf-8"), b"", 0)


class ToolRouter:
    """Маршрутизация вызова по имени инструмента: цикл отдаёт имя и аргументы."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.shell = ShellTool(self.root)
        self.reader = ReadTool(self.root)
        self.grepper = GrepTool(self.root)
        self.lister = ListTool(self.root)

    def run(self, command: str) -> ToolOutput:
        """Совместимость с mock-циклом: без имени — это оболочка."""
        return self.shell.run(command)

    def dispatch(self, name: str, args: dict) -> ToolOutput:
        if name == "read_file":
            return self.reader.run(args.get("path", ""), int(args.get("offset", 1) or 1),
                                   int(args.get("limit", 0) or 0))
        if name == "list_dir":
            return self.lister.run(args.get("path", ".") or ".", args.get("glob", "*") or "*",
                                   bool(args.get("count", False)))
        if name == "grep":
            return self.grepper.run(args.get("pattern", ""), args.get("glob", "*.md") or "*.md",
                                    int(args.get("max_results", 0) or 0))
        return self.shell.run(str(args.get("command", "")))


