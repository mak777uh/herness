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
| C-0010 | Free-модели opencode отдают отказ квоты: HTTP 429, тип FreeUsageLimitError | observation | `python bin/probe_api.py status --check` | вывод пробы, 29.10.2026 | 29.10.2026 | `429` |
| C-0011 | Каталог моделей opencode доступен без авторизации: 82 модели через /zen/v1/models | observation | `python bin/probe_api.py models --check` | вывод пробы, 29.10.2026 | 29.10.2026 | `models=82` |

Правило пополнения: новая строка — только вместе с командой, дайджестом артефакта и датой.
Опровергнутая строка не удаляется, а переводится в `docs/eliminations.md` со ссылкой.

| C-0012 | Запуск dsh headless из CLI без креденшелов падает MISSING_CREDENTIAL; DEEPSEEK_API_KEY из ~/.dsh/.credentials.yaml невалиден (HTTP 401) | observation | `python -c "import pathlib;logs=list(pathlib.Path('runs').glob('*/stderr.log'));hit=any('MISSING_CREDENTIAL' in f.read_text(errors='replace') for f in logs);print('MISSING_CREDENTIAL' if hit else 'not found');raise SystemExit(0 if hit else 1)"` | runs/*/stderr.log | 29.10.2026 (обновлено) | `MISSING_CREDENTIAL` |
| C-0013 | Ключи приложения не видны дочернему процессу: в окружении нет ни одного из DEEPSEEK/OPENAI/OPENCODE/ANTHROPIC | observation | `python bin/probe_api.py env --check` | вывод пробы, 29.10.2026 | 29.10.2026 | `visible_keys=0` |


| C-0014 | Выборка 30 сессий (20 % без инструментов, медиана 11 вызовов) заменена полным подсчётом — см. C-0015 | withdrawn | — | — | 29.10.2026 | |
| C-0015 | По всем 266 сессиям: 16,9 % без вызовов инструментов; медиана 40,5 вызова; p90 = 141; максимум 7026; 22,0 % всех вызовов — повтор той же команды в той же сессии | statistics | python bin/dist_stats.py | research/sessions/TOOL-USE.md | 29.10.2026 | `zero=\d+` |
| C-0016 | INSTEAD OF-триггер по умолчанию выполняется как вызывающий пользователь, поэтому UPDATE через view без UPDATE на базовой таблице завершается отказом | observation | разбор схемы sample2 из lab/pilot/T-01 + документация Postgres | lab/failures/F-0011.md | 29.10.2026 |
| C-0017 | На схеме sample2 у app_rw ровно один рабочий обход: прямой вызов SECURITY DEFINER set_balance; UPDATE через accounts_v падает, если триггерная функция не SECURITY DEFINER | test | прогон на PostgreSQL 17.2, тесты T1–T10 в lab/pilot/out/T-01-L2.evidence.txt | lab/pilot/out/T-01-L2.evidence.txt | 29.10.2026 |

| C-0018 | Отказ free-моделей не зависит от IP: с VPN ответ тот же 429 FreeUsageLimitError; 403 приходит только клиенту без User-Agent (артефакт Cloudflare, а не состояние провайдера) | observation | `python bin/probe_api.py status --check` | вывод пробы, 29.10.2026 | 29.10.2026 | `FreeUsageLimitError` |
| C-0019 | Из 44 507 вызовов инструментов 19 372 (43,5 %) начинаются с `cd` — служебный шум, а не работа; на 29.10.2026 пересчёт даёт 19 590 | statistics | `python bin/patterns.py --check` | вывод команды, 29.10.2026 | 29.10.2026 | `cd_start=` |
| C-0020 | В журналах 14 729 команд вызывают venv-python, 2164 задают PYTHONIOENCODING, 1048 — ErrorActionPreference: повторяющаяся преамбула; пересчёт 29.10.2026: 14 846 и 2 176 | statistics | `python bin/patterns.py --check` | вывод команды, 29.10.2026 | 29.10.2026 | `venv_python=` |
| C-0021 | В docs/PRINCIPLES.md 25 принципов портфеля | statistics | `python bin/count.py principles` | docs/PRINCIPLES.md | 29.10.2026 | `principles=25` |
| C-0022 | В кэше справочника 25 каталогов репозиториев с документами | statistics | `python bin/count.py repos` | refs-cache/ | 29.10.2026 | `repos=25` |
| C-0023 | Шаг не выполняется, если прогон уже превысил потолок шагов/времени/объёма: возврат 3 до запуска команды | test | `python tests/test_budget.py` | tests/test_budget.py | 29.10.2026 | `бюджет: 5/5 ok` |
| C-0024 | На 29.10.2026 ключ OPENCODE_GO_API_KEY валиден, но ни одна из 12 доступных моделей не отвечает: платные 402 (нет средств), free 429 (квота), beam-free 403 RegionError | observation | `python bin/probe_api.py map --check` | вывод карты моделей, 29.10.2026 | 29.10.2026 | `доступно моделей: 0 из 12` |
| C-0025 | Ключ OpenCode Go работает на эндпоинте https://opencode.ai/inference/go/openai/v1 (не на zen): deepseek-v4.1-flash отвечает 200, списание идёт с подписки (billing_source=go); требуется заголовок x-opencode-session, иначе 400 MissingSessionID | test | `python bin/live_probe.py go` | вывод пробы, 29.10.2026 | 29.10.2026 | `"code": 200` |

