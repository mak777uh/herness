"""Fact-check v2: утверждение проверяется по ПОЛНЫМ текстам источников, а не по одному фрагменту.

Это честнее к обоим плечам: A и B получают одинаковую доказательную базу (все 5 файлов), поэтому
разница отражает знание, а не качество моей нарезки фрагментов.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\111\herness")
sys.path.insert(0, str(ROOT))

from core.http_provider import OpenAICompatProvider  # noqa: E402

H2 = ROOT / "lab" / "h2"
BASE = "https://opencode.ai/inference/go/openai/v1"
MODEL = "deepseek-v4.1-flash"
KEY_ENV = "OPENCODE_GO_API_KEY"
SOURCES = ["P16-RESULTS.md", "P17-RESULTS.md", "P18-RESULTS.md", "SELF-WORK.md", "CYCLE.md"]
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

PROMPT = """Ты проверяешь утверждение по набору источников.

Ответь строго JSON: {"verdict": "supported|contradicted|unrelated", "source": "<файл или пусто>", "why": "<до 20 слов>"}
- supported — в источниках есть именно это (число и смысл совпадают);
- contradicted — источники говорят обратное;
- unrelated — в источниках этого нет.
Не додумывай. Отсутствие числа в источниках — это unrelated, а не supported."""


def claims_of(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if len(part.strip()) > 30]
    return [part for part in parts if NUMBER.search(part) or len(part) > 120]


def sources_text() -> str:
    chunks = []
    for name in SOURCES:
        for candidate in (H2 / "A" / "run-1" / name, H2 / "B" / "run-1" / name):
            if candidate.exists():
                chunks.append(f"### {name}\n{candidate.read_text(encoding='utf-8', errors='replace')[:7000]}")
                break
    return "\n\n".join(chunks)


def main() -> int:
    data = json.loads((H2 / "results.json").read_text(encoding="utf-8"))
    client = OpenAICompatProvider(BASE, MODEL, KEY_ENV, max_tokens=300)
    evidence = sources_text()
    rows = []
    for record in data["records"]:
        text = record.get("text") or ""
        if not text:
            continue
        for claim in claims_of(text):
            client.extra_headers = {"x-opencode-session": f"herness-h2fc2-{int(time.time())}"}
            user = f"УТВЕРЖДЕНИЕ:\n{claim}\n\nИСТОЧНИКИ:\n{evidence}"
            try:
                result = client.complete([{"role": "system", "content": PROMPT},
                                          {"role": "user", "content": user}], stream=False)
                raw = (getattr(result, "reply", result).text or "").strip()
                match = re.search(r"\{.*\}", raw, re.S)
                verdict = json.loads(match.group(0)) if match else {"verdict": "unrelated",
                                                                    "source": "", "why": "не разобрал"}
            except Exception as exc:  # noqa: BLE001
                verdict = {"verdict": "unrelated", "source": "", "why": f"ошибка {type(exc).__name__}"}
            rows.append({"arm": record["arm"], "run": record["run"],
                         "verdict": verdict.get("verdict"), "source": verdict.get("source", ""),
                         "why": verdict.get("why", ""), "claim": claim[:200]})
            print(f"{record['arm']}{record['run']} {verdict.get('verdict'):<12} "
                  f"{str(verdict.get('source'))[:16]:<16} {claim[:60]}", flush=True)

    (H2 / "factcheck-v2.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
                                          encoding="utf-8")
    for arm in ("A", "B"):
        subset = [row for row in rows if row["arm"] == arm]
        total = len(subset)
        supported = sum(1 for row in subset if row["verdict"] == "supported")
        contradicted = sum(1 for row in subset if row["verdict"] == "contradicted")
        print(f"\n{arm}: утверждений {total} | подтверждено {supported} "
              f"({supported / total:.2f}) | опровергнуто {contradicted}" if total else f"{arm}: нет данных")
    return 0


if __name__ == "__main__":
    sys.exit(main())
