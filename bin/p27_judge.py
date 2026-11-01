"""p27_judge — сверить ответ прогона с эталоном из lab/p27/dataset.json.

Правило берётся из задачи, а не из моего вкуса:
  * `any_of` — задача просила «утверждение типа X», поэтому верен ЛЮБОЙ номер этого типа
    (решение владельца: определять по контексту задачи);
  * `exact` — задача называла номер, поэтому обязаны совпасть тип и команда проверки из реестра.

    python bin/p27_judge.py <task-id> <журнал.bin>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import accept  # noqa: E402

DATASET = ROOT / "lab" / "p27" / "dataset.json"


def answer_of(journal: Path) -> str:
    records, _tail, _problems = accept.parse_journal(journal.read_bytes())
    answers = [rest for kind, rest in accept.events(records) if kind == "run/end"]
    return answers[-1] if answers else ""


def judge(task: dict, answer: str) -> tuple[bool, str]:
    ids = re.findall(r"C-\d{4}", answer)
    if not ids:
        return (False, "в ответе нет номера утверждения")
    if task["judge"] == "any_of":
        key = set(task["answer_key"])
        hit = [stamp for stamp in ids if stamp in key]
        return (bool(hit), f"назван {ids[0]}; в ключе типа — {len(key)} номеров, попадание: {hit[:3]}")
    key = task["answer_key"]
    if ids[0] != key["id"]:
        return (False, f"назван {ids[0]}, ожидался {key['id']}")
    need_type, need_cmd = key["type"], key["command"]
    type_ok = need_type.lower() in answer.lower()
    command = need_cmd.split()[0] if need_cmd else ""
    command_ok = bool(command) and command in answer
    return (
        type_ok and command_ok,
        f"тип {'есть' if type_ok else 'НЕ назван'}, команда {'есть' if command_ok else 'НЕ названа'}",
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if len(argv) < 2:
        print("p27_judge <task-id> <журнал.bin>", file=sys.stderr)
        return 2
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    task = next((item for item in data["tasks"] if item["id"] == argv[0]), None)
    if task is None:
        print(f"нет задачи {argv[0]}", file=sys.stderr)
        return 2
    journal = Path(argv[1])
    if not journal.exists():
        print(f"нет журнала {journal}", file=sys.stderr)
        return 2
    ok, detail = judge(task, answer_of(journal))
    print(f"{task['id']}: {'верно' if ok else 'НЕВЕРНО'} — {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
