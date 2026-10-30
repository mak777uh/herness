"""Печать методологии: хеш канонического префикса файла, sidecar и проверка.

Взято у MethodSeal (OSF 10.17605/OSF.IO/H64GM): всё, что до маркера, — замороженная методология;
всё после — печать и поздние правки, они в хеш не входят. Отличие: их хук fail-open (при ошибке
разрешает вызов), наш — fail-closed: нет sidecar или он не сходится — это провал.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKER = "## Seal"


def canonical(text: str, marker: str = DEFAULT_MARKER) -> str:
    """CRLF/CR -> LF, префикс до маркера, rstrip и один перевод строки."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    index = normalized.find(marker)
    prefix = normalized[:index] if index >= 0 else normalized
    return prefix.rstrip() + "\n"


def digest(path: Path, marker: str = DEFAULT_MARKER) -> str:
    text = path.read_text(encoding="utf-8")
    return hashlib.sha256(canonical(text, marker).encode("utf-8")).hexdigest()


def sidecar(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


def seal(path: Path, marker: str = DEFAULT_MARKER) -> str:
    value = digest(path, marker)
    sidecar(path).write_text(value + "\n", encoding="utf-8")
    return value


def verify(path: Path, marker: str = DEFAULT_MARKER) -> tuple[bool, str]:
    store = sidecar(path)
    if not store.exists():
        return False, f"{path}: нет печати (fail-closed)"
    expected = store.read_text(encoding="utf-8").strip()
    actual = digest(path, marker)
    if expected != actual:
        return False, f"{path}: печать не совпала ({expected[:12]}… != {actual[:12]}…)"
    return True, f"{path}: печать сходится ({actual[:12]}…)"


def verify_all(root: Path = ROOT) -> list[str]:
    problems = []
    for store in sorted(root.rglob("*.sha256")):
        target = Path(str(store)[: -len(".sha256")])
        if not target.exists():
            problems.append(f"{store}: файла {target.name} нет")
            continue
        ok, message = verify(target)
        if not ok:
            problems.append(message)
    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print("seal <файл> [--marker M] | verify <файл> | verify-all")
        return 2
    command, *rest = argv
    marker = DEFAULT_MARKER
    paths = []
    for arg in rest:
        if arg.startswith("--marker="):
            marker = arg.split("=", 1)[1]
        else:
            paths.append(arg)

    if command == "verify-all":
        problems = verify_all()
        for problem in problems:
            print(f"[FAIL] {problem}")
        print(f"печатей проверено: {len(list(ROOT.rglob('*.sha256')))}, проблем: {len(problems)}")
        return 0 if not problems else 1

    if not paths:
        print("нужен путь к файлу")
        return 2

    for raw in paths:
        target = Path(raw)
        if not target.is_absolute():
            target = ROOT / raw
        if not target.exists():
            print(f"{target}: файла нет")
            return 2
        if command == "seal":
            print(f"{target}: запечатано {seal(target, marker)[:16]}…")
        elif command == "verify":
            ok, message = verify(target, marker)
            print(message)
            if not ok:
                return 1
        else:
            print(f"неизвестная команда: {command}")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
