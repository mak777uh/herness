# DSH: магазин плагинов и поиск — что сделано 30.10.2026

## Магазин встроен

| факт | где |
|---|---|
| пакеты `plugin-market`, `plugin-market-index`, `plugin-market-bundle` | внутри `app.asar` |
| инструмент **`plugin_market`** (read-only каталог) + вкладка Discover | README пакета в asar |
| магазин читает **индексы, которые настраивает пользователь** | `plugin_market` описывает «indexes a user configures» |
| установка идёт через `pluginManager.installBundle` | там же |

То есть «поставить из магазина» = добавить индекс, найти плагин, установить. Сам магазин ничего не
качает без индекса.

## Что уже стояло

`dsh-free-search@0.9.7` в профиле `desktop` (в `package.json` зависимость, движков 27, инструменты
`web_search`, `advanced_search`, `multi_search`, `free_search_test`).

**Обновлено до 0.9.21** (в npm была 0.9.21). Бэкап профиля:
`~/.dsh/profiles/desktop-backup-20261030-025105` (`package.json`, `pnpm-lock.yaml`, `cordis.patch.yml`).

## Почему поиск не работал

1. **Плагин не был в дереве загрузчика.** `web_search` уходил в `web-search-deepseek` с ключом
   `****RhZ5` → **401 invalid**.
2. **`insert` в `cordis.patch.yml` не создаёт строку на лету.** Проверено: правка существующей строки
   `web` применилась живьём (ошибка сменилась на `provider "ddg" is not registered`), а вставка новой —
   нет.
3. **Строка в `cordis.yml` применяется при старте.** Профиль: `cordis.yml` — «пустой список, дерево
   собирается патчами».

## Настройка, которая сделана

| что | значение |
|---|---|
| `cordis.yml` | строка `web-search-free` / `dsh-free-search`, `provider: auto`, `fallbackOn: true` |
| `cordis.patch.yml` | `web.searchProvider` возвращён к `deepseek-official` — плагин перехватывает сам, когда загружен |
| переменные пользователя | `HTTPS_PROXY`, `HTTP_PROXY` = `http://127.0.0.1:2080`, `NODE_USE_ENV_PROXY=1` |

Прокси обязателен: без него Node (`fetch`) не ходит наружу — все движки падали с `fetch failed`.

## Замер: 43 движка плагина напрямую

| движок | результат |
|---|---|
| DuckDuckGo html / lite / videos | 0 результатов (капча), через прокси — пусто |
| Bing / Bing Videos | 0–1 результат, заголовки не про запрос (заглушка) |
| SearXNG (публичные: opnxng, priv.au и др.) | **HTTP 429** на всех |
| Exa / Tavily-подобные / Firecrawl / Jina / Keenable / AnySearch | `fetch failed` без ключа |
| Baidu, Aliyun, Doubao, Kimi, Claude, Gemini, DeepSeek | требуют ключа |
| GitHub (наш токен) | 0 результатов |

**Вывод:** с этой сети и без ключей бесплатный веб-поиск недоступен. Дело не в плагине — движки
отвечают пустотой или 429.

## Что осталось сделать (нужен перезапуск DSH)

1. Перезапустить приложение — тогда строка `web-search-free` попадёт в дерево и `ddg` зарегистрируется.
2. Проверить: `web_search` с любым запросом. Если снова 401 — плагин не загрузился, смотреть
   `~/.dsh/profiles/desktop/cordis.yml`.
3. Если нужен рабочий поиск — один из путей:
   - ключ бесплатного тира (Exa, Tavily, Brave) → в настройках плагина;
   - свой SearXNG (контейнер) → `provider: searxng` + адрес инстанса;
   - без поисковика: наши `hs fetch` и адресные API (GitHub, arXiv, endoflife, kernel.org) — они
     работают и дают первоисточники.

## Откат

```
Copy-Item ~/.dsh/profiles/desktop-backup-20261030-025105/* ~/.dsh/profiles/desktop/ -Force
```

Плюс вернуть `dsh-free-search` к 0.9.7 (`pnpm add dsh-free-search@0.9.7` в профиле).

## Границы

- Плагин **не активирован**: строка появится только после перезапуска; это не проверено.
- Замер движков сделан вызовом экспортов плагина напрямую в Node, а не через `web_search`.
- Поиск через ключевые движки не проверялся: ключей нет.
