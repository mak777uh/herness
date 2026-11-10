"""Помогает ли пауза при блоке DuckDuckGo.

DDG блокирует часть запросов (замер: 4 из 6). Нужно понять, спасает ли
повтор через паузу, или блок держится дольше.

    python work/probe_ddg_retry.py
"""

from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bin"))
import net  # noqa: E402


def attempt(query: str) -> int:
    try:
        page, _, _ = net.fetch("https://html.duckduckgo.com/html/", 200_000, 20,
                               form={"q": query})
        return len(net.parse_ddg(page))
    except net.NetError:
        return -1


def main() -> int:
    query = "tokio rust async"
    for pause in (0, 2, 5, 10):
        if pause:
            print(f"  пауза {pause} с…")
            time.sleep(pause)
        found = attempt(query)
        print(f"  после паузы {pause} с: {'капча' if found == 0 else f'{found} результатов'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
