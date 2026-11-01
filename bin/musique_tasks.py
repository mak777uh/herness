"""musique_tasks — 6 задач из MuSiQue dev с человеческой разметкой ответа и поддержки.

Ключ берётся из данных: `answer` (и `answer_aliases`) для ответа, `is_supporting` для абзацев.
Порог судейства по поддержке объявляется заранее (support_f1 >= 0.5), а не подбирается после.

    python bin/musique_tasks.py            # записать lab/p27/musique/tasks.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "lab" / "p27" / "musique" / "dev.jsonl"
OUT = ROOT / "lab" / "p27" / "musique" / "tasks.json"
TASKS = 6
SUPPORT_F1_MIN = 0.5


def main() -> int:
    if not DATA.exists():
        print(f"нет данных: {DATA} (скачать bin/fetch_url.py)", file=sys.stderr)
        return 2
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    picked = []
    for row in rows:
        paragraphs = row.get("paragraphs") or []
        support = [index for index, item in enumerate(paragraphs) if item.get("is_supporting")]
        if not row.get("answerable", True):
            continue
        if len(paragraphs) != 20 or not (2 <= len(support) <= 4):
            continue
        picked.append((row, support))
        if len(picked) == TASKS:
            break

    tasks = []
    for row, support in picked:
        tasks.append(
            {
                "id": f"T-musique-{row['id']}",
                "question": row["question"],
                "answer": row["answer"],
                "answer_aliases": row.get("answer_aliases", []),
                "support_idx": support,
                "support_f1_min": SUPPORT_F1_MIN,
                "judge": "answer_match_and_support_f1",
                "task": (
                    f"В каталоге /mnt лежат 20 файлов p01.md … p20.md. Ответь на вопрос и укажи, "
                    f"какие файлы подтверждают ответ.\nВопрос: {row['question']}\n"
                    "Ответь двумя строками: 1) ответ; 2) номера подтверждающих файлов через запятую."
                ),
                "criterion": {
                    "task": f"ответить на вопрос MuSiQue {row['id']} с указанием источников",
                    "comment": (
                        "Собрано bin/musique_tasks.py из MuSiQue dev (CC BY 4.0). Ключ ответа и "
                        "поддержки — человеческая разметка набора. Порог support_f1 объявлен до прогона."
                    ),
                    "require_status": "done",
                    "require_commit": True,
                    "require_events": ["claim/anchored"],
                    "max_steps": 20,
                    "max_allowance": 0.05,
                    "max_repeat_ratio": 0.35,
                    "max_calls_without_claim": 20,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": r"p\d{2}",
                },
            }
        )

    data = {
        "schema": 1,
        "source": "MuSiQue-Ans dev (CC BY 4.0, github.com/StonyBrookNLP/musique)",
        "sha256_dev": "15fa63794d18a94ce12411aca6e2327e65b6e83b0b1490efab3f1962e48abf3b",
        "note": (
            "Ответ проверяется по answer/answer_aliases, поддержка — по is_supporting: "
            "support_f1 = 2*|pred∩gold|/(|pred|+|gold|), порог объявлен заранее."
        ),
        "tasks": tasks,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"записано: {OUT.relative_to(ROOT)}; задач {len(tasks)}")
    for task in tasks:
        print(f"  {task['id']}: ответ «{task['answer']}», поддерживают {task['support_idx']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
