"""p27_dataset — собрать набор задач и эталонные ответы из истории репозитория.

Зачем без человека: эталон для наших задач уже лежит в реестре `CLAIMS.md` — там у каждого
утверждения есть номер, тип и команда проверки. Значит «правильный ответ» можно не придумывать,
а **вывести**: для задачи «найди утверждение типа X» верны все утверждения этого типа, для задачи
«найди C-0004» — сам C-0004 и его поля.

Это важно методологически: эталон не мой вкус, а содержимое реестра, то есть его можно
перепроверить командой, а не доверием.

    python bin/p27_dataset.py            # записать lab/p27/dataset.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "CLAIMS.md"
OUT = ROOT / "lab" / "p27" / "dataset.json"

TYPES = ("proof", "test", "statistics", "observation", "judgment")
# Сколько задач каждого вида: 5 «найди тип» (эталон — множество) и 5 «найди номер» (эталон — один).
PER_TYPE = 1
EXACT_IDS = ("C-0004", "C-0021", "C-0112", "C-0122", "C-0179")


def parse_claims() -> dict[str, dict]:
    """Номер → поля. Разбор тот же, что у check_artifacts: 7 колонок."""
    out: dict[str, dict] = {}
    for line in CLAIMS.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| C-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            continue
        claim_id, text, kind, command = cells[0], cells[1], cells[2], cells[3]
        out[claim_id] = {"id": claim_id, "text": text, "type": kind, "command": command.strip("`")}
    return out


def base_criterion(task: str, anchor: str) -> dict:
    return {
        "task": task,
        "comment": (
            "Собрано bin/p27_dataset.py из реестра CLAIMS.md. Условия: статус done, опора, "
            "закрытый журнал, потолки шагов и денег, порог барахтания 0.35, опора при 10+ вызовах, "
            "запись запрещена."
        ),
        "require_status": "done",
        "require_commit": True,
        "require_events": ["claim/anchored"],
        "max_steps": 12,
        "max_allowance": 0.05,
        "max_repeat_ratio": 0.35,
        "max_calls_without_claim": 10,
        "must_not_call": ["write"],
        "tools": ["search", "read", "list"],
        "anchor_regex": anchor,
    }


def build() -> dict:
    claims = parse_claims()
    tasks: list[dict] = []

    for wanted in TYPES:
        pool = [claim for claim in claims.values() if claim["type"] == wanted]
        if not pool:
            continue
        # Эталон — множество номеров: задача просит любое утверждение этого типа, поэтому любой
        # из них верен, а «другой номер» здесь не ошибка (решение владельца: по контексту задачи).
        chosen = pool[0]
        tasks.append(
            {
                "id": f"T-type-{wanted}",
                "task": (
                    f"Найди в /mnt/CLAIMS.md утверждение типа `{wanted}` и назови его id вида C-1234. "
                    "Ответь одной строкой: id и цитата."
                ),
                "judge": "any_of",
                "answer_key": sorted(claim["id"] for claim in pool),
                "hint": f"например {chosen['id']}: {chosen['text'][:60]}",
                "criterion": base_criterion(
                    f"найти утверждение типа {wanted}", r"C-\d{4}"
                ),
                "source": "CLAIMS.md (колонка типа)",
            }
        )

    for claim_id in EXACT_IDS:
        claim = claims.get(claim_id)
        if not claim:
            continue
        tasks.append(
            {
                "id": f"T-exact-{claim_id}",
                "task": (
                    f"Найди в /mnt/CLAIMS.md утверждение {claim_id}, назови его тип и команду проверки. "
                    "Ответь одной строкой: тип и команда."
                ),
                "judge": "exact",
                "answer_key": {
                    "id": claim_id,
                    "type": claim["type"],
                    "command": claim["command"],
                },
                # Здесь номер известен из задачи, поэтому опора — тип и команда, а не номер.
                "hint": f"в реестре: тип {claim['type']}, команда {claim['command']}",
                "criterion": base_criterion(
                    f"найти утверждение {claim_id}, назвать тип и команду", claim_id
                ),
                "source": "CLAIMS.md (строка утверждения)",
            }
        )

    return {
        "schema": 1,
        "built_from": "CLAIMS.md",
        "note": (
            "Эталон выведен из реестра, а не задан человеком. Проверка: для any_of — названный номер "
            "обязан быть в answer_key; для exact — тип и команда обязаны совпасть с реестром."
        ),
        "tasks": tasks,
    }


def main() -> int:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    by_judge: dict[str, int] = {}
    for task in data["tasks"]:
        by_judge[task["judge"]] = by_judge.get(task["judge"], 0) + 1
    print(f"записано: {OUT.relative_to(ROOT)}; задач {len(data['tasks'])} "
          f"({', '.join(f'{k}: {v}' for k, v in sorted(by_judge.items()))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
