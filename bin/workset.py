"""workset — ограниченный рабочий набор и архив (эксперимент E4 плана P33).

Правило: рабочий набор ограничен; вытесненный уходит в `archived`, остаётся искомым и
воскрешается. Удаления нет.

    python bin/workset.py --probe
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import build_registry as reg  # noqa: E402
from bin import preflight as pf  # noqa: E402

OUT = ROOT / "research" / "outputs" / "workset-check.txt"
LIMIT = 3


def main() -> int:
    rows = [json.loads(line) for line in reg.REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    lines = ["# Рабочий набор и архив", ""]

    # 1. Вытеснение: первые LIMIT остаются, остальные уходят в архив (не удаляются).
    workset = [dict(row) for row in rows]
    for row in workset[LIMIT:]:
        row["status"] = "archived"
    active = [row["id"] for row in workset if row["status"] == "active"]
    archived = [row["id"] for row in workset if row["status"] == "archived"]
    ok_limit = len(active) <= LIMIT and len(active) + len(archived) == len(rows)
    lines.append(f"{'рабочий набор':22} {active} (лимит {LIMIT}) — {'ok' if ok_limit else 'ПРОВАЛ'}")
    lines.append(f"{'архив':22} {archived} — {'сохранён' if archived else 'ПУСТ'}")

    # 2. Архивный инструмент находится при поиске с архивом и не находится без него.
    query = "запечатать файл отпечатком"
    with_archive = [item["id"] for item in pf.find(query, workset, ("active", "archived"))]
    without = [item["id"] for item in pf.find(query, workset, ("active",))]
    ok_find = "seal" in with_archive and "seal" not in without
    lines.append(f"{'поиск с архивом':22} {with_archive} — {'найден' if 'seal' in with_archive else 'НЕ найден'}")
    lines.append(f"{'поиск без архива':22} {without} — {'не найден' if 'seal' not in without else 'НАЙДЕН'}")

    # 3. Отрицательный контроль: запрос, которого нет ни в наборе, ни в архиве.
    missing = pf.find("отправить письмо по почте", workset, ("active", "archived"))
    ok_missing = not missing
    lines.append(f"{'нет такого':22} {'ничего' if ok_missing else 'НАШЛОСЬ ЧТО-ТО'}")

    lines += [
        "",
        f"итог: {'все три проверки пройдены' if ok_limit and ok_find and ok_missing else 'есть провал'}",
        "# Что доказывает: вытеснение сохраняет инструмент искомым, а отсутствующий не выдумывается.",
        "# Что не доказывает: что лимит 3 — правильный; число взято как пример, не как замер.",
    ]
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if ok_limit and ok_find and ok_missing else 1


if __name__ == "__main__":
    sys.exit(main())
