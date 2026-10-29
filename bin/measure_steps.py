"""Замер шагов по классам: сколько реально нужно, если не экономить.

Запускает по одной задаче на класс с большим потолком (20), записывает фактическое число шагов.
Порог в profiles.json ставится потом как факт + 2, а не на глаз.
"""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(r"C:\111\herness")
EMPTY = "Задачи этого класса в замере нет: отказ принимается до модели."

TASKS = {
    "T-0001": "Найди, сколько раз слово «критерий» встречается в README.md. Используй grep. Назови число.",
    "T-0002": "В docs/STATUS.md найди строки, где сказано, что что-то готово, но нет ссылки на C-XXXX, команду или тест. Используй grep. Перечисли номера строк или скажи «нет».",
    "T-0003": "Создай в корне файл tmp_measure.txt со строкой ok, прочитай его и подтверди.",
    "T-0004": "Запусти python tests/test_hohfeld.py и скажи, сколько проверок прошло.",
    "T-0006": "Посчитай, сколько прогонов в runs и сколько из них заканчиваются на -live. Используй list_dir с count=true.",
    "T-0007": "Объясни одной фразой, что означает имя herness.",
}

rows = []
for class_id, task in TASKS.items():
    result = subprocess.run(
        [sys.executable, "bin/hs.py", "live", task, "--auto", "--steps", "20"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    run_id = steps = status = ""
    for line in result.stdout.splitlines():
        text = line.strip()
        if '"run"' in text:
            run_id = text.split(":")[1].strip().strip('",')
        elif '"steps"' in text:
            steps = text.split(":")[1].strip().strip(",")
        elif '"status"' in text:
            status = text.split(":")[1].strip().strip('",')
    rows.append((class_id, run_id, steps, status))

print("класс   шагов  статус  прогон")
for class_id, run_id, steps, status in rows:
    print(f"{class_id}  {steps:<6} {status:<7} {run_id}")

(ROOT / "runs" / "step-measure.json").write_text(
    json.dumps([{"class": c, "run": r, "steps": s, "status": st} for c, r, s, st in rows],
               ensure_ascii=False, indent=1), encoding="utf-8")
