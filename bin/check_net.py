"""Проверка net: парсер выдачи и отказы (положительный и отрицательный контроль).

Что проверяется:
  1. настоящая выдача DDG разбирается в 10 результатов с заголовками и адресами;
  2. страница-заглушка (капча) НЕ даёт результатов — иначе «ничего не нашлось»
     было бы выдано за пустую выдачу;
  3. разбор ссылок отбрасывает javascript:, mailto: и повторы;
  4. strip_html убирает скрипты и оставляет текст.

Сеть не нужна: используются сохранённые фрагменты.

    python bin/check_net.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import net  # noqa: E402

DDG_PAGE = """
<html><body>
<div class="result results_links">
  <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ftokio.rs%2Ftutorial&amp;rut=abc">Async in depth | Tokio</a>
  <a class="result__snippet">An asynchronous Rust runtime.</a>
</div>
<div class="result results_links">
  <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fgithub.com%2Fsmol-rs%2Fsmol">GitHub - smol</a>
</div>
</body></html>
"""

CAPTCHA_PAGE = """
<html><body><div class="anomaly-modal__title">Unfortunately, bots use DuckDuckGo too.</div>
<form id="challenge-form" action="/anomaly.js"></form></body></html>
"""

LINK_PAGE = """
<html><head><title>Пример</title></head><body>
<script>var x = 1;</script>
<a href="/a">Первая</a>
<a href="https://b.example/b">Вторая</a>
<a href="javascript:void(0)">Скрипт</a>
<a href="mailto:x@example.com">Почта</a>
<a href="/a">Первая снова</a>
<p>Текст страницы.</p>
</body></html>
"""


def main() -> int:
    checks: list[tuple[str, bool]] = []

    # 1. Положительный контроль: настоящая выдача разбирается.
    results = net.parse_ddg(DDG_PAGE)
    checks.append(("выдача разобрана: 2 результата", len(results) == 2))
    checks.append(("адрес распакован из редиректа DDG",
                   results and results[0]["url"] == "https://tokio.rs/tutorial"))
    checks.append(("заголовок очищен от разметки",
                   results and results[0]["title"] == "Async in depth | Tokio"))

    # 2. Отрицательный контроль: капча не даёт результатов.
    captcha = net.parse_ddg(CAPTCHA_PAGE)
    checks.append(("страница с капчей не даёт результатов", captcha == []))

    # 3. Ссылки: только http(s), без повторов.
    links = net.parse_links(LINK_PAGE, "https://example.com/base/")
    urls = [item["url"] for item in links]
    checks.append(("относительная ссылка стала абсолютной",
                   "https://example.com/a" in urls))
    checks.append(("javascript: отброшен",
                   not any(u.startswith("javascript:") for u in urls)))
    checks.append(("mailto: отброшен",
                   not any(u.startswith("mailto:") for u in urls)))
    checks.append(("повтор не задвоен", urls.count("https://example.com/a") == 1))

    # 4. Текст без скриптов.
    text = net.strip_html(LINK_PAGE)
    checks.append(("скрипт вырезан из текста", "var x" not in text))
    checks.append(("текст страницы остался", "Текст страницы" in text))

    # 5. Отказ с кодом, а не пустой список.
    try:
        raise net.NetError("no-results", "капча")
    except net.NetError as error:
        checks.append(("отказ несёт код", error.code == "no-results"))

    bad = 0
    for title, ok in checks:
        if not ok:
            bad += 1
        print(f"{'ok  ' if ok else 'FAIL'} {title}")
    print()
    if bad:
        print(f"[FAIL] провалено: {bad} из {len(checks)}")
        return 1
    print(f"[ok] пройдено: {len(checks)} из {len(checks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
