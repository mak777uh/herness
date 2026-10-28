#!/usr/bin/env python3
"""mine_report — превращает digest.json в читаемый markdown."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "research" / "sessions" / "digest.json"
DST = ROOT / "research" / "sessions" / "DIGEST.md"


def main() -> int:
    d = json.loads(SRC.read_text(encoding="utf-8"))
    lines = [
        "# DIGEST — что реально происходило в журналах харнесса",
        "",
        f"Сгенерировано: {d['generated_at']} из `~/.dsh/sessions/**/session.v4.jsonl.zstd`.",
        "",
        "## Объём",
        "",
        "| метрика | значение |",
        "|---|---|",
        f"| сессий | {d['sessions']} |",
        f"| сообщений пользователя | {d['user_messages']} |",
        f"| сессий-агентов / сессий-пользователя | {d['origins'].get('subagent', 0)} / {d['origins'].get('user', 0)} |",
        "",
        "## Инструменты: что реально используется",
        "",
        "| инструмент | вызовов | доля ошибок | p95, мс |",
        "|---|---|---|---|",
    ]
    for t in d["tools"][:15]:
        lines.append(f"| `{t['tool']}` | {t['calls']} | {t['fail_pct']}% | {t['p95_ms']} |")

    lines += ["", "## Темы задач (по сообщениям пользователя)", "", "| тема | упоминаний |", "|---|---|"]
    for topic, n in d["topics"]:
        lines.append(f"| {topic} | {n} |")

    lines += ["", "## Боли: повторяющиеся ошибки", ""]
    if d["top_errors"]:
        lines += ["| повторов | сигнатура |", "|---|---|"]
        for sig, n in d["top_errors"][:15]:
            lines.append(f"| {n} | `{sig}` |")
    else:
        lines.append("_ошибок в результатах инструментов не найдено — подозрительно, значит детектор слаб_")

    lines += ["", "## Рабочие каталоги", "", "| сессий | каталог |", "|---|---|"]
    for cwd, n in d["top_cwds"]:
        lines.append(f"| {n} | `{cwd}` |")

    lines += ["", "## Что это не доказывает", "",
              "- Что журналы покрывают всю работу: они покрывают только DSH.",
              "- Что частые инструменты необходимы: частота ≠ необходимость.",
              "- Что ошибки посчитаны полно: детектор опирается на текст результата.",
              "",
              "Данные содержат личные сообщения — зона B/C по PUBLICATION-POLICY, в публичный репозиторий не едут."]

    DST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"записано: {DST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
