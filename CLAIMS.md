# CLAIMS.md — реестр утверждений

Тип свидетельства задаёт **предельную силу формулировки**. Формулировка сильнее типа — дефект.

| тип | что это | что разрешает утверждать |
|---|---|---|
| `proof` | машинно-проверенное доказательство | «доказано для указанной формализации» |
| `test` | воспроизводимый прогон с оракулом | «на этом входе получен этот результат» |
| `statistics` | измерение с бюджетом и разбросом | «p50/p95 такие-то на таком-то железе» |
| `observation` | единичное наблюдение | «наблюдали один раз при таких условиях» |
| `judgment` | суждение владельца | «считаем разумным, не проверено» |

## Утверждения

| id | утверждение | тип | команда | артефакт | дата |
|---|---|---|---|---|---|
| C-0001 | `dsh --version` на этой машине = `0.2.1-rc.3` | observation | `python bin/hs.py facts` | `runs/` | 29.10.2026 | `0\.2\.1-rc\.3` |
| C-0002 | DSH поднимается из изолированного `DSH_HOME` с профилем `headless`, не изменяя установку | observation | `python bin/hs.py doctor` | `docs/DECISION-0001*` | 29.10.2026 | `5/5 ok` |
| C-0003 | Пакеты DSH опубликованы в npm и допускают использование вне Electron-приложения | observation | `python bin/hs.py facts` | `docs/DECISION-0001*` | 29.10.2026 |
| C-0004 | Холодный старт headless-профиля (dump-config, без модели) p50 = 0,46 с на этой машине | statistics | `python bin/hs.py bench -n 3` | вывод команды, 29.10.2026 | 29.10.2026 | `p50` |
| C-0005 | IronClaw (nearai) применяет инъекцию ключей на границе хоста, allowlist эндпоинтов и скан утечек | observation | `python bin/hs.py refs search "wasm sandbox credentials allowlist leak"` | `refs-cache/nearai/ironclaw/README.md` | 29.10.2026 |
| C-0006 | Гейты отбивают посаженные нарушения: контракты 20/20, семь наборов тестов зелёные | test | `python bin/hs.py selftest` | вывод команды, 29.10.2026 (обновлено) | 29.10.2026 | `20/20` |
| C-0007 | Тулчейны на машине на 29.10.2026 занимают 11,61 ГБ (было 8,65 утром): Lean 3 тулчейна, Rust, Foundry; cargo 1.99.1, forge 1.8.5 | observation | `python bin/hs.py tools` | вывод команды, 29.10.2026 | 29.10.2026 (обновлено) | `11.61` |
| C-0008 | Тулчейн `leanprover/lean4:v4.36.0-rc1` (0,2 ГБ) не содержит `lake` и проекты не собирает; 4.30.0 и 4.33.1 полные | observation | `python bin/hs.py tools` | вывод команды, 29.10.2026 | 29.10.2026 | `lake` |
| C-0009 | Записать результат инструмента без проверенного артефакта невозможно; порядок событий: run/start → tool/call → tool/result → assistant/message → run/end | test | `python tests/test_m1_journal.py` | вывод 5/5, 29.10.2026 | 29.10.2026 | `5/5 ok` |
| C-0010 | Через opencode API сейчас нельзя получить ответ модели: free-модели дают 429 (квота исчерпана), платная с OPENCODE_API_KEY — 401 (не ключ), с OPENCODE_GO_API_KEY — 402 (нет средств) | observation | проба сабагента, 29.10.2026: GET /models → 200 (82 модели), chat/completions → 429/401/402 | вывод пробы в отчёте сессии | 29.10.2026 |
| C-0011 | BaseURL https://opencode.ai/zen/v1 и список моделей доступны без авторизации | observation | GET /v1/models без ключа → 200 | то же | 29.10.2026 |

Правило пополнения: новая строка — только вместе с командой, дайджестом артефакта и датой.
Опровергнутая строка не удаляется, а переводится в `docs/eliminations.md` со ссылкой.

| C-0012 | Запуск dsh headless из CLI без креденшелов падает MISSING_CREDENTIAL; DEEPSEEK_API_KEY из ~/.dsh/.credentials.yaml невалиден (HTTP 401) | observation | `python -c "import pathlib;logs=list(pathlib.Path('runs').glob('*/stderr.log'));hit=any('MISSING_CREDENTIAL' in f.read_text(errors='replace') for f in logs);print('MISSING_CREDENTIAL' if hit else 'not found');raise SystemExit(0 if hit else 1)"` | runs/*/stderr.log | 29.10.2026 (обновлено) | `MISSING_CREDENTIAL` |
| C-0013 | Ключи приложения недоступны дочернему процессу: креденшелы живут в сервисе DSH, а не в файле | observation | три прогона с --home и с env-ключом, все без инференса | runs/20261029T15* | 29.10.2026 |


| C-0014 | В выборке 30 сессий 20 % обходятся без инструментов; медиана 11 вызовов, p90 = 94, максимум 174 | statistics | выборка 30 сессий из ~/.dsh/sessions, подсчёт tool/call | вывод команды, 29.10.2026 | 29.10.2026 |
| C-0015 | По всем 266 сессиям: 16,9 % без вызовов инструментов; медиана 40,5 вызова; p90 = 141; максимум 7026; 22,0 % всех вызовов — повтор той же команды в той же сессии | statistics | python bin/dist_stats.py | research/sessions/TOOL-USE.md | 29.10.2026 | `zero=\d+` |
| C-0016 | INSTEAD OF-триггер по умолчанию выполняется как вызывающий пользователь, поэтому UPDATE через view без UPDATE на базовой таблице завершается отказом | observation | разбор схемы sample2 из lab/pilot/T-01 + документация Postgres | lab/failures/F-0011.md | 29.10.2026 |
| C-0017 | На схеме sample2 у app_rw ровно один рабочий обход: прямой вызов SECURITY DEFINER set_balance; UPDATE через accounts_v падает, если триггерная функция не SECURITY DEFINER | test | прогон на PostgreSQL 17.2, тесты T1–T10 в lab/pilot/out/T-01-L2.evidence.txt | lab/pilot/out/T-01-L2.evidence.txt | 29.10.2026 |

| C-0018 | Включение VPN не снимает 429 на free-модели: лимит привязан к учётке, а не к IP | observation | POST https://opencode.ai/zen/v1/chat/completions с VPN → 429 FreeUsageLimitError | вывод пробы, 29.10.2026 | 29.10.2026 |
| C-0019 | Из 44 507 вызовов инструментов 19 372 (43,5 %) начинаются с `cd` — служебный шум, а не работа | statistics | подсчёт префиксов команд по всем сессиям | вывод команды, 29.10.2026 | 19372 |
