"""Fact-check ответов H-0002: следует ли утверждение из файла, на который ссылаются.

Отличие от score_h2: там проверялось наличие числа в файле, здесь — подтверждает ли фрагмент
утверждение по смыслу. Плечо A: берём cited-файл. Плечо B: ссылок нет, ищем файл по числу из
утверждения; если не находится — «источник не найден».
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
CITATION = re.compile(r"\[(" + "|".join(re.escape(name) for name in SOURCES) + r")\]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

PROMPT = """Ты проверяешь, подтверждает ли фрагмент источника утверждение.

Ответь строго JSON: {"verdict": "supported|contradicted|unrelated", "why": "<до 20 слов>"}
- supported — во фрагменте есть то, что утверждается (число и смысл совпадают);
- contradicted — фрагмент говорит обратное;
- unrelated — фрагмент не про это.
Не додумывай. Если числа нет во фрагменте — это не supported."""


def claims_of(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if len(part.strip()) > 30]
    return [part for part in parts if NUMBER.search(part) or len(part) > 120]


def excerpt(source: str, claim: str, window: int = 1200) -> str:
    path = H2 / "A" / "run-1" / source
    if not path.exists():
        return ""
    body = path.read_text(encoding="utf-8", errors="replace")
    numbers = NUMBER.findall(claim)
    for number in numbers:
        index = body.find(number)
        if index >= 0:
            start = max(0, index - window // 2)
            return body[start:start + window]
    return body[:window]


def candidate_sources(claim: str, arm: str) -> list[str]:
    if arm == "A":
        cited = CITATION.findall(claim)
        if cited:
            return cited
    found = [name for name in SOURCES if any(number in excerpt(name, claim) for number in NUMBER.findall(claim))]
    return found[:1]


def check(client, claim: str, source: str) -> dict:
    fragment = excerpt(source, claim)
    if not fragment:
        return {"verdict": "unrelated", "why": "файла нет"}
    extra = {"x-opencode-session": f"herness-h2fact-{int(time.time())}"}
    client.extra_headers = extra
    user = f"УТВЕРЖДЕНИЕ: {claim}\n\nФРАГМЕНТ ({source}):\n{fragment}"
    try:
        result = client.complete([{"role": "system", "content": PROMPT},
                                  {"role": "user", "content": user}], stream=False)
        text = (getattr(result, "reply", result).text or "").strip()
        match = re.search(r"\{.*\}", text, re.S)
        return json.loads(match.group(0)) if match else {"verdict": "unrelated", "why": "не разобрал ответ"}
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "unrelated", "why": f"ошибка {type(exc).__name__}"}


def main() -> int:
    data = json.loads((H2 / "results.json").read_text(encoding="utf-8"))
    client = OpenAICompatProvider(BASE, MODEL, KEY_ENV, max_tokens=300)
    rows = []
    for record in data["records"]:
        text = record.get("text") or ""
        if not text:
            continue
        for claim in claims_of(text):
            sources = candidate_sources(claim, record["arm"])
            source = sources[0] if sources else ""
            verdict = check(client, claim, source) if source else {"verdict": "unrelated",
                                                                   "why": "источник не найден"}
            rows.append({"arm": record["arm"], "run": record["run"], "source": source,
                         "verdict": verdict.get("verdict"), "why": verdict.get("why"),
                         "claim": claim[:220]})
            print(f"{record['arm']}{record['run']} {verdict.get('verdict'):<12} {source:<18} {claim[:70]}",
                  flush=True)
    (H2 / "factcheck.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")

    for arm in ("A", "B"):
        subset = [row for row in rows if row["arm"] == arm]
        supported = sum(1 for row in subset if row["verdict"] == "supported")
        contradicted = sum(1 for row in subset if row["verdict"] == "contradicted")
        total = len(subset)
        print(f"\n{arm}: утверждений {total}, подтверждено {supported} "
              f"({supported / total:.2f}), опровергнуто {contradicted}, "
              f"без источника {sum(1 for row in subset if row['source'] == '')}") if total else None
    return 0


if __name__ == "__main__":
    sys.exit(main())
