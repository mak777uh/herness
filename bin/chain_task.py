"""chain_task — задача, где каждый шаг зависит от предыдущего.

Смысл: проверить бюджет, застой и продление там, где они действительно ограничивают. Задача
строится цепочкой: слово A находит файлы, в них слово B сужает до одного, в нём строка со словом C
даёт ответ. Каждый следующий шаг невозможен без предыдущего.

    python bin/chain_task.py --emit
    python bin/chain_task.py --judge
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
CRITERIA = ROOT / "accept" / "chain"
INDEX = ROOT / "runs" / "accept" / "chain-index.json"


def lines_by_file() -> dict[str, list[str]]:
    out = {}
    for path in sorted(DUMPS.glob("*.txt")):
        out[path.stem] = path.read_text(encoding="utf-8").splitlines()
    return out


def build_chain() -> tuple[str, str, list[str], str, str]:
    """A находит файлы по строкам; B сужает до одного; C даёт строку ответа."""
    files = lines_by_file()
    counts: Counter = Counter()
    for lines in files.values():
        seen = set()
        for line in lines:
            for word in re.findall(r"[A-Za-z]{5,}", line):
                seen.add(word.lower())
        counts.update(seen)
    for word_a, count_a in sorted(counts.items(), key=lambda item: (item[1], item[0])):
        if not 3 <= count_a <= 8:
            continue
        group = [name for name, lines in files.items()
                 if any(word_a in line.lower() for line in lines)]
        if len(group) != count_a:
            continue
        # B ищем среди слов, которые есть в части группы, но не во всей.
        candidates: Counter = Counter()
        for name in group:
            seen = set()
            for line in files[name]:
                for word in re.findall(r"[A-Za-z]{6,}", line):
                    seen.add(word.lower())
            candidates.update(seen)
        for word_b, hits in sorted(candidates.items(), key=lambda item: (item[1], item[0])):
            if word_b == word_a or not 1 <= hits < len(group):
                continue
            narrowed = [name for name, lines in files.items()
                        if any(word_b in line.lower() for line in lines)]
            if len(narrowed) != 1:
                continue
            name = narrowed[0]
            for index, line in enumerate(files[name], 1):
                if not line.startswith("tool/result"):
                    continue
                for word_c in re.findall(r"[A-Za-z]{7,}", line):
                    word = word_c.lower()
                    if word in (word_a, word_b):
                        continue
                    hits = sum(1 for other in files[name] if word in other.lower())
                    if hits != 1:
                        continue
                    return word_a, word_b, group, name, word
    raise RuntimeError("цепочка не собралась")


def emit() -> int:
    word_a, word_b, group, name, word_c = build_chain()
    criterion = {
        "task": f"цепочка: {word_a} → {word_b} → {word_c}",
        "require_status": "done",
        "require_commit": True,
        "max_steps": 20,
        "max_allowance": 0.20,
        "must_not_call": ["write"],
        "tools": ["search", "read", "list"],
        "anchor_regex": name,
        "min_objects": 3,
    }
    item = {
        "id": "CH1-chain",
        "task": (
            "В каталоге runs/dump лежат выгрузки прогонов. Выполни цепочку по шагам и ответь итогом:\n"
            f"1) найди выгрузки, где встречается слово «{word_a}»;\n"
            f"2) среди них найди те, где есть ещё и слово «{word_b}» — таких должна быть одна;\n"
            f"3) в этой выгрузке найди строку со словом «{word_c}» и назови её номер.\n"
            "Ответь одной строкой: имя выгрузки, номер строки."
        ),
        "answer": f"{name}",
        "items": [name],
        "word": word_c,
        "criterion": criterion,
    }
    CRITERIA.mkdir(parents=True, exist_ok=True)
    (CRITERIA / f"{item['id']}.json").write_text(
        json.dumps(criterion, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    INDEX.write_text(json.dumps([item], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{item['id']}|{item['task'].replace(chr(10), ' ')}")
    print(f"ключ: {name}; промежуточные: {word_a} → {len(group)} файлов → {word_b} → {word_c}")
    return 0


def judge() -> int:
    items = json.loads(INDEX.read_text(encoding="utf-8"))
    rows = []
    accepted = correct = 0
    for item in items:
        journal = ROOT / "runs" / "accept" / f"chain-{item['id']}.bin"
        if not journal.exists():
            rows.append(f"{item['id']}: журнала нет")
            continue
        records, _t, _p = accept.parse_journal(journal.read_bytes())
        ok, _r = accept.check(item["criterion"], records)
        answers = [rest for kind, rest in accept.events(records) if kind == "run/end"]
        text = (answers[-1] if answers else "").lower()
        finished = "шаги кончились" not in text and "провайдер не дал" not in text
        hit = finished and all(str(part).lower() in text for part in item["items"])
        steps = sum(1 for kind, _ in accept.events(records) if kind == "step")
        stall = any(k == "run/blocked" and "застой" in r for k, r in accept.events(records))
        accepted += 1 if ok else 0
        correct += 1 if hit else 0
        rows.append(
            f"{item['id']} {'PASS' if ok else 'FAIL':5} {'верно' if hit else 'НЕВЕРНО':8} "
            f"шагов {steps}{' застой' if stall else ''}  ответ: {text[:80]}"
        )
    report = "# Цепочка с зависимостью шагов\n\n" + "\n".join(rows) + f"\n\nпринято: {accepted}; верно: {correct}\n"
    (ROOT / "research" / "outputs" / "chain-task.txt").write_text(report, encoding="utf-8")
    print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="цепочка с зависимостью шагов")
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
