"""Проверить: блокирует ли DuckDuckGo при частых запросах.

В серии задач net search вернул капчу, а отдельный запрос — 10 результатов.
Гипотеза: DDG блокирует при частых запросах подряд.

    python work/probe_ddg_rate.py [N]
"""

from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bin"))
import net  # noqa: E402


def main(argv: list[str]) -> int:
    count = int(argv[0]) if argv else 6
    ok = 0
    blocked = 0
    for index in range(1, count + 1):
        started = time.time()
        try:
            page, size, _ = net.fetch("https://html.duckduckgo.com/html/", 200_000, 20,
                                       form={"q": f"test query {index}"})
            results = net.parse_ddg(page)
            elapsed = int((time.time() - started) * 1000)
            if results:
                ok += 1
                print(f"  {index}: {len(results)} результатов, {size} байт, {elapsed} мс")
            else:
                blocked += 1
                print(f"  {index}: ПУСТО (капча?), {size} байт, {elapsed} мс")
        except net.NetError as error:
            blocked += 1
            print(f"  {index}: ОТКАЗ {error.code}")
        time.sleep(1.0)
    print(f"\nуспешно: {ok}, заблокировано: {blocked} из {count}")
    return 0 if blocked == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
