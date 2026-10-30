"""Прогон H-0002: дисциплина атрибуции (A) против короткого ответа (B) на 4+ источниках.

Пре-регистрация: lab/prereg/H-0002.json (запечатана). Критерий: A выше B по доле утверждений со
ссылкой на файл при 4+ источниках; при отсутствии разницы гипотеза опровергнута.
"""

from __future__ import annotations

import json
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
MODEL = "deepseek-v4.1-flash"
KEY_ENV = "OPENCODE_GO_API_KEY"
H2 = ROOT / "lab" / "h2"

SOURCES = {
    "P16-RESULTS.md": ROOT / "research" / "P16-RESULTS-2026-10-30.md",
    "P17-RESULTS.md": ROOT / "research" / "P17-RESULTS-2026-10-30.md",
    "P18-RESULTS.md": ROOT / "research" / "P18-RESULTS-2026-10-30.md",
    "SELF-WORK.md": ROOT / "lab" / "self-work" / "REPORT.md",
    "CYCLE.md": ROOT / "docs" / "CYCLE.md",
}

TASK = ("Вопрос: какие дефекты в наших утверждениях подтверждены, какими числами, и что осталось "
        "непроверенным? Ответь одним-двумя абзацами.")

ARM_A = ("Ты — исследователь с дисциплиной свидетельств. Каждое фактическое утверждение подкрепляй "
         "ссылкой на файл, где оно есть, в квадратных скобках: [P16-RESULTS.md]. Если источники "
         "противоречат друг другу — назови противоречие. Числа приводи точно, как в файле. В конце "
         "добавь раздел «Не утверждаю:» с тем, что в источниках не подтверждено.")

ARM_B = "Ответь коротко."


def prepare() -> dict[str, Path]:
    dirs = {}
    for arm in ("A", "B"):
        for run in range(1, 4):
            target = H2 / arm / f"run-{run}"
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            for name, source in SOURCES.items():
                shutil.copyfile(source, target / name)
            dirs[f"{arm}{run}"] = target
    return dirs


def run_one(arm: str, run: int, workdir: Path) -> dict:
    extra = {"x-opencode-session": f"herness-h2-{arm}{run}-{int(time.time())}"}
    client = OpenAICompatProvider(BASE, MODEL, KEY_ENV, extra_headers=extra, max_tokens=2048)
    if not client.has_key():
        raise SystemExit(f"нет ключа {KEY_ENV}")
    system = ARM_A if arm == "A" else ARM_B
    run_dir = workdir / "trace"
    run_dir.mkdir(exist_ok=True)
    journal = Journal(run_dir)
    provider = LiveProvider(client, TASK, max_steps=14, use_tools=True, system=system)
    started = time.perf_counter()
    try:
        result = loop_run(TASK, provider, ToolRouter(workdir), journal, max_steps=14,
                          snapshot_root=workdir)
        status = result.get("status", "?")
        steps = result.get("steps")
        text = next((message.get("content", "") for message in reversed(provider.messages)
                     if message.get("role") == "assistant"), "")
    finally:
        journal.close()
    elapsed = round(time.perf_counter() - started, 1)
    (workdir / "final.md").write_text(text, encoding="utf-8")
    return {"arm": arm, "run": run, "status": status, "steps": steps, "seconds": elapsed,
            "chars": len(text), "text": text}


def main(argv: list[str]) -> int:
    runs = int(argv[0]) if argv else 3
    dirs = prepare()
    records = []
    for arm in ("A", "B"):
        for run in range(1, runs + 1):
            key = f"{arm}{run}"
            print(f"[{arm}{run}] старт", flush=True)
            try:
                record = run_one(arm, run, dirs[key])
            except Exception as exc:  # noqa: BLE001
                record = {"arm": arm, "run": run, "status": f"error:{type(exc).__name__}",
                          "text": "", "seconds": 0, "chars": 0}
            print(f"[{arm}{run}] {record['status']} | {record['seconds']} c | {record['chars']} зн.",
                  flush=True)
            records.append(record)
            (H2 / "results.json").write_text(
                json.dumps({"started": datetime.now().isoformat(timespec="seconds"),
                            "prereg": "lab/prereg/H-0002.json", "records": records},
                           ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
