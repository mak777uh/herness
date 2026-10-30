"""Батч реальных задач через наш цикл: журнал, метрики, разбор.

Задачи — про сам репозиторий, поэтому правильность ответа проверяется нашими же командами.
Метрики: шаги, вызовы, повторы одного и того же вызова, отказы инструментов, время, финальный текст.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\111\herness")
sys.path.insert(0, str(ROOT))

from core.http_provider import OpenAICompatProvider  # noqa: E402
from core.journal import Journal  # noqa: E402
from core.live import LiveProvider  # noqa: E402
from core.loop import run as loop_run  # noqa: E402
from core.tools import ToolRouter  # noqa: E402

MODEL = "deepseek-v4.1-flash"
BASE = "https://opencode.ai/inference/go/openai/v1"
KEY_ENV = "OPENCODE_GO_API_KEY"
MAX_STEPS = 12

TASKS = [
    {"id": "py-count",
     "text": "Сколько файлов .py лежит в каталоге bin и сколько из них содержат строку 'def main'?",
     "truth": "пересчитать: Get-ChildItem bin/*.py и поиск 'def main'"},
    {"id": "gates",
     "text": "Какие гейты запускает hs gates и что проверяет гейт способности?",
     "truth": "список в cmd_gates; gate_capabilities сравнивает capabilities.json с кодом"},
    {"id": "claims",
     "text": "Сколько утверждений в CLAIMS.md и у скольких из них заполнено ожидание?",
     "truth": "python bin/coverage.py: 69 утверждений, битых строк 0"},
    {"id": "anchor-test",
     "text": "Есть ли в репозитории тест привязки запроса и сколько случаев он проверяет?",
     "truth": "tests/test_anchor.py, 10 случаев, 10/10 ok"},
    {"id": "trap",
     "text": "Все ли утверждения в CLAIMS.md подтверждены исполняемой командой?",
     "truth": "не все: withdrawn-записи команды не имеют (C-0014)"},
]


def run_task(task: dict) -> dict:
    stamp = int(time.time())
    extra = {"x-opencode-session": f"herness-batch-{task['id']}-{stamp}"}
    client = OpenAICompatProvider(BASE, MODEL, KEY_ENV, extra_headers=extra, max_tokens=8000)
    provider = LiveProvider(client, task["text"], max_steps=MAX_STEPS)

    run_dir = ROOT / "runs" / f"batch-{task['id']}-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    journal = Journal(run_dir)
    started = time.time()
    error = ""
    result = None
    try:
        result = loop_run(task["text"], provider, ToolRouter(ROOT), journal, max_steps=MAX_STEPS,
                          snapshot_root=ROOT)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    finally:
        handle = getattr(journal, "_fh", None)
        if handle is not None and not handle.closed:
            journal.close()

    final = ""
    for message in reversed(provider.messages):
        if message.get("role") == "assistant" and message.get("content"):
            final = message["content"]
            break

    # разбор журнала
    calls, results, repeats = [], [], Counter()
    events_path = run_dir / "events.jsonl"
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            payload = event.get("payload", {})
            if event["type"] == "tool/call":
                name = payload.get("name")
                args = payload.get("arguments")
                calls.append((name, json.dumps(args, ensure_ascii=False, sort_keys=True)))
                repeats[(name, json.dumps(args, ensure_ascii=False, sort_keys=True))] += 1
            elif event["type"] == "tool/result":
                results.append(bool(payload.get("ok")))

    raw_steps = result.get("steps", 0) if result else 0
    steps = len(raw_steps) if isinstance(raw_steps, (list, tuple)) else int(raw_steps or 0)
    return {
        "id": task["id"], "task": task["text"], "truth": task["truth"],
        "run_dir": str(run_dir.relative_to(ROOT)),
        "status": result.get("status") if result else "error", "error": error,
        "steps": steps, "calls": len(calls), "seconds": round(time.time() - started, 1),
        "repeats": sum(count - 1 for count in repeats.values() if count > 1),
        "duplicate_calls": [f"{name}: {args[:60]}" for (name, args), count in repeats.items() if count > 1],
        "failed_tools": results.count(False),
        "tool_sequence": [name for name, _ in calls],
        "final": final[:1500],
    }


def main() -> int:
    only = {arg for arg in sys.argv[1:] if not arg.startswith("-")}
    tasks = [task for task in TASKS if not only or task["id"] in only]
    rows = []
    for task in tasks:
        print(f"[{task['id']}] {task['text'][:70]}...", flush=True)
        rows.append(run_task(task))

    out = ROOT / "lab" / "journal-batch" / "results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{'задача':<12}{'статус':<10}{'шаги':<6}{'вызовы':<8}{'повторы':<9}{'отказы':<8}{'сек'}")
    for row in rows:
        print(f"{row['id']:<12}{row['status']:<10}{row['steps']:<6}{row['calls']:<8}"
              f"{row['repeats']:<9}{row['failed_tools']:<8}{row['seconds']}")
    print(f"\nрезультаты: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
