"""Супервизор: очередь работ с бюджетом, отказом без пре-регистрации и записью следов.

Роль «научного руководителя» здесь машинная: гипотезу ставлю я, а супервизор не даёт запустить работу,
у которой нет плана, скорера и лимита; и не даёт считать exploration свидетельством.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "lab" / "queue.json"
RUNS = ROOT / "lab" / "runs"


def load() -> dict:
    return json.loads(QUEUE.read_text(encoding="utf-8"))


def save(data: dict) -> None:
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    QUEUE.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def problems_of(job: dict) -> list[str]:
    found = []
    if not job.get("id"):
        found.append("нет id")
    if not job.get("command"):
        found.append(f"{job.get('id')}: нет команды")
    if not job.get("budget_seconds"):
        found.append(f"{job.get('id')}: нет бюджета времени")
    if not job.get("acceptance"):
        found.append(f"{job.get('id')}: не сказано, что считается принятым")
    if not job.get("exploration", False) and not job.get("prereg"):
        found.append(f"{job.get('id')}: не exploration и нет пре-регистрации")
    prereg = job.get("prereg")
    if prereg and not (ROOT / prereg).exists():
        found.append(f"{job.get('id')}: файла пре-регистрации нет ({prereg})")
    if not job.get("scorer"):
        found.append(f"{job.get('id')}: нет скорера — результат нельзя оценить")
    return found


def status(data: dict) -> int:
    jobs = data.get("jobs", [])
    counts = {}
    for job in jobs:
        counts[job.get("status", "?")] = counts.get(job.get("status", "?"), 0) + 1
    print(f"очередь: {len(jobs)} работ | " + ", ".join(f"{key}: {value}" for key, value in sorted(counts.items())))
    for job in jobs:
        print(f"  {job['id']:<8} {job.get('status', '?'):<9} {job.get('kind', '?'):<10} "
              f"{job.get('title', '')[:70]}")
    budget = data.get("budget", {})
    print(f"бюджет: {budget.get('max_jobs_per_day')} работ/сутки, "
          f"{budget.get('max_seconds_total')} секунд суммарно")
    return 0


def check(data: dict) -> int:
    found = [problem for job in data.get("jobs", []) for problem in problems_of(job)]
    for problem in found:
        print(f"[FAIL] {problem}")
    print(f"работ проверено: {len(data.get('jobs', []))}, проблем: {len(found)}")
    return 0 if not found else 1


def run_job(job: dict) -> dict:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    directory = RUNS / f"sup-{job['id']}-{stamp}"
    directory.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        environment = {**os.environ, **job.get("env", {})}
        completed = subprocess.run(job["command"], cwd=ROOT, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", env=environment,
                                   timeout=int(job["budget_seconds"]))
        code, out, err = completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        code, out, err = 124, str(exc.stdout or ""), f"превышен бюджет {job['budget_seconds']} c"
    elapsed = round(time.perf_counter() - started, 1)
    (directory / "stdout.txt").write_text(out or "", encoding="utf-8")
    (directory / "stderr.txt").write_text(err or "", encoding="utf-8")
    scorer_out = ""
    scorer = job.get("scorer") or ""
    if code == 0 and scorer.endswith(".py"):
        try:
            scored = subprocess.run(["python", scorer], cwd=ROOT, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace",
                                    env={**os.environ, **job.get("env", {})}, timeout=300)
            scorer_out = (scored.stdout or "") + (scored.stderr or "")
        except Exception as exc:  # noqa: BLE001
            scorer_out = f"скоринг не удался: {type(exc).__name__}"
        (directory / "scorer.txt").write_text(scorer_out, encoding="utf-8")
    record = {"id": job["id"], "started": stamp, "seconds": elapsed, "exit": code,
              "scorer_ran": bool(scorer_out),
              "budget_seconds": job["budget_seconds"], "exploration": job.get("exploration", False),
              "prereg": job.get("prereg"), "command": job["command"],
              "evidence": not job.get("exploration", False)}
    (directory / "job.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                                        encoding="utf-8")
    return record


def main(argv: list[str]) -> int:
    data = load()
    command = argv[0] if argv else "status"

    if command == "status":
        return status(data)
    if command == "check":
        return check(data)
    if command != "run":
        print("status | check | run [id]")
        return 2

    wanted = argv[1] if len(argv) > 1 else None
    pending = [job for job in data["jobs"]
               if job.get("status") in ("queued", "failed") and (wanted is None or job["id"] == wanted)]
    if not pending:
        print("нет работ в очереди" if wanted is None else f"{wanted}: нет в очереди")
        return 1

    for job in pending:
        found = problems_of(job)
        if found:
            job["status"] = "rejected"
            job["rejected_because"] = found
            print(f"[rejected] {job['id']}: " + "; ".join(found))
            save(data)
            continue
        record = run_job(job)
        job["status"] = "done" if record["exit"] == 0 else "failed"
        job["last_run"] = record["started"]
        job["last_exit"] = record["exit"]
        print(f"[{job['status']}] {job['id']} | {record['seconds']} c | код {record['exit']}")
        save(data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
