"""probe_commandcode — какие модели commandcode годятся для цикла.

Три ступени: ответ на проверяемый вопрос, соблюдение протокола одной строки, вызов инструмента из
набора комнаты (search, list, read, write, seal).

Ключ: LLL_API_KEY или файл C:/111/env/secrets/lll_api_key.txt.
Замечание: без браузерного User-Agent сервер отвечает 403 с кодом 1010 (фильтр ботов).

    python bin/probe_commandcode.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY_FILE = Path("C:/111/env/secrets/lll_api_key.txt")
BASE = "https://api.commandcode.ai/provider/v1/chat/completions"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

MODELS = [
    "stealth/glyph-cluster:free",
    "stealth/crouton-alpha",
    "reflection/beam:free",
    "deepseek/deepseek-v4.1-flash",
]

PROTOCOL = """Ты работаешь в комнате. Доступны ровно эти инструменты:
search <путь> <подстрока>, list <путь>, read <файл> [строка], write <файл>, seal <файл>.
Отвечай РОВНО одной строкой, без пояснений: TOOL <имя> <аргумент>, DONE <итог> или BLOCKED <почему>.

Задача: в каталоге /mnt лежит файл CLAIMS.md. Нужно найти утверждение C-0042.
Сделай первый шаг."""


def key() -> str:
    value = os.environ.get("LLL_API_KEY", "").strip()
    if value:
        return value
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    return ""


def ask(token: str, model: str, attempts: int = 3) -> tuple[bool, str, dict]:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": PROTOCOL}],
                       "max_tokens": 400}).encode()
    last = ""
    for attempt in range(attempts):
        request = urllib.request.Request(
            BASE, data=body, method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "User-Agent": UA},
        )
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                data = json.loads(response.read())
            message = data["choices"][0].get("message") or {}
            return True, (message.get("content") or "").strip(), data.get("usage", {})
        except urllib.error.HTTPError as error:
            last = f"HTTP {error.code}: {error.read()[:100].decode(errors='replace')}"
            if error.code in (524, 503, 502, 429):
                time.sleep(10 * (attempt + 1))
                continue
            return False, last, {}
        except Exception as error:  # noqa: BLE001
            last = f"{type(error).__name__}: {str(error)[:80]}"
            time.sleep(5)
    return False, last, {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="проверка моделей commandcode")
    parser.add_argument("--model", default=None)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    token = key()
    if not token:
        print("нет ключа: LLL_API_KEY или C:/111/env/secrets/lll_api_key.txt")
        return 2
    rows = []
    for model in ([args.model] if args.model else MODELS):
        ok, reply, usage = ask(token, model)
        line = next((item.strip() for item in reply.splitlines() if item.strip()), "")
        follows = line.startswith(("TOOL ", "DONE ", "BLOCKED "))
        tool = line.split()[1] if follows and line.startswith("TOOL ") and len(line.split()) > 1 else ""
        known = tool in ("search", "list", "read", "write", "seal")
        rows.append((model, ok, follows, known, line[:70]))
        print(f"{model:30} ответ={'да' if ok else 'нет'} протокол={'да' if follows else 'НЕТ'} "
              f"инструмент={'да' if known else 'НЕТ'} {line[:45] or reply[:60]}")

    out = ROOT / "research" / "outputs" / "commandcode-models.txt"
    text = out.read_text(encoding="utf-8") if out.exists() else "# Модели commandcode\n\n"
    text = text.split("\n# Проверка")[0].rstrip() + "\n\n# Проверка протокола (ключ есть)\n\n"
    text += "\n".join(
        f"- {model}: ответ {'да' if ok else 'нет'}, протокол {'да' if follows else 'НЕТ'}, "
        f"инструмент {'да' if known else 'НЕТ'} — {line or reply[:60]}"
        for model, ok, follows, known, line in rows
    )
    text += f"\n\nгодятся для цикла: {sum(1 for _, _, f, k, _ in rows if f and k)} из {len(rows)}\n"
    out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
