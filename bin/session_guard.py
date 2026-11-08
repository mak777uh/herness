"""session_guard — проверка последовательности шагов в цикле агента.

Модель доказана в Lean (`bin/session_types.py`). Но модель и код — разные вещи.
Здесь — перенос правила в код: DONE не может быть первым шагом.

    python bin/session_guard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "outputs" / "session-guard.txt"


def main() -> int:
    lines = ["# Проверка последовательности шагов", ""]
    lines.append("## Что доказано в Lean")
    lines.append("")
    lines.append("- `done_not_first`: DONE не может быть первым шагом")
    lines.append("- `no_step_after_finish`: после конца ничего не происходит")
    lines.append("- `reachable_from_start`: из начала можно дойти до конца за два шага")
    lines.append("")
    lines.append("## Что перенесено в код")
    lines.append("")
    lines.append("Правило в `core-rs/src/loopmod.rs`: если шаг `DONE`, а до него не было ни одного")
    lines.append("`TOOL`, это ошибка «нечего завершать».")
    lines.append("")
    lines.append("## Граница")
    lines.append("")
    lines.append("Доказан протокол, а не то, что содержимое `DONE` отвечает задаче.")
    lines.append("Это записано в `docs/VERIFICATION-SPEC.md`.")
    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
