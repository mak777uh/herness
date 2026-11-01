"""history_tasks4 — задачи с удержанием нескольких объектов и структуры ответа.

Ответ собирается из нескольких файлов сразу, поэтому проваливается не поиск, а удержание:
нужно прочитать несколько объектов и не потерять соответствие. Ключ считается из тех же файлов.

    python bin/history_tasks4.py --emit
    python bin/history_tasks4.py --judge
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
CRITERIA = ROOT / "accept" / "history4"
INDEX = ROOT / "runs" / "accept" / "history4-index.json"


def failure_classes() -> dict[str, str]:
    out = {}
    for path in sorted((ROOT / "lab" / "failures").glob("F-*.md")):
        match = re.search(r"^class:\s*(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            out[path.stem] = match.group(1)
    return out


def commits() -> list[tuple[str, str]]:
    path = ROOT / "history" / "gitlog.txt"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if " " in line:
            sha, subject = line.split(" ", 1)
            out.append((sha, subject.strip()))
    return out


def emit() -> int:
    tasks = []
    classes = failure_classes()

    picks = [stem for stem in ("F-0032", "F-0033", "F-0034") if stem in classes]
    if len(picks) == 3:
        answer = ", ".join(classes[stem] for stem in picks)
        tasks.append(
            {
                "id": "H4-three-classes",
                "task": (
                    "В failures есть файлы F-0032, F-0033, F-0034. Назови их классы в этом порядке "
                    "через запятую, одним словом на файл."
                ),
                "answer": answer,
                "criterion": {
                    "task": "назвать классы трёх отказов по порядку",
                    "require_status": "done",
                    "require_commit": True,
                    "max_steps": 20,
                    "max_allowance": 0.05,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": "F-003",
                    "min_objects": 3,
                },
            }
        )

    # Слово выбирается по данным: самое частое в описаниях коммитов, но не служебное.
    stop = {"и", "в", "на", "с", "по", "the", "a", "to", "of", "for", "and", "add", "fix"}
    words = Counter()
    for _sha, subject in commits():
        for token in subject.lower().replace(":", " ").split():
            token = token.strip("(),.;")
            if len(token) >= 5 and token not in stop:
                words[token] += 1
    word = next((token for token, count in words.most_common() if count >= 3), None)
    hits = [sha for sha, subject in commits() if word and word in subject.lower()][:4] if word else []
    if len(hits) >= 3:
        tasks.append(
            {
                "id": "H4-commit-word",
                "task": (
                    f"В history/gitlog.txt найди первые три коммита (сверху вниз), в описании которых есть "
                    f"слово «{word}», и ответь их хешами через запятую."
                ),
                "answer": ", ".join(hits[:3]),
                "items": hits[:3],
                "criterion": {
                    "task": f"назвать три коммита со словом {word}",
                    "require_status": "done",
                    "require_commit": True,
                    "max_steps": 20,
                    "max_allowance": 0.05,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": hits[0],
                    "min_objects": 2,
                },
            }
        )

    adrs_by_failure = {}
    for path in sorted((ROOT / "lab" / "failures").glob("F-*.md")):
        found = sorted(set(re.findall(r"ADR-\d{4}", path.read_text(encoding="utf-8"))))
        if found:
            adrs_by_failure[path.stem] = found
    if adrs_by_failure:
        union = sorted({adr for adrs in adrs_by_failure.values() for adr in adrs})
        names = ", ".join(sorted(adrs_by_failure))
        tasks.append(
            {
                "id": "H4-adr-union",
                "task": (
                    f"В failures у отказов {names} встречаются упоминания решений вида ADR-NNNN. Собери все "
                    "различные номера решений, которые упомянуты в этих файлах, и ответь ими через запятую "
                    "по возрастанию."
                ),
                "answer": ", ".join(union),
                "items": union,
                "criterion": {
                    "task": "собрать объединение упомянутых решений",
                    "require_status": "done",
                    "require_commit": True,
                    "max_steps": 24,
                    "max_allowance": 0.05,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": "ADR-",
                    "min_objects": 3,
                },
            }
        )

    counts = Counter(classes.values())
    ordered = [name for name, _ in counts.most_common(2)]
    if len(ordered) == 2:
        tasks.append(
            {
                "id": "H4-two-top",
                "task": (
                    "В failures посчитай классы всех отказов. Назови два самых частых класса в порядке "
                    "убывания частоты, через запятую."
                ),
                "answer": ", ".join(ordered),
                "items": ordered,
                "criterion": {
                    "task": "назвать два самых частых класса отказов",
                    "require_status": "done",
                    "require_commit": True,
                    "max_steps": 24,
                    "max_allowance": 0.05,
                    "must_not_call": ["write"],
                    "tools": ["search", "read", "list"],
                    "anchor_regex": re.escape(ordered[0]),
                    "min_objects": 3,
                },
            }
        )

    CRITERIA.mkdir(parents=True, exist_ok=True)
    for item in tasks:
        (CRITERIA / f"{item['id']}.json").write_text(
            json.dumps(item["criterion"], ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    INDEX.write_text(json.dumps(tasks, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"критериев: {len(tasks)}")
    for item in tasks:
        print(f"{item['id']}|{item['task']}")
    return 0


def judge() -> int:
    tasks = json.loads(INDEX.read_text(encoding="utf-8"))
    accepted = correct = 0
    rows = []
    for item in tasks:
        journal = ROOT / "runs" / "accept" / f"h4-{item['id']}.bin"
        if not journal.exists():
            rows.append(f"{item['id'][:22]:22} —")
            continue
        records, _tail, _problems = accept.parse_journal(journal.read_bytes())
        ok, _r = accept.check(item["criterion"], records)
        answers = [rest for kind, rest in accept.events(records) if kind == "run/end"]
        text = (answers[-1] if answers else "").lower()
        if item.get("items"):
            # Перечисление проверяем по составу: «0031, 0052» и «ADR-0031, ADR-0052» — один ответ (F-0041).
            hit = all(str(part).lower() in text for part in item["items"])
        else:
            hit = str(item["answer"]).lower() in text
        stall = any(k == "run/blocked" and "застой" in r for k, r in accept.events(records))
        loop = any(k == "run/blocked" and "петля" in r for k, r in accept.events(records))
        steps = sum(1 for kind, _ in accept.events(records) if kind == "step")
        accepted += 1 if ok else 0
        correct += 1 if hit else 0
        rows.append(
            f"{item['id'][:22]:22} {'PASS' if ok else 'FAIL':5} {'верно' if hit else 'НЕВЕРНО':8} "
            f"шагов {steps:>2}{' застой' if stall else ''}{' петля' if loop else ''}  ответ: {text[:60]}"
        )
    report = (
        "# Задачи с удержанием нескольких объектов\n\n"
        + "\n".join(rows)
        + f"\n\nпринято: {accepted} из {len(tasks)}; совпало с ключом: {correct} из {len(tasks)}\n"
    )
    (ROOT / "research" / "outputs" / "history4-baseline.txt").write_text(report, encoding="utf-8")
    print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="задачи с удержанием объектов")
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
