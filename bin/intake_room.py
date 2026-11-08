"""intake_room — вкладка для реальных задач владельца.

Владелец кладёт задачу в `intake/` (или через `python bin/intake_room.py --add`),
харнесс прогоняет её в комнате и складывает результат в `intake/done/`.

    python bin/intake_room.py --add --task "..." [--criteria accept/...json]
    python bin/intake_room.py --list
    python bin/intake_room.py --run [--limit N]
    python bin/intake_room.py --report
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTAKE = ROOT / "intake"
DONE = INTAKE / "done"
REPORT = ROOT / "research" / "outputs" / "intake-report.txt"

# Критерий по умолчанию для реальных задач: агент должен закончить сам.
DEFAULT_CRITERIA = {
    "require_status": "done",
    "max_steps": 24,
    "max_allowance": 0.1,
    "must_not_call": ["write"],
    "tools": ["search", "list", "read"],
}


def add(task: str, criteria: Path | None) -> int:
    INTAKE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    name = f"T-{stamp}"
    data = dict(DEFAULT_CRITERIA)
    data["task"] = task
    if criteria and criteria.exists():
        data = json.loads(criteria.read_text(encoding="utf-8"))
        data["task"] = task
    (INTAKE / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"задача добавлена: {name}")
    print(f"  {task}")
    return 0


def listing() -> int:
    INTAKE.mkdir(parents=True, exist_ok=True)
    pending = sorted(p for p in INTAKE.glob("*.json"))
    done = sorted(DONE.glob("*.json")) if DONE.exists() else []
    print(f"в очереди: {len(pending)}")
    for path in pending:
        data = json.loads(path.read_text(encoding="utf-8"))
        print(f"  {path.stem}: {data['task'][:70]}")
    print(f"выполнено: {len(done)}")
    return 0


def run(limit: int, timeout: int) -> int:
    INTAKE.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)
    paths = sorted(INTAKE.glob("*.json"))
    if limit:
        paths = paths[:limit]
    if not paths:
        print("очередь пуста")
        return 0

    results = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        print(f"--- {path.stem}: {data['task'][:60]}", flush=True)
        started = time.time()
        proc = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(ROOT / "core-rs" / "accept-run.ps1"),
             "-Mode", "loop-bridge", "-Kernel", "vmlinuz-own-hardened2", "-Net",
             # Путь относительный: accept-run склеивает его с корнем репозитория,
             # а абсолютный путь даёт «C:\111\herness\C:\111\herness\...» (найдено прогоном).
             "-TimeoutSec", str(timeout), "-Criteria", str(path.relative_to(ROOT)),
             "-Task", data["task"]],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
        )
        verdict = "UNKNOWN"
        for line in (proc.stdout or "").splitlines():
            if line.strip().startswith("итог:"):
                verdict = line.split(":", 1)[1].strip()
        row = {"task": path.stem, "text": data["task"], "verdict": verdict,
               "seconds": round(time.time() - started, 1)}
        results.append(row)
        print(f"    {verdict} ({row['seconds']} с)", flush=True)
        # Сначала пишем результат, потом убираем из очереди: иначе при сбое записи
        # задача теряется (найдено первым же прогоном вкладки).
        (DONE / path.name).write_text(
            json.dumps({**data, "verdict": verdict}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        path.unlink()

    report(results)
    return 0


def report(results: list[dict] | None = None) -> int:
    lines = ["# Реальные задачи владельца", ""]
    if results is None:
        results = []
        for path in sorted(DONE.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            results.append({"task": path.stem, "text": data.get("task", ""),
                            "verdict": data.get("verdict", "UNKNOWN"), "seconds": 0})
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    lines.append(f"задач: {len(results)}, прошло: {passed}")
    lines.append("")
    lines.append("| задача | вердикт | секунд |")
    lines.append("|---|---|---|")
    for row in results:
        lines.append(f"| {row['task']} | {row['verdict']} | {row['seconds']} |")
    lines.append("")
    lines.append("## Тексты")
    lines.append("")
    for row in results:
        lines.append(f"- **{row['task']}** ({row['verdict']}): {row['text']}")
    text = "\n".join(lines) + "\n"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text, encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="вкладка реальных задач")
    parser.add_argument("--add", action="store_true")
    parser.add_argument("--task", default="")
    parser.add_argument("--criteria", default="")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=420)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.add:
        if not args.task:
            print("нужно --task \"текст задачи\"", file=sys.stderr)
            return 2
        return add(args.task, Path(args.criteria) if args.criteria else None)
    if args.list:
        return listing()
    if args.run:
        return run(args.limit, args.timeout)
    if args.report:
        return report()
    print("укажи --add, --list, --run или --report", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
