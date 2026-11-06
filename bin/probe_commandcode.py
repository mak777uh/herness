"""probe_commandcode — какие модели commandcode годятся для цикла.

Проверка трёхступенчатая, как для OpenRouter: ответ на проверяемый вопрос, соблюдение протокола
одной строки, вызов инструмента из набора комнаты (search, list, read, write, seal).

Ключ берётся из переменной LLL_API_KEY (провайдер commandcode в профиле DSH).

    python bin/probe_commandcode.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.commandcode.ai/provider/v1/chat/completions"

MODELS = [
    "stealth/crouton-alpha",
    "stealth/glyph-cluster:free",
    "reflection/beam:free",
    "deepseek/deepseek-v4.1-flash",
]

PROTOCOL = """Ты работаешь в комнате. Доступны ровно эти инструменты:
search <путь> <подстрока>, list <путь>, read <файл> [строка], write <файл>, seal <файл>.
Отвечай РОВНО одной строкой, без пояснений: TOOL <имя> <аргумент>, DONE <итог> или BLOCKED <почему>.

Задача: в каталоге /mnt лежит файл CLAIMS.md. Нужно найти утверждение C-0042.
Сделай первый шаг."""


def ask(key: str, model: str) -> tuple[bool, str, dict]:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": PROTOCOL}],
                       "max_tokens": 400}).encode()
    request = urllib.request.Request(
        BASE, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read())
        message = data["choices"][0].get("message") or {}
        return True, (message.get("content") or "").strip(), data.get("usage", {})
    except urllib.error.HTTPError as error:
        return False, f"HTTP {error.code}: {error.read()[:120].decode(errors='replace')}", {}
    except Exception as error:  # noqa: BLE001
        return False, f"{type(error).__name__}: {str(error)[:100]}", {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="проверка моделей commandcode")
    parser.add_argument("--model", default=None)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    key = os.environ.get("LLL_API_KEY", "").strip()
    if not key:
        print("нет LLL_API_KEY в окружении")
        return 2
    rows = []
    for model in ([args.model] if args.model else MODELS):
        ok, reply, usage = ask(key, model)
        line = next((item.strip() for item in reply.splitlines() if item.strip()), "")
        follows = line.startswith(("TOOL ", "DONE ", "BLOCKED "))
        tool = line.split()[1] if follows and line.startswith("TOOL ") and len(line.split()) > 1 else ""
        known = tool in ("search", "list", "read", "write", "seal")
        rows.append((model, ok, follows, known, line[:70], usage))
        print(f"{model:32} ответ={'да' if ok else 'нет'} протокол={'да' if follows else 'НЕТ'} "
              f"инструмент={'да' if known else 'НЕТ'} {line[:50]}")

    out = ROOT / "research" / "outputs" / "commandcode-models.txt"
    out.write_text(
        "# Модели commandcode (api.commandcode.ai)\n\n"
        + "\n".join(
            f"- {model}: ответ {'да' if ok else 'нет'}, протокол {'да' if follows else 'НЕТ'}, "
            f"инструмент {'да' if known else 'НЕТ'} — {line}"
            for model, ok, follows, known, line, _usage in rows
        )
        + f"\n\nгодятся для цикла: {sum(1 for _, _, f, k, _, _ in rows if f and k)} из {len(rows)}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
