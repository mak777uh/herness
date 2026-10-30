"""Эксперимент: даёт ли дисциплина свидетельств выигрыш на задаче с противоречием.

Две руки, одинаковые инструменты и модель, разница только в системном промпте:
A — требуется ссылка на файл, фиксация противоречия и раздел «не утверждаю»;
B — «ответь коротко».

Метрики: заметил ли оба числа, назвал ли противоречие, сослался ли на файл, сколько шагов.
"""

import json
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

TASK = (
    "Какая версия пакета lean4 в официальном канале Guix? "
    "Единственные источники — два файла в каталоге lab/exp-discipline/sources. "
    "Других файлов не читай. Ответь, указав версию."
)

PROMPT_A = (
    "Ты аналитик с дисциплиной свидетельств. Прочитай оба файла-источника инструментами. "
    "Для каждого числа укажи, из какого файла оно взято. Если источники противоречат — назови "
    "противоречие явно и не усредняй. В конце добавь раздел «Не утверждаю»: что осталось "
    "непроверенным и почему. Не читай файлы вне каталога источников."
)
PROMPT_B = "Ответь коротко на вопрос, опираясь на файлы. Не читай файлы вне каталога источников."

MODEL = "deepseek-v4.1-flash"
BASE = "https://opencode.ai/inference/go/openai/v1"
KEY_ENV = "OPENCODE_GO_API_KEY"
MAX_STEPS = 10


def analyse(text: str) -> dict:
    low = text.lower()
    return {
        "mentions_417": "4.17" in text,
        "mentions_429": "4.29" in text,
        "flags_conflict": any(word in low for word in ("противореч", "расхожден", "конфликт",
                                                       "различа", "не совпад")),
        "cites_file": any(name in low for name in ("guix-catalog", "guix-master", ".md")),
        "has_not_claimed": "не утверждаю" in low,
        "length": len(text),
    }


def run_arm(arm: str, prompt: str, index: int) -> dict:
    # Go-эндпоинт требует стабильный id разговора: без него 400 MissingSessionID
    stamp = int(time.time())
    extra = {"x-opencode-session": f"herness-exp2-{arm}-{index}-{stamp}"}
    client = OpenAICompatProvider(BASE, MODEL, KEY_ENV, extra_headers=extra, max_tokens=8000)
    provider = LiveProvider(client, TASK, max_steps=MAX_STEPS, system=prompt)

    run_dir = ROOT / "runs" / f"exp2-{arm}-{index}-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    journal = Journal(run_dir)
    started = time.time()
    try:
        result = loop_run(TASK, provider, ToolRouter(ROOT), journal, max_steps=MAX_STEPS)
    finally:
        handle = getattr(journal, "_fh", None)
        if handle is not None and not handle.closed:
            journal.close()

    final = ""
    for message in reversed(provider.messages):
        if message.get("role") == "assistant" and message.get("content"):
            final = message["content"]
            break

    metrics = analyse(final)
    raw_steps = result.get("steps", 0)
    steps_count = len(raw_steps) if isinstance(raw_steps, (list, tuple)) else int(raw_steps or 0)
    metrics.update({"arm": arm, "run": index, "status": result.get("status"),
                    "steps": steps_count, "calls": provider.calls,
                    "seconds": round(time.time() - started, 1), "final": final[:2500]})
    return metrics


def main() -> int:
    rows = []
    for arm, prompt in (("A", PROMPT_A), ("B", PROMPT_B)):
        for index in (1, 2, 3):
            print(f"прогон {arm}-{index}...", flush=True)
            try:
                rows.append(run_arm(arm, prompt, index))
            except Exception as exc:  # noqa: BLE001
                rows.append({"arm": arm, "run": index, "status": f"ошибка: {type(exc).__name__}: {exc}"})

    out = ROOT / "lab" / "exp-discipline" / "results.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{'рука':<5}{'оба числа':<11}{'противоречие':<14}{'ссылка':<9}{'не утв.':<9}{'шаги':<6}{'сек'}")
    for row in rows:
        if "mentions_417" not in row:
            print(f"{row['arm']}-{row['run']}  {row.get('status')}")
            continue
        both = row["mentions_417"] and row["mentions_429"]
        print(f"{row['arm']}-{row['run']:<4}{str(both):<11}{str(row['flags_conflict']):<14}"
              f"{str(row['cites_file']):<9}{str(row['has_not_claimed']):<9}{row['steps']:<6}{row['seconds']}")
    print(f"\nрезультаты: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
