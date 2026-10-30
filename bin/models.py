"""Реестр моделей: список, проверка отклика, цены. Аргумент против прокси — свои семейства моделей."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.http_provider import OpenAICompatProvider  # noqa: E402

BASE = "https://opencode.ai/inference/go/openai/v1"
KEY_ENV = "OPENCODE_GO_API_KEY"
REGISTRY = ROOT / "models.json"

KNOWN = [
    {"id": "deepseek-v4.1-flash", "family": "deepseek", "price_in": 0.15, "price_out": 0.60,
     "role": "основная: дешёвые прогоны, рецензии"},
    {"id": "deepseek-v4-pro", "family": "deepseek", "price_in": 0.66, "price_out": 1.98,
     "role": "рецензент по умолчанию и репликация"},
    {"id": "qwen3.8-flash", "family": "qwen", "price_in": 0.15, "price_out": 0.47,
     "role": "третье семейство для внешней валидности"},
    {"id": "glm-5.3-flash", "family": "glm", "price_in": 0.15, "price_out": 0.50,
     "role": "четвёртое семейство; на анализе длинных документов отдавал пустой ответ"},
    {"id": "mimo-v2.6-flash", "family": "mimo", "price_in": 0.14, "price_out": 0.28,
     "role": "самое дешёвое; не проверялось"},
]


def ping(model: str) -> dict:
    started = time.perf_counter()
    extra = {"x-opencode-session": f"herness-ping-{model}-{int(time.time())}"}
    client = OpenAICompatProvider(BASE, model, KEY_ENV, extra_headers=extra, max_tokens=64)
    if not client.has_key():
        return {"ok": False, "why": "нет ключа"}
    try:
        result = client.complete([{"role": "user", "content": "Ответь одним словом: работает"}],
                                 stream=False)
        text = (getattr(result, "reply", result).text or "").strip()
        return {"ok": bool(text), "seconds": round(time.perf_counter() - started, 1),
                "reply": text[:40]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "why": type(exc).__name__,
                "seconds": round(time.perf_counter() - started, 1)}


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "list"
    data = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {"models": KNOWN}

    if command == "list":
        print(f"{'модель':<22}{'семейство':<12}{'вход/выход':<14}{'роль'}")
        for model in data["models"]:
            print(f"{model['id']:<22}{model['family']:<12}"
                  f"{model['price_in']}/{model['price_out']:<10}{model['role'][:40]}")
        return 0

    if command == "ping":
        targets = argv[1:] or [model["id"] for model in data["models"]]
        results = {}
        for model_id in targets:
            outcome = ping(model_id)
            results[model_id] = outcome
            status = "ok" if outcome["ok"] else f"нет ({outcome.get('why')})"
            print(f"{model_id:<22}{status:<28}{outcome.get('seconds', '')} c "
                  f"{outcome.get('reply', '')}")
        for model in data["models"]:
            if model["id"] in results:
                model["ping"] = results[model["id"]]
        REGISTRY.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\nзаписано: {REGISTRY}")
        return 0

    print("list | ping [модели]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
