"""Какие поисковики переживают блок DuckDuckGo.

DDG заблокировал IP (капча держится >10 с). Нужен план Б: проверить
альтернативы, которые раньше отвечали.

    python work/probe_alternatives.py
"""

from __future__ import annotations

import re
import ssl
import sys
import time
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

TARGETS = [
    ("mojeek", "https://www.mojeek.com/search?q=tokio+rust"),
    ("marginalia", "https://marginalia-search.com/search?query=tokio+rust"),
    ("lite-ddg", "https://lite.duckduckgo.com/lite/?q=tokio+rust"),
    ("startpage", "https://www.startpage.com/sp/search?query=tokio+rust"),
    ("brave", "https://search.brave.com/search?q=tokio+rust"),
    ("searx-be", "https://searx.be/search?q=tokio+rust"),
]


def main() -> int:
    for name, url in TARGETS:
        request = urllib.request.Request(url, headers={"User-Agent": UA})
        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=20,
                                        context=ssl.create_default_context()) as response:
                body = response.read(300_000).decode("utf-8", errors="replace")
                code = response.status
        except urllib.error.HTTPError as error:
            body = ""
            code = error.code
        except Exception as error:  # noqa: BLE001
            print(f"{name:12} ОШИБКА {type(error).__name__}")
            continue
        elapsed = int((time.time() - started) * 1000)
        links = len(re.findall(r'href="https?://', body))
        captcha = "captcha" in body.lower() or "unusual traffic" in body.lower()
        verdict = "капча" if captcha else ("ok" if links > 5 else "мало ссылок")
        print(f"{name:12} {code} {len(body):>7} байт {elapsed:>5} мс "
              f"ссылок {links:>4}  {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
