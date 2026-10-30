"""Модели рабочего провайдера: ключ берём из ~/.dsh/.credentials.yaml (значение не печатаем)."""

import json
import urllib.request
from pathlib import Path

import yaml

creds = yaml.safe_load(Path.home().joinpath(".dsh", ".credentials.yaml").read_text(encoding="utf-8"))
key = creds.get("OPENCODE_GO_API_KEY") or creds.get("OPENCODE_API_KEY")
print("ключ:", "есть" if key else "нет")

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
