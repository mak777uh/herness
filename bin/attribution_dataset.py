"""attribution_dataset — задачи на атрибуцию с ключом, выведенным машинно из файлов репозитория.

Зачем без внешнего набора: MuSiQue из этого окружения недоступен (C-0198), а гипотеза H-0002
просит число. Ключ здесь не «мнение», а результат `grep` по тем же файлам, которые попадут в
комнату: если утверждение C-0122 встречается в трёх файлах, то правильный ответ — ровно эти три.

    python bin/attribution_dataset.py            # записать lab/p27/attribution.json

Что именно проверяется: модель должна не просто найти утверждение, а перечислить ВСЕ источники,
где оно есть, и не добавить лишних. Это ближе к атрибуции, чем «найди и назови».
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "lab" / "p27" / "attribution.json"

# Файлы, которые копируются в комнату. Набор фиксирован, чтобы ключ и комната совпадали.
SOURCES = [
    "CLAIMS.md",
    "NOT-CLAIMED.md",
    "README.md",
    "docs/ADR-0049-acceptance-outside-room.md",
    "docs/ADR-0050-loop-prompt-history.md",
    "docs/ADR-0051-resume-after-crash.md",
    "research/P29-TRIAGE-2026-11-01.md",
    "docs/prompts/P28-series-decisions.md",
]

CLAIM_IDS = ["C-0021", "C-0112", "C-0162", "C-0178", "C-0186", "C-0196"]


def main() -> int:
    texts = {}
    for name in SOURCES:
        path = ROOT / name
        if not path.exists():
            print(f"нет файла {name}", file=sys.stderr)
            return 2
        texts[name] = path.read_text(encoding="utf-8", errors="replace")

    tasks = []
    for claim_id in CLAIM_IDS:
        pattern = re.compile(rf"\b{re.escape(claim_id)}\b")
        key = sorted(name for name, text in texts.items() if pattern.search(text))
        if not key:
            print(f"{claim_id}: нет ни в одном файле — пропущено", file=sys.stderr)
            continue
        tasks.append(
            {
                "id": f"T-attr-{claim_id}",
                "claim": claim_id,
                "task": (
                    f"Утверждение {claim_id} упоминается в нескольких файлах рабочего каталога /mnt. "
                    "Перечисли ВСЕ файлы, где оно встречается, полными путями относительно /mnt. "
                    "Ответь одной строкой: пути через запятую."
                ),
                "answer_key": key,
                "sources_in_room": SOURCES,
                "method": "ключ = grep по тем же файлам, которые лежат в комнате",
                "criterion": {
                    "task": f"перечислить все файлы, где встречается {claim_id}",
                    "comment": (
                        "Собрано bin/attribution_dataset.py. Ключ выведен поиском по файлам комнаты, "
                        "а не назначен человеком. Опора — номер утверждения."
                    ),
                    "require_status": "done",
                    "require_commit": True,
                    "require_events": ["claim/anchored"],
                    "max_steps": 14,
                    "max_allowance": 0.05,
                    "max_repeat_ratio": 0.35,
                    "max_calls_without_claim": 14,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": claim_id.replace("C-", "C-"),
                },
            }
        )

    data = {
        "schema": 1,
        "built_from": "файлы репозитория (SOURCES)",
        "note": (
            "Ключ атрибуции выведен машинно: множество файлов, в которых встречается номер "
            "утверждения. Проверка ответа — сравнение множеств, а не суждение."
        ),
        "tasks": tasks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"записано: {OUT.relative_to(ROOT)}; задач {len(tasks)}")
    for task in tasks:
        print(f"  {task['id']}: {len(task['answer_key'])} источников — {', '.join(task['answer_key'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
