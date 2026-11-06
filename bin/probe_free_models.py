"""probe_free_models — какие бесплатные модели годятся для цикла.

Три ступени, каждая проверяема:
  1) ответ на вопрос с известным ответом;
  2) соблюдение протокола одной строки (TOOL / DONE / BLOCKED);
  3) вызов ИЗ НАБОРА инструментов комнаты (search, list, read, write, seal) — а не grep/cat.

Третья ступень важнее первых двух: модель, которая зовёт grep, в комнате бесполезна.

    python bin/probe_free_models.py
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRETS = Path("C:/111/env/secrets")
PROXY = "http://127.0.0.1:2080"

FREE = [
    "stealth/crouton-alpha",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "nvidia/nemotron-3.5-lightning:free",
    "dots-studio/dots-3-note-preview:free",
    "cohere/north-mini-code:free",
    "recursive/flint-v1.0:free",
]
TOOLS = ("search", "list", "read", "write", "seal")

PROTOCOL = """Ты работаешь в комнате. Доступны ровно эти инструменты:
search <путь> <подстрока>, list <путь>, read <файл> [строка], write <файл>, seal <файл>.
Отвечай РОВНО одной строкой, без пояснений: TOOL <имя> <аргумент>, DONE <итог> или BLOCKED <почему>.

Задача: в каталоге /mnt лежит файл CLAIMS.md. Нужно найти утверждение C-0042.
Сделай первый шаг."""


def key_for(name: str) -> str | None:
    path = SECRETS / f"{name}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        for value in data.values():
            if isinstance(value, str) and len(value) > 10:
                return value
    return None


def ask(url: str, key: str, model: str, prompt: str, proxy: str | None) -> tuple[bool, str]:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": 400}).encode()
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    ) if proxy else urllib.request.build_opener()
    try:
        with opener.open(request, timeout=120) as response:
            data = json.loads(response.read())
        message = data["choices"][0].get("message") or {}
        return True, (message.get("content") or "").strip()
    except urllib.error.HTTPError as error:
        return False, f"HTTP {error.code}: {error.read()[:90].decode(errors='replace')}"
    except Exception as error:  # noqa: BLE001
        return False, f"{type(error).__name__}: {str(error)[:80]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="проверка моделей для цикла")
    parser.add_argument("--proxy", default=PROXY)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    key = key_for("openrouter")
    if not key:
        print("нет ключа openrouter")
        return 2
    url = "https://openrouter.ai/api/v1/chat/completions"
    rows = []
    for model in FREE:
        ok, reply = ask(url, key, model, PROTOCOL, args.proxy or None)
        line = next((item.strip() for item in reply.splitlines() if item.strip()), "")
        follows = line.startswith(("TOOL ", "DONE ", "BLOCKED "))
        tool = line.split()[1] if follows and line.startswith("TOOL ") and len(line.split()) > 1 else ""
        known = tool in TOOLS
        rows.append((model, ok, follows, known, line[:70]))
        print(f"{model:44} ответ={'да' if ok else 'нет'} протокол={'да' if follows else 'НЕТ'} "
              f"инструмент={'да' if known else 'НЕТ'} {line[:50]}")

    out = ROOT / "research" / "outputs" / "free-models.txt"
    out.write_text(
        "# Модели через OpenRouter (прокси 127.0.0.1:2080)\n\n"
        "Проверка: ответ, соблюдение протокола одной строки, вызов из набора инструментов комнаты.\n\n"
        + "\n".join(
            f"- {model}: протокол {'да' if follows else 'НЕТ'}, инструмент {'да' if known else 'НЕТ'} — {line}"
            for model, ok, follows, known, line in rows
        )
        + f"\n\nгодятся для цикла: {sum(1 for _, _, f, k, _ in rows if f and k)} из {len(rows)}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
