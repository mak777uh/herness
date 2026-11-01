"""link_check — проверка доступности ссылок из research/DATA-LINKS.md.

Не «доверять списку»: каждая ссылка получает код ответа. Пишет артефакт, чтобы «проверено»
отличалось от «записано».

    python bin/link_check.py                 # проверить все
    python bin/link_check.py --limit 10      # первые N (быстро)
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research" / "DATA-LINKS.md"
OUT = ROOT / "research" / "outputs" / "link-check.txt"


def urls_from(text: str) -> list[str]:
    found = []
    for raw in re.findall(r"[a-z0-9.\-]+\.(?:com|org|io|dev|ai|edu|net|co)(?:/[^\s|·)]*)?", text):
        url = "https://" + raw.rstrip(".,)")
        if url not in found:
            found.append(url)
    return found


def probe(url: str, timeout: int = 15) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (herness link check)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return f"[{response.status}] {url}"
    except urllib.error.HTTPError as error:
        return f"[{error.code}] {url}"
    except Exception as error:  # noqa: BLE001
        return f"[ERR] {url} — {type(error).__name__}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="проверка ссылок на данные")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    urls = urls_from(SOURCE.read_text(encoding="utf-8"))
    if args.limit:
        urls = urls[: args.limit]
    if not urls:
        print("ссылок не найдено", file=sys.stderr)
        return 2

    lines = [f"# Проверка ссылок: {SOURCE.name}", ""]
    ok = fail = 0
    for url in urls:
        line = probe(url)
        lines.append(line)
        if line.startswith("[2"):
            ok += 1
        else:
            fail += 1
    lines += ["", f"отвечают: {ok}; не отвечают: {fail}; всего: {len(urls)}"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-3:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
