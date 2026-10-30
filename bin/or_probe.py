"""Проверка доступа к OpenRouter: без печати ключа."""

import json
import urllib.request
from pathlib import Path

SECRET = Path(r"C:\111\env\secrets\openrouter.json")
data = json.loads(SECRET.read_text(encoding="utf-8"))
print("поля файла:", sorted(data) if isinstance(data, dict) else type(data).__name__)

key = None
if isinstance(data, dict):
    for field in ("api_key", "key", "token", "API_KEY", "openrouter"):
        value = data.get(field)
        if isinstance(value, str) and value.startswith("sk-or"):
            key = value
            break
    if key is None:
        for value in data.values():
            if isinstance(value, str) and value.startswith("sk-or"):
                key = value
                break
print("ключ найден:", bool(key), "| длина:", len(key) if key else 0)

if key:
    for url, label in (("https://openrouter.ai/api/v1/key", "ключ"),
                       ("https://openrouter.ai/api/v1/models", "модели")):
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}",
                                                       "User-Agent": "herness"})
        try:
            body = json.loads(urllib.request.urlopen(request, timeout=30).read().decode())
        except Exception as exc:  # noqa: BLE001
            print(f"{label}: ошибка {type(exc).__name__}")
            continue
        if label == "ключ":
            info = body.get("data", {})
            print("ключ: лимит", info.get("limit"), "| израсходовано", info.get("usage"),
                  "| free_tier", info.get("is_free_tier"), "| rate", info.get("rate_limit"))
        else:
            models = body.get("data", [])
            free = [model for model in models if str(model.get("id", "")).endswith(":free")]
            print(f"моделей всего: {len(models)}, бесплатных (:free): {len(free)}")
            for model in free[:8]:
                print("   ", model.get("id"), "| контекст", model.get("context_length"))
