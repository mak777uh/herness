"""series50_run — прогон серии из 50 задач.

Запускает приёмку по одной задаче на закалённом ядре, собирает числа.

    python bin/series50_run.py --limit 5      # первые пять (разведка)
    python bin/series50_run.py                # все пятьдесят
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRITERIA = ROOT / "accept" / "series50"
RUNS = ROOT / "runs" / "series50"
OUT = ROOT / "research" / "outputs" / "series50.txt"
KERNEL = "vmlinuz-own-hardened2"


def run_one(path: Path, timeout: int) -> dict:
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
    return {"task": path.stem, "verdict": verdict, "seconds": round(time.time() - started, 1),
            "expected": criteria["require_status"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="прогон серии из 50")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=420)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    RUNS.mkdir(parents=True, exist_ok=True)
    paths = sorted(CRITERIA.glob("*.json"))
    if args.limit:
        paths = paths[: args.limit]

    results = []
    for index, path in enumerate(paths, start=1):
        row = run_one(path, args.timeout)
        results.append(row)
        print(f"[{index}/{len(paths)}] {row['task']}: {row['verdict']} ({row['seconds']} с)",
              flush=True)

    (RUNS / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")

    passed = sum(1 for r in results if r["verdict"] == "PASS")
    failed = sum(1 for r in results if r["verdict"] == "FAIL")
    unknown = sum(1 for r in results if r["verdict"] == "UNKNOWN")
    lines = ["# Серия из 50 задач", ""]
    lines.append(f"задач: {len(results)}")
    lines.append(f"PASS: {passed}")
    lines.append(f"FAIL: {failed}")
    lines.append(f"UNKNOWN: {unknown}")
    lines.append("")
    lines.append("| задача | ожидание | вердикт | секунд |")
    lines.append("|---|---|---|---|")
    for row in results:
        lines.append(f"| {row['task']} | {row['expected']} | {row['verdict']} | {row['seconds']} |")
    text = "\n".join(lines) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
