"""live_probe — проверка живого ключа без вывода секрета.

Читает ключ из хранилища DSH, делает один запрос к провайдеру и печатает только статус и длину
ответа. Значение ключа не печатается никогда.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import urllib.error
import urllib.request


def from_store(name: str) -> str | None:
    path = pathlib.Path.home() / ".dsh" / ".credentials.yaml"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^\s*" + re.escape(name) + r"\s*:\s*(.+)$", line)
        if match:
            return match.group(1).strip().strip("\"'")
    return None


def probe(url: str, model: str, key: str, session: str = "") -> dict:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "reply with the single word: ok"}],
        "max_tokens": 8,
    }).encode()
    request = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
        "User-Agent": "herness-live/1.0",
    })
    if session:
        request.add_header("x-opencode-session", session)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            return {"code": response.status, "text": text.strip()[:60], "usage": usage}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        return {"code": exc.code, "error": detail}
    except Exception as exc:
        return {"code": 0, "error": type(exc).__name__ + ": " + str(exc)[:160]}


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "deepseek"
    name = {"deepseek": "DEEPSEEK_API_KEY", "opencode": "OPENCODE_API_KEY",
            "go": "OPENCODE_GO_API_KEY"}.get(which, "DEEPSEEK_API_KEY")
    key = from_store(name)
    if not key:
        print("ключ " + name + " не найден в хранилище")
        return 2

    if which == "go":
        result = probe("https://opencode.ai/inference/go/openai/v1/chat/completions",
                       "deepseek-v4.1-flash", key, session="herness-live")
    elif which == "deepseek":
        result = probe("https://api.deepseek.com/chat/completions", "deepseek-chat", key)
    else:
        result = probe("https://opencode.ai/zen/v1/chat/completions", "deepseek-v4.1-flash-free", key)

    print(name + " -> " + json.dumps(result, ensure_ascii=False)[:400])
    return 0 if result.get("code") == 200 else 1


if __name__ == "__main__":
    sys.exit(main())

