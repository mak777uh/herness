"""Рецензент: ищет, что убьёт утверждение, и пишет вердикт в lab/reviews.

Взят по образцу reviewer из Morphogenesis: не запускает прогоны, не правит утверждения, пишет только
рецензии. Модель — та же закреплённая, но с враждебной задачей: не подтвердить, а опровергнуть.
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

MODEL = "deepseek-v4.1-flash"
REVIEWER_MODEL = "deepseek-v4-pro"  # по умолчанию рецензент — другая модель, чем производитель
BASE = "https://opencode.ai/inference/go/openai/v1"
KEY_ENV = "OPENCODE_GO_API_KEY"
REVIEWS = ROOT / "lab" / "reviews"

PROMPT = """Ты — рецензент-скептик. Твоя задача НЕ подтвердить утверждение, а найти, что его убьёт.

Дано:
- утверждение;
- команда проверки;
- ожидание (что должно быть в артефакте);
- содержимое артефакта (может быть обрезано).

Ответь строго JSON:
{"verdict": "upheld|killed|unclear",
 "artifact_checked": "<что именно смотрел>",
 "reasons": ["...", "..."],
 "what_would_kill_it": "<чего достаточно, чтобы утверждение упало>"}

Правила:
1. upheld — только если артефакт действительно содержит ожидание, а утверждение не шире него.
2. killed — если артефакт противоречит или утверждение шире, чем артефакт подтверждает.
3. unclear — если артефакта нет, он пуст или не о том.
Не выдумывай содержимое артефакта. Не хвали. Не пересказывай утверждение."""


def claims() -> dict[str, dict]:
    rows = {}
    for line in (ROOT / "CLAIMS.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("| C-"):
            continue
        cells = [cell.strip().strip("`").strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        rows[cells[0]] = {"id": cells[0], "claim": cells[1], "type": cells[2],
                          "command": cells[3], "artifact": cells[4], "expect": cells[6]}
    return rows


def artifact_text(path: str, limit: int = 6000) -> str:
    target = ROOT / path
    if not target.exists():
        return ""
    try:
        return target.read_text(encoding="utf-8", errors="replace")[:limit]
    except (OSError, ValueError):
        return ""


def review(claim_id: str, row: dict, model: str = REVIEWER_MODEL) -> dict:
    body = artifact_text(row["artifact"])
    user = (f"УТВЕРЖДЕНИЕ: {row['claim']}\n"
            f"КОМАНДА: {row['command']}\n"
            f"ОЖИДАНИЕ В АРТЕФАКТЕ: {row['expect']}\n"
            f"АРТЕФАКТ ({row['artifact']}):\n{body or '(не найден или пуст)'}")
    extra = {"x-opencode-session": f"herness-review-{claim_id}-{int(time.time())}"}
    client = OpenAICompatProvider(BASE, model, KEY_ENV, extra_headers=extra, max_tokens=4000)
    result = client.complete([{"role": "system", "content": PROMPT},
                              {"role": "user", "content": user}], stream=False)
    reply = getattr(result, "reply", result)
    text = (reply.text or "").strip()
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {"verdict": "unclear", "artifact_checked": row["artifact"], "model": model,
                "reasons": [f"модель не вернула JSON: {text[:200]}"],
                "what_would_kill_it": "не удалось разобрать ответ"}
    try:
        parsed = json.loads(match.group(0))
        parsed["model"] = model
        return parsed
    except json.JSONDecodeError:
        return {"verdict": "unclear", "artifact_checked": row["artifact"], "model": model,
                "reasons": ["JSON не разобрался"], "what_would_kill_it": "не удалось разобрать ответ"}


def write_review(claim_id: str, row: dict, verdict: dict) -> Path:
    REVIEWS.mkdir(parents=True, exist_ok=True)
    path = REVIEWS / f"{claim_id}-{time.strftime('%Y-%m-%d')}.md"
    reasons = "\n".join(f"  - {reason}" for reason in verdict.get("reasons", []))
    path.write_text(
        f"id: {claim_id}\n"
        f"date: {time.strftime('%Y-%m-%d')}\n"
        f"claim: {row['claim']}\n"
        f"verdict: {verdict.get('verdict', 'unclear')}\n"
        f"artifact_checked: {verdict.get('artifact_checked', row['artifact'])}\n"
        f"method: рецензент {verdict.get('model', 'deepseek-v4-pro')}: чтение артефакта и сверка с ожиданием\n"
        f"reasons:\n{reasons}\n"
        f"what_would_kill_it: {verdict.get('what_would_kill_it', '—')}\n",
        encoding="utf-8")
    return path


def main(argv: list[str]) -> int:
    rows = claims()
    args = [arg for arg in argv if not arg.startswith("--")]
    model = MODEL
    for arg in argv:
        if arg.startswith("--model="):
            model = arg.split("=", 1)[1]
    ids = args or sorted(rows)[:3]
    for claim_id in ids:
        if claim_id not in rows:
            print(f"{claim_id}: нет такого утверждения")
            continue
        row = rows[claim_id]
        verdict = review(claim_id, row, model=model)
        path = write_review(claim_id, row, verdict)
        print(f"{claim_id}: {verdict.get('verdict')} -> {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
