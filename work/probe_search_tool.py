"""Что реально возвращает search /mnt C-0295 в комнате.

Модель искала C-0295 девять раз и не нашла, хотя строка в CLAIMS.md есть.
Нужно увидеть ответ инструмента, а не гадать.

    python work/probe_search_tool.py
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(r"C:\111\herness")


def main() -> int:
    # Прогон с задачей, которая заставляет искать и печатает результат в журнале.
    criteria = {
        "comment": "Проба: что возвращает search по C-0295",
        "task": "Найди C-0295 в CLAIMS.md и назови его тип. Ответь одним словом.",
        "require_status": "done",
        "max_steps": 4,
        "max_allowance": 0.2,
        "must_not_call": ["write"],
        "tools": ["search", "list", "read"],
    }
    path = ROOT / "accept" / "_probe-c0295.json"
    path.write_text(json.dumps(criteria, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    try:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(ROOT / "core-rs" / "accept-run.ps1"),
             "-Mode", "loop-bridge", "-Kernel", "vmlinuz-own-hardened2", "-Net",
             "-TimeoutSec", "180", "-Criteria", "accept/_probe-c0295.json",
             "-Task", criteria["task"]],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(((result.stdout or "") + (result.stderr or "")).strip()[-500:])
    finally:
        path.unlink(missing_ok=True)

    sys.path.insert(0, str(ROOT / "bin"))
    from accept import parse_journal  # noqa: E402

    recs, _, _ = parse_journal((ROOT / "runs" / "accept" / "journal.bin").read_bytes())
    print("\n=== журнал ===")
    for kind, payload in recs:
        text = str(payload)
        if kind == "tool/result" or "model/reply" in text:
            print(f"{kind}: {text[:300]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
