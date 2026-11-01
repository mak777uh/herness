"""fetch_url — хостовая загрузка файла по URL, отдельно от моста и отдельно от комнаты.

Зачем: часть внешних наборов недоступна из комнаты (сети нет) и не всегда доступна «в лоб» из
хост-процесса: DNS для некоторых домов не разрешается, а Google Drive отдаёт файл только по
подтверждению. Инструмент делает одну вещь: пробует указанные URL по очереди, пишет то, что
получилось, и **всегда** сохраняет журнал попыток. Успех и неудача одинаково становятся
артефактом.

Важно: это инструмент хоста. Возможность вызывать его **не выдаётся модели** — она не в списке
инструментов комнаты и не маршрутизируется через мост.

    python bin/fetch_url.py --out lab/p27/musique/dev.jsonl --max-bytes 20000000 URL1 URL2 ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path


def try_fetch(url: str, max_bytes: int, timeout: int = 60):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (herness host fetch)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            return None, f"код {response.status}"
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            return None, f"больше лимита {max_bytes} байт"
        if "text/html" in (response.headers.get("Content-Type") or ""):
            # HTML вместо файла — обычно страница подтверждения (Drive) или ошибка.
            return None, "ответ HTML, а не данные"
        return data, f"ок, {len(data)} байт"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="загрузка внешнего файла на хосте")
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-bytes", type=int, default=50_000_000)
    parser.add_argument("--log", default="research/outputs/fetch-url.txt")
    parser.add_argument("urls", nargs="+")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    lines = [f"# Загрузка внешнего файла: {args.out}", ""]
    saved = False
    for url in args.urls:
        try:
            data, note = try_fetch(url, args.max_bytes)
        except Exception as error:  # noqa: BLE001
            lines.append(f"[ERR] {url}")
            lines.append(f"      {type(error).__name__}: {error}")
            continue
        if data is None:
            lines.append(f"[NO ] {url} — {note}")
            continue
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        lines.append(f"[OK ] {url} — {note}")
        lines.append(f"      sha256 {digest}")
        saved = True
        break

    lines.append("")
    lines.append("итог: " + ("файл сохранён" if saved else "ни один URL не отдал данные"))
    text = "\n".join(lines) + "\n"
    log = Path(args.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(text, encoding="utf-8")
    print(text)
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
