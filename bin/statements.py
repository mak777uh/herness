"""statements — измерение того, сколько утверждений о СОСТОЯНИИ не имеет владельца.

Важное различение: в ROADMAP строки «готово: …» внутри незакрытого этапа — это критерий закрытия
(обещание), а не утверждение о факте. Считать их утверждениями значит мерить не то.

Поэтому: секция считается «состоянием», только если её заголовок говорит «закрыт / готов / сделано»;
иначе её строки — критерии, и владельца им не требуется.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ["README.md", "docs/STATUS.md", "docs/ROADMAP.md", "docs/VERIFIABILITY.md", "docs/PLAN.md"]

HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
CLOSED = re.compile(r"(?i)(закрыт|готово|сделан|выполнен|done|closed)")
CAPABILITY = re.compile(
    r"(?i)\b(готов|реализован|работает|проверен|измерен|закрыт|пройден|сделан)\w*|\b\d+\b")
OWNER = re.compile(r"(C-\d{4}|E-\d{4}|K\d{3}|ADR-\d{4}|`[^`]*`|bin/[\w./-]+|hs \w+|tests/[\w./-]+)")


def scan(path: Path) -> tuple[int, int, list[str]]:
    total = owned = 0
    examples: list[str] = []
    closed_section = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        heading = HEADING.match(line.strip())
        if heading:
            closed_section = bool(CLOSED.search(heading.group(2)))
            continue
        text = line.strip().lstrip("-*").strip()
        if len(text) < 25 or not CAPABILITY.search(text):
            continue
        if not closed_section:
            continue
        total += 1
        if OWNER.search(text):
            owned += 1
        elif len(examples) < 3:
            examples.append(text[:110])
    return total, owned, examples


def main() -> int:
    grand_total = grand_owned = 0
    print("файл                                  в закрытых секциях  с владельцем  доля")
    for name in FILES:
        path = ROOT / name
        if not path.exists():
            continue
        total, owned, examples = scan(path)
        grand_total += total
        grand_owned += owned
        share = round(100 * owned / total) if total else 0
        print(f"{name:<36} {total:>17} {owned:>12} {share:>5}%")
        for example in examples:
            print("    · " + example)
    share = round(100 * grand_owned / grand_total) if grand_total else 0
    print(f"\nитого: {grand_total} утверждений о состоянии, с владельцем {grand_owned} ({share}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
