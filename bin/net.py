"""net — командная строка выхода в сеть для агента: search, open, links, follow.

Зачем своя, если есть `hs fetch` и `hs browser` (ADR-0054):

* `fetch` берёт ОДИН адрес и не помнит, откуда он взялся; агенту нужна сессия:
  нашёл → открыл → перешёл по ссылке с этой страницы;
* `browser` поднимает Chrome и решает капчу, но это секунды и мегабайты; для
  обычного чтения он лишний вес (ADR-0032).

Из первых принципов, что делает её «для агентов»:

1. **Номера вместо адресов.** Агент получает `1, 2, 3…` и говорит `open 3`.
   Это дешевле по токенам и не даёт уйти на произвольный адрес — только на тот,
   что реально был в выдаче или на странице.
2. **Текст, а не разметка.** HTML в 10–50 раз дороже и содержит мусор.
3. **Бюджет и явная обрезка.** `обрезано: да` в ответе, а не тихое усечение.
4. **Отказ с кодом, а не пустой список.** Пустой результат выглядит как «ничего не
   нашлось» и врёт; капча и блок — это UNKNOWN, а не «нет результатов».

Поиск: DuckDuckGo HTML. Замер 08.11.2026 показал, что Google с `udm=14` и `gbv=1`
отдаёт JS-заглушку (`enablejs`) без выдачи, а DDG HTML — 10 результатов за ~1,4 с
на двух языках. Поэтому поиск через DDG, и это записано в ADR-0054.

    python bin/net.py search "rust async runtime"
    python bin/net.py open 3
    python bin/net.py open https://example.com
    python bin/net.py links
    python bin/net.py follow 2
"""

from __future__ import annotations

import argparse
import html as htmlmod
import json
import pathlib
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "runs" / "net"
SESSION = STATE / "session.json"
JOURNAL = STATE / "net.jsonl"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

DEFAULT_MAX_BYTES = 200_000
DEFAULT_TIMEOUT = 20


class NetError(Exception):
    """Отказ с кодом: агент должен видеть причину, а не пустой список."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def journal(event: dict) -> None:
    """Журнал переходов: адрес, код, байты, время. Содержимое не пишем."""
    STATE.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": now(), **event}, ensure_ascii=False) + "\n")


def load_session() -> dict:
    if not SESSION.exists():
        return {"results": [], "links": [], "page": None}
    try:
        return json.loads(SESSION.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"results": [], "links": [], "page": None}


def save_session(session: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    SESSION.write_text(json.dumps(session, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")


def normalize_url(url: str) -> str:
    """Привести адрес к виду, который принимает urllib.

    Две вещи, обе проверены на Википедии 08.11.2026:
      * путь с кириллицей кодируется в percent-форму (иначе UnicodeEncodeError);
      * домен с кириллицей переводится в punycode (иначе DNS не найдёт его).
    """
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    netloc = host
    if parts.port:
        netloc = f"{host}:{parts.port}"
    path = urllib.parse.quote(parts.path, safe="/%:@&=+$,;~()!*'")
    query = urllib.parse.quote(parts.query, safe="=&%:@+$,;~()!*'/")
    return urllib.parse.urlunsplit((parts.scheme, netloc, path, query, ""))


def fetch(url: str, max_bytes: int, timeout: int, form: dict | None = None) -> tuple[str, int, bool]:
    """Забрать страницу. Возвращает (текст, размер, обрезано ли).

    Кириллица в адресе кодируется в percent-форму: urllib требует ASCII в
    строке запроса, и без этого «Википедия» падала с UnicodeEncodeError.
    Кириллический домен дополнительно переводится в punycode.
    """
    url = normalize_url(url)
    data = urllib.parse.urlencode(form).encode() if form else None
    request = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout,
                                    context=ssl.create_default_context()) as response:
            raw = response.read(max_bytes + 1)
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as error:
        raise NetError("http", f"HTTP {error.code} на {url}") from error
    except urllib.error.URLError as error:
        raise NetError("network", f"нет связи с {url}: {error.reason}") from error
    except TimeoutError as error:
        raise NetError("timeout", f"таймаут {timeout} с на {url}") from error
    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode(charset, errors="replace")
    return text, len(raw[:max_bytes]), truncated


def strip_html(page: str) -> str:
    """Читаемый текст: убрать скрипты, стили и разметку."""
    page = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?is)<!--.*?-->", " ", page)
    page = re.sub(r"(?i)<br\s*/?>", "\n", page)
    page = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|section|article)>", "\n", page)
    page = re.sub(r"<[^>]+>", " ", page)
    page = htmlmod.unescape(page)
    page = re.sub(r"[ \t\u00a0]+", " ", page)
    page = re.sub(r"\n\s*\n\s*\n+", "\n\n", page)
    return page.strip()


def page_title(page: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", page)
    return htmlmod.unescape(re.sub(r"\s+", " ", match.group(1))).strip() if match else ""


def parse_ddg(page: str) -> list[dict]:
    """Разобрать выдачу DuckDuckGo HTML.

    Отрицательный контроль: страница с капчей не содержит `result__a`, поэтому
    даёт пустой список — и вызывающий код обязан превратить это в отказ, а не
    в «ничего не нашлось».
    """
    results = []
    for match in re.finditer(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        page, re.S,
    ):
        href, title = match.group(1), match.group(2)
        clean_title = htmlmod.unescape(re.sub(r"<[^>]+>", "", title)).strip()
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        real = parsed.get("uddg", [href])[0]
        if not clean_title or not real.startswith("http"):
            continue
        results.append({"title": clean_title, "url": real})
    return results


# Служебные пути, которые не ведут к содержанию. Агент платит за них токенами,
# а переходит по ним впустую: «Sign in», «Copilot», «Pricing» на каждой странице.
NOISE = (
    "/login", "/signup", "/signin", "/register", "/pricing", "/features/",
    "/enterprise", "/security", "/marketplace", "/topics", "/collections",
    "/sponsors", "/about", "/contact", "/legal", "/privacy", "/terms",
    "/settings", "/notifications", "/explore", "/trending", "/solutions",
    "/platform", "/resources", "/customers", "/careers", "/blog",
)

# Метки, которые тоже не содержание: навигация и призывы.
NOISE_LABELS = {
    "sign in", "sign up", "log in", "login", "register", "pricing", "about",
    "contact", "careers", "blog", "privacy", "terms", "security", "enterprise",
    "copilot", "actions", "codespaces", "issues", "pull requests", "marketplace",
    "explore", "topics", "collections", "sponsors", "settings", "notifications",
    "skip to content", "navigation menu", "github", "home", "search",
}


def is_noise(url: str, label: str) -> bool:
    """Служебная ли ссылка: навигация сайта, а не содержание.

    Порог намеренно мягкий: лучше показать лишнюю ссылку, чем спрятать нужную.
    Отбрасываем только явное — известные разделы сайта и подписи-призывы.
    """
    low = label.strip().lower()
    if low in NOISE_LABELS:
        return True
    path = urllib.parse.urlparse(url).path.lower()
    if path in ("", "/"):
        return True
    return any(path == item or path.startswith(item) for item in NOISE)


def content_region(page: str) -> str:
    """Вырезать основное содержимое страницы, если разметка его помечает.

    Замер 08.11.2026: на Википедии и GitHub ссылки со всей страницы — это меню
    и подвал («Заглавная», «Содержание», «Sign in»), а не содержание. Агент
    платит за них токенами и переходит впустую.

    Берём ОТ НАЧАЛА контейнера до конца страницы, а не до закрывающего тега:
    страница обрезана по бюджету, закрывающего тега может не быть вовсе, и
    поиск пары молча не срабатывал (Википедия: <main> на позиции 62 247, а
    регулярка до </main> не находила ничего).
    """
    for marker in (
        'id="mw-parser-output"',
        'id="mw-content-text"',
        "<main",
        "<article",
        'id="content"',
    ):
        at = page.find(marker)
        if at > 0:
            tail = page[at:]
            if len(tail) > 2000:
                return tail
    return page


def parse_links(page: str, base: str) -> list[dict]:
    """Ссылки страницы: только http(s), абсолютные, без повторов и служебных.

    Сначала пробуем содержимое; если оттуда набралось меньше трёх ссылок —
    берём всю страницу, чтобы не потерять навигацию по главам и статьям.
    """
    region = content_region(page)
    links = _links_from(region, base)
    if len(links) < 3 and region is not page:
        links = _links_from(page, base)
    return links


def _links_from(page: str, base: str) -> list[dict]:
    seen: set[str] = set()
    links: list[dict] = []
    for match in re.finditer(r'<a[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', page, re.S | re.I):
        href, text = match.group(1), match.group(2)
        absolute = urllib.parse.urljoin(base, htmlmod.unescape(href))
        if not absolute.startswith(("http://", "https://")):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        label = htmlmod.unescape(re.sub(r"<[^>]+>", " ", text))
        label = re.sub(r"\s+", " ", label).strip()
        if is_noise(absolute, label):
            continue
        links.append({"title": label[:120] or absolute, "url": absolute})
    return links


def cmd_search(args) -> int:
    query = " ".join(args.query) if isinstance(args.query, list) else args.query
    text, size, truncated = fetch("https://html.duckduckgo.com/html/",
                                  args.max_bytes, args.timeout, form={"q": query})
    results = parse_ddg(text)
    journal({"cmd": "search", "query": query, "bytes": size, "found": len(results)})
    if not results:
        # Пустой список — это не «ничего не нашлось»: DDG мог отдать капчу.
        raise NetError("no-results",
                       "DuckDuckGo не вернул результатов (возможна капча или блок)")
    session = load_session()
    session["results"] = results
    save_session(session)
    print(f"найдено: {len(results)}{' (обрезано)' if truncated else ''}")
    for i, item in enumerate(results, 1):
        print(f"{i}. {item['title']}")
        print(f"   {item['url']}")
    return 0


def open_url(url: str, args, session: dict) -> int:
    page, size, truncated = fetch(url, args.max_bytes, args.timeout)
    text = strip_html(page)
    title = page_title(page)
    links = parse_links(page, url)
    journal({"cmd": "open", "url": url, "bytes": size, "truncated": truncated,
             "links": len(links)})
    session["page"] = {"url": url, "title": title}
    session["links"] = links
    save_session(session)
    print(f"страница: {title or '(без заголовка)'}")
    print(f"адрес: {url}")
    print(f"байт: {size}{'  обрезано: да' if truncated else ''}")
    print(f"ссылок: {len(links)}")
    print()
    limit = args.chars
    print(text[:limit])
    if len(text) > limit:
        print(f"\n[текст обрезан: показано {limit} из {len(text)} символов]")
    return 0


def cmd_open(args) -> int:
    session = load_session()
    target = args.target.strip()
    if target.isdigit():
        index = int(target)
        pool = session.get("results") or session.get("links") or []
        if not pool:
            raise NetError("no-list", "нечего открывать: сначала search или links")
        if not 1 <= index <= len(pool):
            raise NetError("bad-index", f"номер {index} вне списка (1..{len(pool)})")
        return open_url(pool[index - 1]["url"], args, session)
    if not target.startswith(("http://", "https://")):
        raise NetError("bad-url", f"адрес должен начинаться с http(s): {target}")
    return open_url(target, args, session)


def cmd_links(args) -> int:
    session = load_session()
    page = session.get("page")
    links = session.get("links") or []
    if not page:
        raise NetError("no-page", "страница не открыта: сначала open")
    if not links:
        raise NetError("no-links", f"на странице нет ссылок: {page.get('url')}")
    journal({"cmd": "links", "url": page.get("url"), "count": len(links)})
    print(f"страница: {page.get('title') or page.get('url')}")
    for i, item in enumerate(links[: args.limit], 1):
        print(f"{i}. {item['title'][:80]}")
        print(f"   {item['url']}")
    if len(links) > args.limit:
        print(f"... ещё {len(links) - args.limit} (--limit чтобы показать больше)")
    return 0


def cmd_follow(args) -> int:
    session = load_session()
    links = session.get("links") or []
    if not links:
        raise NetError("no-links", "нет ссылок: сначала open страницы")
    index = args.number
    if not 1 <= index <= len(links):
        raise NetError("bad-index", f"номер {index} вне списка (1..{len(links)})")
    return open_url(links[index - 1]["url"], args, session)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="выход в сеть для агента")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
        p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
        p.add_argument("--chars", type=int, default=6000)
        p.add_argument("--json", action="store_true")

    # Запрос приходит строкой: из комнаты мост передаёт «search rust async runtime»
    # без кавычек, и argparse иначе разбил бы его на три аргумента. Склеиваем
    # остаток в один запрос — агенту не нужно помнить про кавычки.
    search = sub.add_parser("search", help="поиск через DuckDuckGo HTML")
    search.add_argument("query", nargs="+", help="слова запроса")
    common(search)

    open_p = sub.add_parser("open", help="открыть страницу по номеру или адресу")
    open_p.add_argument("target")
    common(open_p)

    links = sub.add_parser("links", help="ссылки текущей страницы")
    links.add_argument("--limit", type=int, default=20)
    common(links)

    follow = sub.add_parser("follow", help="перейти по ссылке с текущей страницы")
    follow.add_argument("number", type=int)
    common(follow)

    args = parser.parse_args(argv)
    handlers = {"search": cmd_search, "open": cmd_open,
                "links": cmd_links, "follow": cmd_follow}
    try:
        return handlers[args.cmd](args)
    except NetError as error:
        journal({"cmd": args.cmd, "error": error.code, "message": error.message})
        if getattr(args, "json", False):
            print(json.dumps({"error": error.code, "message": error.message},
                             ensure_ascii=False))
        else:
            print(f"ОТКАЗ {error.code}: {error.message}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
