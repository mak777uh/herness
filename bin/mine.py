#!/usr/bin/env python3
"""mine — добыча фактов из журналов харнесса.

Задача: не угадывать, какие задачи и боли реальны, а прочитать их в журналах прогонов.
Источник: ~/.dsh/sessions/**/session.v4.jsonl.zstd (формат v4, множество кадров zstd).

Что извлекается:
  - задачи: сообщения пользователя (текст, время);
  - действия: вызовы инструментов (имя, длительность, успех/ошибка);
  - боли: сигнатуры ошибок, сгруппированные по нормализованному тексту;
  - среда: рабочие каталоги, происхождение сессий (user/subagent), глубина делегирования.

Записи содержат личные данные: результат — зона B/C, не для публикации.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SESSIONS = Path.home() / ".dsh" / "sessions"
OUT = Path(__file__).resolve().parents[1] / "research" / "sessions"

ERROR_RE = re.compile(r"(?i)\b(error|failed|exception|denied|refused|not found|timeout|cannot|не удалось)\b")
EXIT_RE = re.compile(r"^\[exit code: (\d+)\]")
PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+")
HEX_RE = re.compile(r"\b[0-9a-f]{8,}\b")
NUM_RE = re.compile(r"\b\d+(\.\d+)?\b")

TOPICS = {
    "lean": re.compile(r"(?i)\b(lean|lake|mathlib|olean)\b"),
    "solidity": re.compile(r"(?i)\b(solidity|forge|foundry|solc|контракт)\b"),
    "rust": re.compile(r"(?i)\b(cargo|rust|rustc|clippy)\b"),
    "сеть": re.compile(r"(?i)\b(proxy|прокси|сеть|network|dns|http|подключ)\b"),
    "публикация": re.compile(r"(?i)\b(git push|коммит|commit|публик|repo|репозитор)\b"),
    "харнесс": re.compile(r"(?i)\b(харнесс|harness|агент|agent|модел|model|dsh)\b"),
    "ошибка": re.compile(r"(?i)\b(ошибк|баг|bug|падает|crash|сломал)\b"),
    "исследование": re.compile(r"(?i)\b(исслед|проанализ|найди|поиск|research|отчёт|report)\b"),
}


def zstd_lines(path: Path):
    proc = subprocess.Popen(["zstd", "-d", "-c", str(path)],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace")
    try:
        for line in proc.stdout:
            yield line
    finally:
        proc.stdout.close()
        proc.wait()


def norm(text: str) -> str:
    s = PATH_RE.sub("<path>", text)
    s = HEX_RE.sub("<id>", s)
    s = NUM_RE.sub("<n>", s)
    return re.sub(r"\s+", " ", s).strip()[:160]


def parse_session(path: Path) -> dict:
    header, tasks, calls, errors = {}, [], [], Counter()
    topics = Counter()
    pending: dict[str, dict] = {}
    steps = 0
    first_ts = last_ts = None

    for line in zstd_lines(path):
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = ev.get("type", "")
        ts = ev.get("time")

        if kind == "session":
            header = ev
            first_ts = ev.get("createdAt")
            continue
        if kind == "step/start":
            steps += 1
        if ts:
            last_ts = ts
            first_ts = first_ts or ts

        data = ev.get("data", {})

        if kind == "user/message":
            text = " ".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")
            text = text.strip()
            if text and data.get("source", {}).get("kind") == "user":
                tasks.append({"text": text[:300], "time": ts})
                for name, pat in TOPICS.items():
                    if pat.search(text):
                        topics[name] += 1

        elif kind == "tool/call":
            call_id = data.get("callId", "")
            pending[call_id] = {"name": data.get("name", "?"), "time": ts}
            calls.append(pending[call_id])

        elif kind == "tool/result":
            call_id = data.get("toolCallId") or data.get("message", {}).get("toolCallId", "")
            text = " ".join(part.get("text", "") for part in data.get("message", {}).get("content", []) if part.get("type") == "text")
            call = pending.pop(call_id, None)
            if call is not None:
                call["duration_ms"] = (ts - call["time"]) if (ts and call.get("time")) else None
                call["ok"] = True
                m = EXIT_RE.match(text.strip())
                if m and m.group(1) != "0":
                    call["ok"] = False
                    call["error"] = norm(text.splitlines()[0])
                elif not m and ERROR_RE.search(text[:600]):
                    call["ok"] = False
                    call["error"] = norm(text.strip()[:200])
                if not call["ok"]:
                    errors[call.get("error", "?")] += 1

    return {
        "file": str(path),
        "cwd": header.get("cwd"),
        "origin": header.get("origin", "user"),
        "depth": header.get("delegationDepth", 0),
        "steps": steps,
        "created": first_ts,
        "last": last_ts,
        "tasks": tasks,
        "calls": calls,
        "errors": dict(errors),
        "topics": dict(topics),
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mine")
    ap.add_argument("--limit", type=int, default=0, help="первые N сессий (0 = все)")
    ap.add_argument("--min-kb", type=int, default=0, help="пропускать файлы меньше N КБ")
    ap.add_argument("--max-mb", type=int, default=0, help="пропускать файлы больше N МБ")
    args = ap.parse_args(argv)

    files = sorted(SESSIONS.rglob("*.zstd"))
    if args.min_kb:
        files = [f for f in files if f.stat().st_size >= args.min_kb * 1024]
    if args.max_mb:
        files = [f for f in files if f.stat().st_size <= args.max_mb * 1024 * 1024]
    if args.limit:
        files = files[: args.limit]

    OUT.mkdir(parents=True, exist_ok=True)
    tool_stats: dict[str, dict] = defaultdict(lambda: {"n": 0, "fail": 0, "ms": []})
    error_counter: Counter = Counter()
    topic_counter: Counter = Counter()
    cwds: Counter = Counter()
    origins: Counter = Counter()
    all_tasks = []
    sessions = []

    for i, path in enumerate(files, 1):
        try:
            info = parse_session(path)
        except Exception as exc:  # noqa: BLE001
            print(f"[skip] {path.name}: {exc}", file=sys.stderr)
            continue
        sessions.append({k: info[k] for k in ("file", "cwd", "origin", "depth", "steps", "tasks")})
        cwds[info["cwd"] or "?"] += 1
        origins[info["origin"]] += 1
        for name, count in info["topics"].items():
            topic_counter[name] += count
        all_tasks.extend(info["tasks"])
        for call in info["calls"]:
            st = tool_stats[call["name"]]
            st["n"] += 1
            if call.get("ok") is False:
                st["fail"] += 1
            if call.get("duration_ms"):
                st["ms"].append(min(call["duration_ms"], 600000))
        error_counter.update(info["errors"])
        if i % 25 == 0:
            print(f"... {i}/{len(files)}", file=sys.stderr)

    def p95(values):
        if not values:
            return None
        values = sorted(values)
        return values[int(len(values) * 0.95) - 1] if len(values) > 1 else values[0]

    tools = []
    for name, st in sorted(tool_stats.items(), key=lambda kv: -kv[1]["n"]):
        tools.append({
            "tool": name,
            "calls": st["n"],
            "fail": st["fail"],
            "fail_pct": round(100 * st["fail"] / st["n"], 1) if st["n"] else 0,
            "p95_ms": p95(st["ms"]),
        })

    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sessions": len(sessions),
        "user_messages": len(all_tasks),
        "origins": dict(origins),
        "top_cwds": cwds.most_common(10),
        "topics": topic_counter.most_common(),
        "tools": tools,
        "top_errors": error_counter.most_common(25),
        "task_samples": [t["text"] for t in all_tasks[:60]],
    }

    (OUT / "digest.json").write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "sessions.json").write_text(json.dumps(sessions, ensure_ascii=False)[:5_000_000], encoding="utf-8")

    print(json.dumps({k: digest[k] for k in ("sessions", "user_messages", "origins", "topics")},
                     ensure_ascii=False, indent=2))
    print(f"\nзаписано: {OUT / 'digest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
