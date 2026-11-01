"""check_admin_inbox — находки не теряются и не приходят без формата.

Проверки:
  1) у каждой находки (кроме README и шаблона) есть обязательные поля: дата, проект, что случилось,
     где, предлагаю, чем проверю, статус;
  2) статус — из допустимого набора, и если он не «ожидает», есть решение и ссылка.

    python bin/check_admin_inbox.py
    python bin/check_admin_inbox.py --self-test
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "lab" / "admin-inbox"
REQUIRED = ["дата:", "проект:", "что случилось:", "где:", "предлагаю:", "чем проверю:", "статус:"]
STATUSES = {"ожидает", "принято", "отклонено", "отложено"}


def findings() -> list[Path]:
    if not INBOX.exists():
        return []
    return [
        path for path in sorted(INBOX.glob("*.md"))
        if path.name not in {"README.md", "_template.md"}
    ]


def problems_for(paths: list[Path]) -> list[str]:
    problems = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        missing = [field for field in REQUIRED if field not in text]
        if missing:
            problems.append(f"{path.name}: нет полей {', '.join(field.rstrip(':') for field in missing)}")
            continue
        match = re.search(r"статус:\s*(\S+)", text)
        status = match.group(1).strip("*` ") if match else ""
        if status not in STATUSES:
            problems.append(f"{path.name}: статус {status!r} вне {sorted(STATUSES)}")
        elif status != "ожидает" and "решение админа:" not in text:
            problems.append(f"{path.name}: статус {status}, но нет решения админа")
    return problems


def self_test() -> int:
    tmp = ROOT / "lab" / "admin-inbox" / "_selftest.md"
    tmp.write_text("дата: 2026-11-01\nпроект: x\nчто случилось: y\n", encoding="utf-8")
    try:
        found = problems_for([tmp])
    finally:
        tmp.unlink(missing_ok=True)
    if not found:
        print("[FAIL] self-test: находка без полей не отвергнута")
        return 1
    print(f"[ok] self-test: {len(found)} отказ(ов) на находку без полей")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--self-test" in args:
        return self_test()
    if not INBOX.exists():
        print("[FAIL] нет каталога lab/admin-inbox")
        return 1
    paths = findings()
    problems = problems_for(paths)
    waiting = sum(1 for path in paths if "статус: ожидает" in path.read_text(encoding="utf-8").lower())
    for problem in problems:
        print(f"[FAIL] {problem}")
    if problems:
        return 1
    print(f"[ok] находок: {len(paths)}, ожидают решения: {waiting}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
