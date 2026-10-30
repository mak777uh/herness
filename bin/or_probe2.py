"""Диагностика ответа OpenRouter: код и текст ошибки, без ключа."""

import json
import urllib.error
import urllib.request
from pathlib import Path

key = json.loads(Path(r"C:\111\env\secrets\openrouter.json").read_text(encoding="utf-8"))["openrouter"]
print("префикс ключа:", key[:8] + "…", "| длина:", len(key))

for url in ("https://openrouter.ai/api/v1/key", "https://openrouter.ai/api/v1/models"):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}",
                                                   "User-Agent": "herness"})
    try:
        body = urllib.request.urlopen(request, timeout=30).read().decode()
        print(url, "-> 200, байт:", len(body))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        print(url, "-> HTTP", exc.code, "|", detail)
    except Exception as exc:  # noqa: BLE001
        print(url, "-> ошибка", type(exc).__name__)
