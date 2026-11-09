"""Полный анализ репозитория: числа из фактов, а не из документации.

Зачем: в docs/CONTINUE.md и в сообщении владельцу стоят числа, которые
разошлись с файлами (например «NOT-CLAIMED.md — 29 записей» при 14 живых).
Анализ должен называть факт и расхождение, а не повторять документацию.

    python bin/repo_report.py
    python bin/repo_report.py --json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def count_rows(path: pathlib.Path, pattern: str) -> int:
    if not path.exists():
        return -1
    text = path.read_text(encoding="utf-8", errors="replace")
    return len(re.findall(pattern, text, re.M))


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    return (result.stdout or "").strip()


def lines_of(glob: str) -> int:
    files = git("ls-files", glob).splitlines()
    total = 0
    for name in files:
        path = ROOT / name
        if path.is_file():
            try:
                total += len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                pass
    return total


def main(argv: list[str]) -> int:
    facts = {
        "коммитов": int(git("rev-list", "--count", "HEAD") or 0),
        "первый коммит": git("log", "--reverse", "--format=%ad", "--date=short").splitlines()[:1],
        "последний коммит": git("log", "-1", "--format=%ad", "--date=short"),
        "файлов в git": len(git("ls-files").splitlines()),
        "Python строк": lines_of("*.py"),
        "Rust строк": lines_of("*.rs"),
        "Markdown строк": lines_of("*.md"),
        "утверждений C-": count_rows(ROOT / "CLAIMS.md", r"^\| C-\d{4}"),
        "не-утверждений NC-": count_rows(ROOT / "NOT-CLAIMED.md", r"^\| `NC-\d+`"),
        "требований R-": count_rows(ROOT / "REQUIREMENTS.md", r"^## R-\d{4}"),
        "ADR": len(list((ROOT / "docs").glob("ADR-*.md"))),
        "гейтов в hs.py": count_rows(ROOT / "bin" / "hs.py", r'\("[\w\- ]+", gate_\w+\)'),
        "скриптов bin/": len(list((ROOT / "bin").glob("*.py"))),
        "тестов tests/": len(list((ROOT / "tests").glob("*.py"))),
        "исследований research/*.md": len(list((ROOT / "research").glob("*.md"))),
    }
    facts["первый коммит"] = facts["первый коммит"][0] if facts["первый коммит"] else "?"

    # Заявленные в документации числа — для сверки.
    declared = {}
    continue_md = ROOT / "docs" / "CONTINUE.md"
    if continue_md.exists():
        text = continue_md.read_text(encoding="utf-8", errors="replace")
        for label, pattern in (("NOT-CLAIMED", r"NOT-CLAIMED\.md`? — (\d+)"),
                               ("CLAIMS", r"CLAIMS\.md`? — (\d+)"),
                               ("требований", r"(\d+) записей с якорями")):
            match = re.search(pattern, text)
            if match:
                declared[label] = int(match.group(1))

    if "--json" in argv:
        print(json.dumps({"факты": facts, "заявлено в docs/CONTINUE.md": declared},
                         ensure_ascii=False, indent=1))
        return 0

    print("=== ФАКТЫ (из файлов и git) ===")
    for key, value in facts.items():
        print(f"  {key:28} {value}")

    if declared:
        print()
        print("=== РАСХОЖДЕНИЯ С docs/CONTINUE.md ===")
        pairs = {"NOT-CLAIMED": "не-утверждений NC-", "CLAIMS": "утверждений C-",
                 "требований": "требований R-"}
        for label, claimed in declared.items():
            actual = facts.get(pairs.get(label, ""), -1)
            mark = "ok  " if actual == claimed else "FAIL"
            print(f"  {mark} {label:14} заявлено {claimed:>4}, фактически {actual:>4}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
