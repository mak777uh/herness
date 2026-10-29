"""Статистика использования инструментов по всем сессиям.

Считаем: долю сессий без вызовов, распределение числа вызовов и долю повторных
одинаковых команд — прокси избыточных вызовов внутри сессии.
"""

from __future__ import annotations

import json
import statistics as st
import subprocess
from collections import Counter
from pathlib import Path

SESSIONS = Path.home() / ".dsh" / "sessions"
OUT = Path(__file__).resolve().parents[1] / "research" / "sessions" / "TOOL-USE.md"


def scan(path: Path) -> tuple[int, list[str]]:
    proc = subprocess.Popen(["zstd", "-d", "-c", str(path)], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
    calls = 0
    commands: list[str] = []
    for line in proc.stdout:
        if '"tool/call"' not in line:
            continue
        calls += 1
        try:
            event = json.loads(line)
            args = event.get("data", {}).get("arguments") or "{}"
            parsed = json.loads(args) if isinstance(args, str) else args
            cmd = parsed.get("command") or parsed.get("file_path") or parsed.get("pattern") or ""
            if cmd:
                commands.append(str(cmd)[:200])
        except (json.JSONDecodeError, AttributeError):
            pass
    proc.wait()
    return calls, commands


def main() -> int:
    files = sorted(SESSIONS.rglob("*.zstd"))
    counts: list[int] = []
    total_calls = 0
    total_dupes = 0
    per_session_dupes: list[float] = []

    for i, path in enumerate(files, 1):
        calls, commands = scan(path)
        counts.append(calls)
        total_calls += calls
        dupe = sum(count - 1 for count in Counter(commands).values() if count > 1)
        total_dupes += dupe
        if calls:
            per_session_dupes.append(dupe / calls)
        if i % 50 == 0:
            print(f"... {i}/{len(files)}", flush=True)

    counts.sort()
    zero = sum(1 for c in counts if c == 0)
    med = st.median(counts)
    p90 = counts[int(len(counts) * 0.9)]
    lines = [
        "# TOOL-USE — как мы на самом деле пользуемся инструментами",
        "",
        f"Сессий: {len(counts)} (все в `~/.dsh/sessions`).",
        "",
        "| метрика | значение |",
        "|---|---|",
        f"| без вызовов инструментов | {zero} ({round(100 * zero / len(counts), 1)} %) |",
        f"| медиана вызовов на сессию | {med} |",
        f"| p90 вызовов | {p90} |",
        f"| максимум | {max(counts)} |",
        f"| всего вызовов | {total_calls} |",
        f"| повторных одинаковых команд | {total_dupes} ({round(100 * total_dupes / max(total_calls, 1), 1)} % от всех) |",
        f"| медиана доли повторов в сессии | {round(100 * st.median(per_session_dupes), 1) if per_session_dupes else 0} % |",
        "",
        "## Что это значит",
        "",
        "- Сессии без инструментов — это и есть натуральный L0: их нельзя не заметить при выборе уровня.",
        "- Повторные одинаковые команды — нижняя оценка избыточности: команда выполнена заново,",
        "  хотя результат уже был.",
        "- Тяжёлый хвост (p90) — место, где прячется цена; среднее здесь бесполезно.",
        "",
        "## Чего это не доказывает",
        "",
        "- Повтор команды не всегда избыточен: файл мог измениться между вызовами.",
        "- Доля L0 завышена: часть сессий — субагенты, которые только возвращают текст.",
        "- Это распределение нашего прошлого, а не будущего потока.",
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nзаписано: {OUT}")
    print(f"сессий={len(counts)} zero={zero} median={med} p90={p90} "
          f"calls={total_calls} dupes={total_dupes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
