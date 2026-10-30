"""Эксперимент 002: реальные задачи из истории харнесса, три размера.

Задачи взяты из наших же прогонов: маленькая (EOL NixOS), средняя с ловушкой (lean4 в openSUSE) и
большая (свод реестра ОС из четырёх ответов). Руки те же: дисциплина свидетельств против «коротко».

Оценка — по заранее записанным правилам (rubric), а не по общему впечатлению.
"""

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\111\herness")
sys.path.insert(0, str(ROOT))

from core.http_provider import OpenAICompatProvider  # noqa: E402
from core.journal import Journal  # noqa: E402
from core.live import LiveProvider  # noqa: E402
from core.loop import run as loop_run  # noqa: E402
from core.tools import ToolRouter  # noqa: E402

PROMPT_A = (
    "Ты аналитик с дисциплиной свидетельств. Прочитай все файлы-источники в каталоге задачи. "
    "Для каждого утверждения укажи, из какого файла оно взято. Если источники противоречат — назови "
    "противоречие и не усредняй. Если источник не прочитан (отказ, 403) — скажи это прямо и не "
    "выводи из этого отсутствие. В конце добавь раздел «Не утверждаю»."
)
PROMPT_B = "Ответь коротко на вопрос, опираясь на файлы в каталоге задачи."

MODEL = "deepseek-v4.1-flash"
BASE = "https://opencode.ai/inference/go/openai/v1"
KEY_ENV = "OPENCODE_GO_API_KEY"
MAX_STEPS = 14

TASKS = [
    {
        "id": "small",
        "dir": "lab/exp3/small",
        "text": ("Какой срок поддержки (EOL) у ветки NixOS 26.05? "
                 "Источники — файлы в каталоге задачи. Других файлов не читай."),
        "rubric": [
            ("2026-12-31", 2, "названа дата EOL"),
            ("26.05", 1, "названа ветка"),
        ],
    },
    {
        "id": "medium",
        "dir": "lab/exp3/medium",
        "text": ("Есть ли пакет lean4 в официальном репозитории openSUSE? "
                 "Источники — файлы в каталоге задачи. Других файлов не читай."),
        "rubric": [
            ("science", 2, "различает основной и сторонний репозиторий"),
            ("403", 2, "называет отказ источника"),
            ("не установлен|нельзя утверждать|не прочитан|не подтвержд", 2, "не делает вывод из 403"),
        ],
        "penalty": [("в официальном репозитории есть|входит в официальн", -2, "ложное утверждение")],
    },
    {
        "id": "large",
        "dir": "lab/exp3/large",
        "text": ("Сведи реестр ОС по четырём ответам: что утверждают единогласно, а где расходятся? "
                 "Источники — файлы в каталоге задачи. Других файлов не читай."),
        "rubric": [
            ("поколени|snapper|ostree|rollback|откат", 1, "тема отката затронута"),
            ("соглас|единогласно|совпада|все четыре|все ответы", 1, "названо согласие"),
            ("расхожден|противореч|спор|различа", 2, "названы расхождения"),
            ("guix", 2, "указано расхождение по Guix"),
            ("openSUSE|science|4.15", 2, "указано расхождение по openSUSE"),
        ],
    },
]


def score(task: dict, text: str) -> dict:
    low = text.lower()
    total, hits, notes = 0, 0, []
    for pattern, points, label in task["rubric"]:
        if re.search(pattern, low, re.I):
            total += points
            hits += 1
            notes.append(f"+{points} {label}")
        else:
            notes.append(f"+0 {label}")
    for pattern, points, label in task.get("penalty", []):
        if re.search(pattern, low, re.I):
            total += points
            notes.append(f"{points} {label}")
    maximum = sum(p for _, p, _ in task["rubric"])
    presentation = {
        "cites_file": bool(re.search(r"\.md|файл", low)),
        "flags_conflict": bool(re.search(r"расхожден|противореч|конфликт|различа", low)),
        "not_claimed": "не утверждаю" in low,
        "says_unread": bool(re.search(r"403|не прочитан|отказ источник", low)),
    }
    return {"points": total, "max": maximum, "hits": hits, "notes": notes,
            "presentation": presentation}


def run_one(task: dict, arm: str, prompt: str, index: int) -> dict:
    stamp = int(time.time())
    extra = {"x-opencode-session": f"herness-exp3-{task['id']}-{arm}-{index}-{stamp}"}
    client = OpenAICompatProvider(BASE, MODEL, KEY_ENV, extra_headers=extra, max_tokens=8000)
    instruction = task["text"] + f" Каталог: {task['dir']}."
    provider = LiveProvider(client, instruction, max_steps=MAX_STEPS, system=prompt)

    started = time.time()
    result = None
    last_error = None
    run_dir = None
    for attempt in range(3):
        stamp_attempt = f"{stamp}-{attempt}"
        run_dir = ROOT / "runs" / f"exp3-{task['id']}-{arm}-{index}-{stamp_attempt}"
        run_dir.mkdir(parents=True, exist_ok=True)
        journal = Journal(run_dir)
        try:
            result = loop_run(instruction, provider, ToolRouter(ROOT), journal, max_steps=MAX_STEPS)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            retryable = any(word in str(exc).lower() for word in
                            ("ssl", "connection", "disconnected", "сеть", "timed out", "10054"))
            if not retryable:
                break
            time.sleep(5 + attempt * 5)
        finally:
            handle = getattr(journal, "_fh", None)
            if handle is not None and not handle.closed:
                journal.close()
    if result is None:
        raise last_error if last_error else RuntimeError("прогон не удался")

    final = ""
    for message in reversed(provider.messages):
        if message.get("role") == "assistant" and message.get("content"):
            final = message["content"]
            break
    raw_steps = result.get("steps", 0)
    steps = len(raw_steps) if isinstance(raw_steps, (list, tuple)) else int(raw_steps or 0)
    return {"task": task["id"], "arm": arm, "run": index, "status": result.get("status"),
            "steps": steps, "seconds": round(time.time() - started, 1),
            **score(task, final), "final": final[:2000]}


def main() -> int:
    rows = []
    for task in TASKS:
        for arm, prompt in (("A", PROMPT_A), ("B", PROMPT_B)):
            for index in (1, 2):
                print(f"{task['id']} {arm}-{index}...", flush=True)
                try:
                    rows.append(run_one(task, arm, prompt, index))
                except Exception as exc:  # noqa: BLE001
                    rows.append({"task": task["id"], "arm": arm, "run": index,
                                 "status": f"ошибка: {type(exc).__name__}: {exc}"})

    out = ROOT / "lab" / "exp3" / "results.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{'задача':<8}{'рука':<5}{'баллы':<9}{'шаги':<6}{'сек':<7}статус")
    for row in rows:
        print(f"{row['task']:<8}{row['arm']}-{row['run']:<3}"
              f"{str(row.get('points', '—')) + '/' + str(row.get('max', '—')):<9}"
              f"{row.get('steps', '—'):<6}{row.get('seconds', '—'):<7}{row.get('status', '')}")

    for task in TASKS:
        for arm in ("A", "B"):
            got = [r["points"] for r in rows if r.get("task") == task["id"] and r.get("arm") == arm
                   and "points" in r]
            if got:
                print(f"{task['id']:<8}{arm}: среднее {sum(got) / len(got):.1f} из {task['rubric'] and sum(p for _, p, _ in task['rubric'])}")
    print("\nизложение (доля прогонов):")
    for task in TASKS:
        for arm in ("A", "B"):
            cells = [r["presentation"] for r in rows
                     if r.get("task") == task["id"] and r.get("arm") == arm and "presentation" in r]
            if not cells:
                continue
            n = len(cells)
            print(f"  {task['id']:<7}{arm}: файл {sum(c['cites_file'] for c in cells)}/{n}"
                  f", расхождение {sum(c['flags_conflict'] for c in cells)}/{n}"
                  f", «не утверждаю» {sum(c['not_claimed'] for c in cells)}/{n}")
    print(f"\nрезультаты: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
