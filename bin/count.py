"""count — числа, на которые ссылаются документы.

Документ не должен быть сильнее дерева: если в README написано «25 принципов», это число обязано
печататься командой и стоять в реестре утверждений.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def principles() -> int:
    text = (ROOT / "docs" / "PRINCIPLES.md").read_text(encoding="utf-8")
    return len(re.findall(r"^\|\s*P\d+", text, re.MULTILINE))


def criteria() -> int:
    text = (ROOT / "docs" / "CRITERIA.md").read_text(encoding="utf-8")
    return len(re.findall(r"^\|\s*K\d+", text, re.MULTILINE))


def claims() -> int:
    text = (ROOT / "CLAIMS.md").read_text(encoding="utf-8")
    return len(re.findall(r"^\|\s*C-\d+", text, re.MULTILINE))


def repos() -> int:
    """Репозитории в кэше справочника: каталог, в котором есть документы."""
    cache = ROOT / "refs-cache"
    if not cache.exists():
        return 0
    return sum(1 for d in cache.iterdir() if d.is_dir() and any(d.rglob("*.md")))


def tests() -> int:
    return len(list((ROOT / "tests").glob("test_*.py")))


COUNTERS = {"principles": principles, "criteria": criteria, "claims": claims,
            "repos": repos, "tests": tests}


def main(argv: list[str]) -> int:
    keys = argv or list(COUNTERS)
    for key in keys:
        if key not in COUNTERS:
            print(f"неизвестный счётчик: {key}", file=sys.stderr)
            return 2
        print(f"{key}={COUNTERS[key]()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

