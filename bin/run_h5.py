"""H-0005: 20 задач, два плеча, парный McNemar. Один прогон на вопрос на плечо."""

from __future__ import annotations

import json
import math
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\111\herness")
sys.path.insert(0, str(ROOT))

from core.http_provider import OpenAICompatProvider  # noqa: E402
from core.journal import Journal  # noqa: E402
from core.live import LiveProvider  # noqa: E402
from core.loop import run as loop_run  # noqa: E402
from core.tools import ToolRouter  # noqa: E402

BASE = "https://opencode.ai/inference/go/openai/v1"
MODEL = os.environ.get("H5_MODEL", "deepseek-v4.1-flash")
KEY_ENV = "OPENCODE_GO_API_KEY"
H5 = ROOT / "lab" / "h5"
SOURCES = {
    "P16-RESULTS.md": ROOT / "research" / "P16-RESULTS-2026-10-30.md",
    "P17-RESULTS.md": ROOT / "research" / "P17-RESULTS-2026-10-30.md",
    "P18-RESULTS.md": ROOT / "research" / "P18-RESULTS-2026-10-30.md",
    "SELF-WORK.md": ROOT / "lab" / "self-work" / "REPORT.md",
    "CYCLE.md": ROOT / "docs" / "CYCLE.md",
}

ARM_A = ("Отвечай с дисциплиной свидетельств: каждое фактическое утверждение подкрепляй ссылкой на файл "
         "в квадратных скобках, например [SELF-WORK.md]. Числа приводи точно как в файле. Если в файлах "
         "нет ответа — напиши «нет в источниках». В конце раздел «Не утверждаю:».")
ARM_B = "Ответь коротко."

QUESTIONS = [
    "Сколько рецензий прошло на 30.10.2026 и какие были вердикты?",
    "Какой recall у плеча с дисциплиной и у короткого плеча в H-0002?",
    "Сколько утверждений в реестре и сколько прошли рецензию?",
    "Какие дефекты нашёл рецензент в наших утверждениях?",
    "Почему C-0087 был исправлен и что показала повторная проверка?",
    "Какие веса у Proof of Usefulness и что они означают?",
    "Сколько инстансов IAL нашёл IAL-Scan и на скольких репозиториях?",
    "Как устроена канонизация при печати методологии MethodSeal?",
    "Почему хук MethodSeal назван fail-open и чем наша печать отличается?",
    "Сколько стоит учёт бюджета на транзакцию в cadaques?",
    "Какие числа дают SAGE и When Should LLMs Trust Their Own Revisions?",
    "Что показала кривая Fact Check при росте числа вызовов с 2 до 150?",
    "Сколько инструментов в шортлисте даёт почти то же покрытие, что показ 50?",
    "Какие двери отказов есть в правиле закрытия эксперимента?",
    "Что входит в обязательный след эксперимента по нашему циклу?",
    "Чем отличается статус retro от case в реестре?",
    "Какие три ошибки измерителя мы допустили за один день?",
    "Что говорит правило K252 и как оно появилось?",
    "Сколько задач в батче дошли и сколько из них верны?",
    "Чем прослеживаемость отличается от атрибуции по нашим критериям?",
]

CITATION = __import__("re").compile(r"\[(" + "|".join(__import__("re").escape(n) for n in SOURCES) + r")\]")
NUMBER = __import__("re").compile(r"\d+(?:[.,]\d+)?")


def prepare() -> None:
    for arm in ("A", "B"):
        for index in range(1, len(QUESTIONS) + 1):
            target = H5 / arm / f"task-{index:02d}"
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            for name, source in SOURCES.items():
                shutil.copyfile(source, target / name)


def run_one(arm: str, index: int, question: str) -> dict:
    workdir = H5 / arm / f"task-{index:02d}"
    extra = {"x-opencode-session": f"herness-h5-{arm}{index}-{int(time.time())}"}
    client = OpenAICompatProvider(BASE, MODEL, KEY_ENV, extra_headers=extra, max_tokens=1200)
    journal = Journal(workdir / "trace")
    try:
        provider = LiveProvider(client, question, max_steps=12, use_tools=True,
                                system=ARM_A if arm == "A" else ARM_B)
        result = loop_run(question, provider, ToolRouter(workdir), journal, max_steps=12,
                          snapshot_root=workdir)
        text = next((message.get("content", "") for message in reversed(provider.messages)
                     if message.get("role") == "assistant"), "")
        status = result.get("status", "?")
    finally:
        journal.close()
    (workdir / "final.md").write_text(text, encoding="utf-8")
    return {"arm": arm, "task": index, "question": question, "status": status, "text": text}


def score(record: dict) -> dict:
    text = record["text"]
    parts = [part.strip() for part in __import__("re").split(r"(?<=[.!?])\s+", text) if len(part.strip()) > 25]
    claims = [p for p in parts if NUMBER.search(p) or len(p) > 110]
    cited = [p for p in claims if CITATION.search(p)]
    share = len(cited) / len(claims) if claims else 0.0
    return {"arm": record["arm"], "task": record["task"], "claims": len(claims), "cited": len(cited),
            "share": round(share, 2), "pass": bool(claims) and share >= 0.5,
            "status": record["status"]}


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    total = sum(math.comb(n, i) for i in range(0, k + 1))
    return min(1.0, 2 * total / (2 ** n))


def main() -> int:
    if not H5.exists() or not (H5 / "A").exists():
        prepare()
    records = []
    data_path = H5 / "results.json"
    if data_path.exists():
        records = json.loads(data_path.read_text(encoding="utf-8")).get("records", [])
    # сбойные прогоны (сеть) повторяем, бюджет оставляем как честный исход
    retryable = [row for row in records if str(row.get("status", "")).startswith("error")]
    if retryable:
        records = [row for row in records if not str(row.get("status", "")).startswith("error")]
        print(f"повторяем сбойных: {len(retryable)}", flush=True)
    done = {(row["arm"], row["task"]) for row in records}
    for arm in ("A", "B"):
        for index, question in enumerate(QUESTIONS, start=1):
            if (arm, index) in done:
                continue
            time.sleep(2)
            try:
                record = run_one(arm, index, question)
            except Exception as exc:  # noqa: BLE001
                record = {"arm": arm, "task": index, "question": question,
                          "status": f"error:{type(exc).__name__}", "text": ""}
            records.append(record)
            print(f"[{arm}{index:02d}] {record['status']} | {len(record['text'])} зн.", flush=True)
            data_path.write_text(json.dumps({"started": datetime.now().isoformat(timespec="seconds"),
                                             "model": MODEL, "records": records},
                                            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rows = [score(record) for record in records]
    (H5 / "scores.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    by_task = {}
    for row in rows:
        by_task.setdefault(row["task"], {})[row["arm"]] = row["pass"]
    both = sum(1 for value in by_task.values() if value.get("A") and value.get("B"))
    a_only = sum(1 for value in by_task.values() if value.get("A") and not value.get("B"))
    b_only = sum(1 for value in by_task.values() if value.get("B") and not value.get("A"))
    neither = sum(1 for value in by_task.values() if not value.get("A") and not value.get("B"))
    print(f"\nоба прошли: {both} | только A: {a_only} | только B: {b_only} | ни один: {neither}")
    print(f"exact McNemar: b={a_only}, c={b_only}, p={mcnemar_exact(a_only, b_only):.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
