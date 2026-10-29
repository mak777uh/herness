"""Готовит задачи пилота из истории: полный текст задачи + эталонный ответ."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

SESSIONS = Path.home() / ".dsh" / "sessions"
OUT = Path(__file__).resolve().parents[1] / "lab" / "pilot"
NEED = "Postgres schema"


def texts(path: Path) -> tuple[str | None, str | None, int]:
    proc = subprocess.Popen(["zstd", "-d", "-c", str(path)], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
    task = answer = None
    calls = 0
    for line in proc.stdout:
        if '"user/message"' in line and task is None:
            try:
                event = json.loads(line)
                data = event.get("data", {})
                if data.get("source", {}).get("kind") == "user":
                    task = " ".join(p.get("text", "") for p in data.get("content", []) if p.get("type") == "text").strip()
            except json.JSONDecodeError:
                pass
        elif '"tool/call"' in line:
            calls += 1
        elif '"assistant/message"' in line:
            try:
                event = json.loads(line)
                content = event.get("data", {}).get("message", {}).get("content", [])
                text = " ".join(p.get("text", "") for p in content if p.get("type") == "text").strip()
                if text:
                    answer = text
            except json.JSONDecodeError:
                pass
    proc.wait()
    return task, answer, calls


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    saved = 0
    for path in sorted(SESSIONS.rglob("*.zstd")):
        task, answer, calls = texts(path)
        if not task or NEED not in task or not answer:
            continue
        saved += 1
        (OUT / f"T-{saved:02d}.task.txt").write_text(task, encoding="utf-8")
        (OUT / f"T-{saved:02d}.ref.txt").write_text(answer, encoding="utf-8")
        print(f"T-{saved:02d}: calls={calls} len(task)={len(task)} len(ref)={len(answer)}")
        if saved >= 8:
            break
    print(f"\nсохранено в {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
