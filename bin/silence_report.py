"""silence_report — почему прогон закончился без заявления.

Метрика C-0212 показала: 17 прогонов из 39 не дали ни заявления, ни вердикта. Здесь эти прогоны
разбираются по причинам, выводимым из журнала, а не по догадке:

  шаги-кончились   — бюджет шагов исчерпан, заявления не было;
  упирался-в-файл  — больше половины вызовов read/search одного и того же файла;
  искал-и-не-нашёл — search возвращал 0 совпадений в большинстве вызовов;
  отказа-не-было   — BLOCKED не пытался, хотя бюджет кончился (наш дефект, F-0034);
  прочее.

    python bin/silence_report.py     # research/outputs/silence-report.txt
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, ".")
from bin import accept  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
JOURNALS = ROOT / "runs" / "accept"


def calls(records) -> list[str]:
    return [rest for kind, rest in accept.events(records) if kind == "tool/call"]


def results(records) -> list[str]:
    return [rest for kind, rest in accept.events(records) if kind == "tool/result"]


def classify(records, tools: list[str]) -> str:
    kinds = [kind for kind, _ in accept.events(records)]
    if "run/blocked" in kinds or "run/no-work" in kinds:
        return "заявил-отказ"
    steps = [rest for kind, rest in accept.events(records) if kind == "step"]
    empty = sum(1 for text in results(records) if "найдено 0" in text)
    called = calls(records)
    if not called:
        return "не-вызвал-инструментов"
    same_file = Counter(re.sub(r"^\w+\s+(\S+).*$", r"\1", call) for call in called)
    top_file, top_count = same_file.most_common(1)[0]
    if empty >= max(2, len(called) // 2):
        return "искал-и-не-нашёл"
    if top_count >= max(3, len(called) // 2):
        return "упирался-в-файл"
    if steps:
        return "шаги-кончились"
    return "прочее"


def main() -> int:
    series = list((ROOT / "lab/p27").glob("*.json")) + list((ROOT / "lab/p27/musique").glob("*.json"))
    tasks = {}
    for path in series:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for task in data.get("tasks", []):
            if "criterion" in task:
                tasks[task["id"]] = task
    refusal = json.loads((ROOT / "lab/p27/refusal/tasks.json").read_text(encoding="utf-8"))
    for task in refusal["tasks"]:
        tasks[task["id"]] = task

    lines = ["# Разбор прогонов без заявления", "",
             f"{'журнал':26} {'задача':30} причина"]
    reasons = Counter()
    total = 0
    for path in sorted(JOURNALS.glob("*.bin")):
        stem = path.stem
        match = re.match(r"^(?:p27|p27r2|refusal2?|refusal3|musique[3-7])-(.+)$", stem)
        if not match:
            continue
        name = match.group(1)
        task = None
        if name in tasks:
            task = tasks[name]
        elif name.isdigit():
            order = json.loads((ROOT / "lab/p27/musique/tasks.json").read_text(encoding="utf-8"))["tasks"]
            task = order[int(name)] if int(name) < len(order) else None
        if task is None:
            continue
        try:
            records, _tail, _problems = accept.parse_journal(path.read_bytes())
        except Exception:  # noqa: BLE001
            continue
        kinds = [kind for kind, _ in accept.events(records)]
        if "claim/anchored" in kinds:
            continue
        total += 1
        reason = classify(records, ["search", "read", "list"])
        reasons[reason] += 1
        lines.append(f"{stem[:26]:26} {task['id'][:30]:30} {reason}")

    lines += ["", "итог по причинам:"]
    for reason, count in reasons.most_common():
        lines.append(f"  {reason}: {count}")
    lines += [f"", f"всего прогонов без заявления: {total}",
              "# Причины выведены из журнала: число пустых результатов поиска, доля вызовов одного",
              "# файла, наличие шагов и попытки отказа. Это разбор, а не объяснение задним числом."]
    text = "\n".join(lines) + "\n"
    out = ROOT / "research" / "outputs" / "silence-report.txt"
    out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
