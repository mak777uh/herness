"""Ищем отчёты proof-of-usefulness: список статей по тегу."""

import json
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 herness"}
URLS = [
    "https://hackernoon.com/tagged/proof-of-usefulness-hackathon",
    "https://hackernoon.com/tagged/proof-of-usefulness",
]

for url in URLS:
    try:
        request = urllib.request.Request(url, headers=UA)
        html = urllib.request.urlopen(request, timeout=30).read().decode("utf-8", "replace")
        print(f"{url}: {len(html)} байт")
        links = re.findall(r'href="(https://hackernoon\.com/[a-z0-9-]+)"', html)
        seen = []
        for link in links:
            if link not in seen and "tagged" not in link:
                seen.append(link)
        print("статей найдено:", len(seen))
        for link in seen[:15]:
            print("  ", link)
        titles = re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S)
        cleaned = [re.sub(r"<[^>]+>", "", t).strip()[:90] for t in titles[:10]]
        print("заголовки:", json.dumps(cleaned, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        print(f"{url}: ошибка {type(exc).__name__}")
