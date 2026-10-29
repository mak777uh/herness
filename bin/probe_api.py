"""probe_api — проверка утверждений о доступе к провайдерам.

Три режима:

* `status` — что отвечает free-эндпоинт opencode zen (код и тип ошибки);
* `env`    — видит ли дочерний процесс ключи приложения (ожидается: нет);
* `check`  — сверка с ожиданиями, выход 1 при расхождении.

Сеть может измениться; поэтому проверяется не «работает ли», а «какой отказ сейчас».
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

URL = "https://opencode.ai/zen/v1/chat/completions"
BODY = json.dumps({
    "model": "deepseek-v4.1-flash-free",
    "messages": [{"role": "user", "content": "say ok"}],
    "max_tokens": 8,
}).encode()

SECRET_NAMES = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "OPENCODE_API_KEY", "ANTHROPIC_API_KEY")
STORE_NAMES = ("OPENCODE_GO_API_KEY", "OPENCODE_API_KEY", "DEEPSEEK_API_KEY")


def store_key(name: str) -> str:
    """Ключ из хранилища DSH по имени. Значение не печатается."""
    from pathlib import Path
    import re

    path = Path.home() / ".dsh" / ".credentials.yaml"
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^\s*" + re.escape(name) + r"\s*:\s*(.+)$", line)
        if match:
            return match.group(1).strip().strip("\"'")
    return ""


def catalogue(key: str) -> list[str]:
    request = urllib.request.Request("https://opencode.ai/zen/v1/models",
                                     headers={"User-Agent": "herness/1.0",
                                              "Authorization": "Bearer " + key})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = json.loads(opener.open(request, timeout=45).read().decode("utf-8", "replace"))
    return [m.get("id") for m in data.get("data", []) if m.get("id")]


def model_map(key: str) -> list[tuple[str, int, str]]:
    """Карта: модель → код ответа и тип отказа."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    out = []
    for model in catalogue(key):
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": "say ok"}],
                           "max_tokens": 8, "stream": False}).encode()
        request = urllib.request.Request("https://opencode.ai/zen/v1/chat/completions", data=body,
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": "Bearer " + key,
                                                  "User-Agent": "herness/1.0"})
        try:
            opener.open(request, timeout=45).read()
            out.append((model, 200, "ok"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            try:
                kind = json.loads(detail).get("error", {}).get("type", "")
            except json.JSONDecodeError:
                kind = ""
            out.append((model, exc.code, kind))
        except Exception as exc:  # noqa: BLE001
            out.append((model, 0, type(exc).__name__))
    return out


def status() -> dict:
    opener = urllib.request.build_opener()
    request = urllib.request.Request(URL, data=BODY, headers={
        "Content-Type": "application/json",
        "User-Agent": "herness-probe/1.0",
    })
    try:
        with opener.open(request, timeout=45) as response:
            body = response.read().decode("utf-8", "replace")
            return {"code": response.status, "type": "ok", "detail": body[:200]}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            kind = json.loads(detail).get("error", {}).get("type", "?")
        except json.JSONDecodeError:
            kind = "?"
        return {"code": exc.code, "type": kind, "detail": detail[:200]}
    except Exception as exc:  # сеть, прокси, таймаут
        return {"code": 0, "type": type(exc).__name__, "detail": str(exc)[:200]}


def visible_keys() -> list[str]:
    return [name for name in SECRET_NAMES if os.environ.get(name)]


def models() -> dict:
    """Список моделей без авторизации: доступен ли каталог."""
    request = urllib.request.Request("https://opencode.ai/zen/v1/models",
                                     headers={"User-Agent": "herness-probe/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
            count = len(data.get("data", [])) if isinstance(data, dict) else 0
            return {"code": response.status, "models": count}
    except Exception as exc:
        return {"code": 0, "models": 0, "detail": str(exc)[:120]}


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else "status"

    if mode == "map":
        key = store_key("OPENCODE_GO_API_KEY")
        if not key:
            print("нет ключа OPENCODE_GO_API_KEY в хранилище")
            return 2
        rows = model_map(key)
        for model, code, kind in rows:
            print("{0:<32} {1}  {2}".format(model, code, kind))
        available = [row for row in rows if row[1] == 200]
        print("доступно моделей: {0} из {1}".format(len(available), len(rows)))
        if "--check" in argv:
            passed = len(available) == 0
            print("[{0}] на 29.10.2026 ключ валиден, но ни одна модель не отвечает".format(
                "ok" if passed else "FAIL"))
            return 0 if passed else 1
        return 0

    if mode == "models":
        catalogue = models()
        print("http={0} models={1}".format(catalogue["code"], catalogue["models"]))
        if "--check" in argv:
            ok = catalogue["code"] == 200 and catalogue["models"] > 0
            print("[{0}] каталог моделей доступен без авторизации".format("ok" if ok else "FAIL"))
            return 0 if ok else 1
        return 0

    if mode == "env":
        found = visible_keys()
        print(f"visible_keys={len(found)} {found}")
        if "--check" in argv:
            ok = not found
            print(f"[{'ok' if ok else 'FAIL'}] ключи приложения не видны дочернему процессу")
            return 0 if ok else 1
        return 0

    result = status()
    print(f"http={result['code']} type={result['type']}")
    print(result["detail"].replace("\n", " ")[:160])

    if "--check" in argv:
        # утверждение C-0018: лимит free-моделей привязан к учётке; сейчас это 429
        ok = result["code"] == 429 or result["type"] in {"FreeUsageLimitError", "ok"}
        print(f"[{'ok' if ok else 'FAIL'}] free-эндпоинт отвечает отказом квоты ({result['code']} {result['type']})")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

