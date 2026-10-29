"""Извлекает пары «задача владельца → финальный ответ» из журналов.

Нужно для пилота L1/L2: реальные задачи с известным результатом, а не выдуманные.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

SESSIONS = Path.home() / ".dsh" / "sessions"
OUT = Path(__file__).resolve().parents[1] / "research" / "sessions" / "task-pairs.json"


def extract(path: Path) -> dict | None:
    proc = subprocess.Popen(["zstd", "-d", "-c", str(path)], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
    task = None
    answer = None
    calls = 0
    for line in proc.stdout:
        if '"user/message"' in line and task is None:
            try:
                event = json.loads(line)
                data = event.get("data", {})
                if data.get("source", {}).get("kind") == "user":
                    text = " ".join(p.get("text", "") for p in data.get("content", []) if p.get("type") == "text")
                    task = text.strip() or None
            except json.JSONDecodeError:
                pass
        elif '"tool/call"' in line:
            calls += 1
        elif '"assistant/message"' in line:
            try:
                event = json.loads(line)
                content = event.get("data", {}).get("message", {}).get("content", [])
                text = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
                if text.strip():
                    answer = text.strip()
            except json.JSONDecodeError:
                pass
    proc.wait()
    if not task or not answer:
        return None
    return {"file": str(path), "calls": calls, "task": task[:600], "answer": answer[:800]}


def main() -> int:
    pairs = []
    for path in sorted(SESSIONS.rglob("*.zstd")):
        info = extract(path)
        if info:
            pairs.append(info)
    OUT.write_text(json.dumps(pairs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"пар: {len(pairs)}; записано: {OUT}")
    for i, p in enumerate(pairs[:12], 1):
        print(f"{i:>2}. calls={p['calls']:<4} task={p['task'][:90]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
