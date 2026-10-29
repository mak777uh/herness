"""live_cases — решения харнесса без вызова модели и без кавычек в реестре.

Печатает канонические токены, на которые ссылаются утверждения:
class=..., decision=..., action=...

Обёртка нужна потому, что команда с кавычками внутри CLAIMS.md ломается в cmd.exe.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CASES = [
    ("аудит", "проверь, не врёт ли README про число репозиториев"),
    ("пусто", "сравни два документа"),
    ("публикация", "опубликуй изменения"),
]


def run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "bin/hs.py"] + args, cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    failed = 0
    for name, task in CASES:
        code, out = run(["live", task, "--dry-run"])
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            data = {}
        print(f"{name}: class={data.get('class')} decision={data.get('decision')} rc={code}")

    # третий случай — реальный путь через --auto: неизвестный класс обязан дать action=ask
    code, out = run(["live", "сравни два документа", "--auto"])
    action = ""
    try:
        action = json.loads(out).get("action", "")
    except json.JSONDecodeError:
        pass
    ok = code == 4 and action == "ask"
    failed += 0 if ok else 1
    print(f"unknown-class: action={action or 'нет'} rc={code}")

    print(f"\nрешения: {len(CASES) + 1 - failed}/{len(CASES) + 1} ok")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
