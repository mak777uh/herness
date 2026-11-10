"""Прогон 10 новых задач: типы, которых не было в серии 50.

Пишет результат в research/outputs/new10.txt. Файлы репозитория во время
прогона НЕ меняются: прошлый раз правка CLAIMS.md посреди серии сломала
образ комнаты и 16 задач получили отказ.

    python bin/new10_run.py
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
CRITERIA = ROOT / "accept" / "new10"
OUT = ROOT / "research" / "outputs" / "new10.txt"
KERNEL = "vmlinuz-own-hardened2"


def run_one(path: pathlib.Path, timeout: int) -> dict:
    criteria = json.loads(path.read_text(encoding="utf-8"))
    started = time.time()
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(ROOT / "core-rs" / "accept-run.ps1"),
         "-Mode", "loop-bridge", "-Kernel", KERNEL, "-Net",
         "-TimeoutSec", str(timeout), "-Criteria", str(path.relative_to(ROOT)),
         "-Task", criteria["task"]],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = (result.stdout or "") + (result.stderr or "")
    verdict = "UNKNOWN"
    for line in text.splitlines():
        if line.strip().startswith("итог:"):
            verdict = line.split(":", 1)[1].strip()
    return {"task": path.stem, "verdict": verdict,
            "seconds": round(time.time() - started, 1)}


def main() -> int:
    paths = sorted(CRITERIA.glob("*.json"))
    if not paths:
        print(f"нет задач в {CRITERIA}")
        return 2
    results = []
    for index, path in enumerate(paths, start=1):
        row = run_one(path, 420)
        results.append(row)
        print(f"[{index}/{len(paths)}] {row['task']}: {row['verdict']} ({row['seconds']} с)",
              flush=True)

    passed = sum(1 for r in results if r["verdict"] == "PASS")
    lines = ["# Новые 10 задач: типы, которых не было в серии 50", "",
             f"задач: {len(results)}", f"PASS: {passed}",
             f"не PASS: {len(results) - passed}", "",
             "| задача | вердикт | секунд |", "|---|---|---|"]
    for row in results:
        lines.append(f"| {row['task']} | {row['verdict']} | {row['seconds']} |")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nитог: {passed} из {len(results)}")
    print(f"записано: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
