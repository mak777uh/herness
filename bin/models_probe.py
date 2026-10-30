"""Список моделей у рабочего провайдера: что доступно без OpenRouter."""

import json
import os
import urllib.request

key = os.environ.get("OPENCODE_GO_API_KEY")
if not key:
    print("ключ в env не задан — читаю из файла")
    from pathlib import Path
    raw = Path(r"C:\111\env\secrets\opencode_go_key.txt").read_text(encoding="utf-8").strip()
    key = raw if raw.startswith("sk-") else json.loads(raw)["key"]

request = urllib.request.Request("https://opencode.ai/inference/go/openai/v1/models",
                                 headers={"Authorization": f"Bearer {key}", "User-Agent": "herness"})
try:
    data = json.loads(urllib.request.urlopen(request, timeout=30).read().decode())
    models = data.get("data", [])
    print("моделей:", len(models))
    for model in models:
        print("  ", model.get("id"), "| контекст", model.get("context_length"))
except Exception as exc:  # noqa: BLE001
    print("ошибка:", type(exc).__name__, str(exc)[:140])
