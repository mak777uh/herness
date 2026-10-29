"""Повтор задач из архива живым циклом.

Берём готовые задачи пилота (lab/pilot/T-XX.task.txt) — это настоящие задачи из журналов,
а не самотест. Сравнение с эталоном делает человек: скрипт только собирает ответы.
"""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(r"C:\111\herness")
PILOT = ROOT / "lab" / "pilot"

rows = []
for task_file in sorted(PILOT.glob("T-*.task.txt")):
    task = task_file.read_text(encoding="utf-8").strip()
    name = task_file.name.replace(".task.txt", "")
    result = subprocess.run(
        [sys.executable, "bin/hs.py", "live", task, "--auto", "--steps", "3", "--max-tokens", "6000"],
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
        elif '"action"' in text:
            status = "refused/asked"
    answer = ""
    if run_id:
        events = ROOT / "runs" / run_id / "events.jsonl"
        if events.exists():
            for line in events.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                if event.get("type") == "assistant/message":
                    answer = (event["payload"].get("text") or "").strip()
    rows.append({"task": name, "run": run_id, "steps": steps, "status": status,
                 "answer": answer[:400]})
    print(f"{name}: steps={steps} status={status}")

(ROOT / "runs" / "archive-replay.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
