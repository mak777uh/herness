"""caught_by — чем пойман отказ, если поле не заполнено.

Правило: у отказа без «чем пойман» нет гарантии, что он не повторится. Поле заполняется из того,
что в файле уже есть: поле `detect` (как нашли) — основной источник; если его нет, берётся `test`.

    python bin/caught_by.py            # дописать caught_by там, где его нет
    python bin/caught_by.py --check    # только посчитать
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURES = ROOT / "lab" / "failures"


def field(text: str, name: str) -> str:
    match = re.search(rf"^{name}:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def fill() -> int:
    added = skipped = 0
    for path in sorted(FAILURES.glob("F-*.md")):
        text = path.read_text(encoding="utf-8")
        if re.search(r"^caught_by:", text, re.MULTILINE):
            skipped += 1
            continue
        source = field(text, "detect") or field(text, "test")
        if not source:
            print(f"{path.stem}: нет ни detect, ни test — оставить как есть")
            continue
        # Строка вставляется после test, чтобы порядок полей оставался читаемым.
        if re.search(r"^test:", text, re.MULTILINE):
            text = re.sub(r"^(test:.*)$", r"\1\ncaught_by: " + source, text, count=1, flags=re.MULTILINE)
        else:
            text = text.rstrip("\n") + f"\ncaught_by: {source}\n"
        path.write_text(text, encoding="utf-8")
        added += 1
    print(f"дописано: {added}; уже было: {skipped}")
    return 0


def check() -> int:
    missing = [
        path.stem for path in sorted(FAILURES.glob("F-*.md"))
        if not re.search(r"^caught_by:", path.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    print(f"без caught_by: {len(missing)}")
    for name in missing[:10]:
        print("  -", name)
    return 0 if not missing else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="чем пойман отказ")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return check() if args.check else fill()


if __name__ == "__main__":
    sys.exit(main())
