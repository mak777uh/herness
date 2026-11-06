"""long_task — задача, которая по построению требует десятков шагов.

Смысл: проверить прогон, где модель работает долго. До сих пор ни одна задача не требовала больше
двадцати шагов, и механизмы (бюджет, застой, петля) не проверялись под нагрузкой.

Задача: в runs/dump 93 выгрузки; нужно найти редкое слово, назвать число выгрузок с ним и
перечислить их имена. Одним поиском это не решается: поиск обрезается на сорока совпадениях,
а имена надо собрать из сводки по файлам.

    python bin/long_task.py --emit
    python bin/long_task.py --judge
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, ".")
from bin import accept  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DUMPS = ROOT / "runs" / "dump"
CRITERIA = ROOT / "accept" / "long"
INDEX = ROOT / "runs" / "accept" / "long-index.json"


def pick_word() -> tuple[str, list[str]]:
    counts: Counter = Counter()
    files: dict[str, set[str]] = {}
    for path in sorted(DUMPS.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        for word in set(re.findall(r"[A-Za-z]{7,}", text)):
            counts[word.lower()] += 1
            files.setdefault(word.lower(), set()).add(path.stem)
    # Слово, встречающееся ровно в трёх выгрузках: искать надо по всем, а ответ короткий.
    # Слово должно встречаться в строке задачи (run/start) и НЕ встречаться ни в каком другом
    # месте выгрузки: иначе поиск находит служебные строки и ответ размывается (F-0059).
    task_lines: dict[str, set[str]] = {}
    other: set[str] = set()
    for path in sorted(DUMPS.glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            words = {w.lower() for w in re.findall(r"[A-Za-z]{7,}", line)}
            if line.startswith("run/start: task:"):
                for word in words:
                    task_lines.setdefault(word, set()).add(path.stem)
            else:
                other |= words
    # Строгих кандидатов мало: старые журналы цитируют задачи друг друга. Берём слово, которое
    # встречается в строках задач и нигде больше, и предпочитаем то, у которого меньше выгрузок —
    # ответ должен быть коротким, а поиск всё равно идёт по всем 93 (F-0059).
    clean = [(word, sorted(stems)) for word, stems in task_lines.items() if word not in other]
    if not clean:
        raise RuntimeError("не нашлось слова, встречающегося только в строках задач")
    clean.sort(key=lambda item: (len(item[1]), item[0]))
    return clean[0]
    raise RuntimeError("не нашлось слова в трёх выгрузках")


def emit() -> int:
    word, names = pick_word()
    criterion = {
        "task": f"найти выгрузки со словом {word} и перечислить их",
        "require_status": "done",
        "require_commit": True,
        "max_steps": 40,
        "max_allowance": 0.20,
        "must_not_call": ["write"],
        "tools": ["search", "read", "list"],
        # Опора — имя первой выгрузки из ответа: оно есть и в ответе, и в сводке поиска.
        "anchor_regex": names[0],
    }
    item = {
        "id": "L1-rare-word",
        "task": (
            f"В каталоге runs/dump лежат 93 выгрузки прогонов. Найди, в скольких из них встречается "
            f"слово «{word}», и перечисли имена этих выгрузок без расширения. Ответь одной строкой: "
            "число, затем имена через запятую."
        ),
        "answer": f"{len(names)}",
        "items": [str(len(names))] + names,
        "criterion": criterion,
    }
    CRITERIA.mkdir(parents=True, exist_ok=True)
    (CRITERIA / f"{item['id']}.json").write_text(
        json.dumps(criterion, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    INDEX.write_text(json.dumps([item], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{item['id']}|{item['task']}")
    print(f"ключ: {item['answer']} — {', '.join(names)}")
    return 0


def judge() -> int:
    items = json.loads(INDEX.read_text(encoding="utf-8"))
    accepted = correct = 0
    rows = []
    for item in items:
        journal = ROOT / "runs" / "accept" / f"long-{item['id']}.bin"
        if not journal.exists():
            rows.append(f"{item['id']}: журнала нет")
            continue
        records, _tail, _problems = accept.parse_journal(journal.read_bytes())
        ok, _r = accept.check(item["criterion"], records)
        answers = [rest for kind, rest in accept.events(records) if kind == "run/end"]
        text = (answers[-1] if answers else "").lower()
        finished = "шаги кончились" not in text and "провайдер не дал" not in text
        hit = finished and all(str(part).lower() in text for part in item["items"])
        steps = sum(1 for kind, _ in accept.events(records) if kind == "step")
        accepted += 1 if ok else 0
        correct += 1 if hit else 0
        rows.append(
            f"{item['id']} {'PASS' if ok else 'FAIL':5} {'верно' if hit else 'НЕВЕРНО':8} "
            f"шагов {steps}  ответ: {text[:90]}"
        )
    report = "# Длинная задача\n\n" + "\n".join(rows) + f"\n\nпринято: {accepted} из {len(items)}; верно: {correct}\n"
    (ROOT / "research" / "outputs" / "long-task.txt").write_text(report, encoding="utf-8")
    print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="длинная задача")
    parser.add_argument("--emit", action="store_true")
    parser.add_argument("--judge", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.emit:
        return emit()
    if args.judge:
        return judge()
    print("укажи --emit или --judge", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
