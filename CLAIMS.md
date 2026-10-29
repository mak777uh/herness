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

| id | утверждение | тип | команда | артефакт | дата | ожидание |
| --- | --- | --- | --- | --- | --- | --- |
Колонка «ожидание» — регулярное выражение, которому обязан соответствовать вывод команды. Пустая ячейка значит «сверяется только код возврата».
|---|---|---|---|---|---|
| C-0001 | `dsh --version` на этой машине = `0.2.1-rc.3` | observation | `python bin/hs.py facts` | `runs/` | 29.10.2026 | `0\.2\.1-rc\.3` |
| C-0002 | DSH поднимается из изолированного DSH_HOME с профилем headless; неизменность установки этим не детектируется — нет проверки хешей или mtime | judgment | `python bin/check_artifacts.py C-0002` | docs/STATUS.md | 29.10.2026 | `M1` |
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


| C-0014 | Выборка 30 сессий (20 % без инструментов, медиана 11 вызовов) заменена полным подсчётом — см. C-0015 | withdrawn | — | — | 29.10.2026 |  |
| C-0015 | По всем 266 сессиям: 16,9 % без вызовов инструментов; медиана 40,5 вызова; p90 = 141; максимум 7026; 22,0 % всех вызовов — повтор той же команды в той же сессии | statistics | `python bin/check_artifacts.py C-0015` | research/snapshots/2026-10-29-stats.json | 29.10.2026 | `"sessions": 278` |
| C-0016 | INSTEAD OF-триггер по умолчанию выполняется как вызывающий пользователь, поэтому UPDATE через view без UPDATE на базовой таблице завершается отказом | observation | `python bin/check_artifacts.py C-0016` | lab/failures/F-0011.md, lab/pilot/out/T-01-L2.evidence.txt | 29.10.2026 | `permission denied` | отказ` |
| C-0017 | На схеме sample2 у app_rw ровно один рабочий обход: прямой вызов SECURITY DEFINER set_balance; UPDATE через accounts_v падает, если триггерная функция не SECURITY DEFINER. Версия сервера в транскрипте не зафиксирована, роль app_rw создаётся вне его | observation | `python bin/check_artifacts.py C-0017` | lab/pilot/out/T-01-L2.evidence.txt | 29.10.2026 | `SECURITY DEFINER` |

| C-0018 | Отказ free-моделей не зависит от IP: с VPN ответ тот же 429 FreeUsageLimitError; 403 приходит только клиенту без User-Agent (артефакт Cloudflare, а не состояние провайдера) | observation | `python bin/probe_api.py status --check` | вывод пробы, 29.10.2026 | 29.10.2026 | `FreeUsageLimitError` |
| C-0019 | Из 44 507 вызовов инструментов 19 372 (43,5 %) начинаются с `cd` — служебный шум, а не работа; на 29.10.2026 пересчёт даёт 19 590 | statistics | `python bin/check_artifacts.py C-0019` | research/snapshots/2026-10-29-stats.json | 29.10.2026 | `"cd_start": 20523` |
| C-0020 | В журналах 14 729 команд вызывают venv-python, 2164 задают PYTHONIOENCODING, 1048 — ErrorActionPreference: повторяющаяся преамбула; пересчёт 29.10.2026: 14 846 и 2 176 | statistics | `python bin/check_artifacts.py C-0020` | research/snapshots/2026-10-29-stats.json | 29.10.2026 | `"venv_python": 15302` |
| C-0021 | В docs/PRINCIPLES.md 25 принципов портфеля | statistics | `python bin/count.py principles` | docs/PRINCIPLES.md | 29.10.2026 | `principles=25` |
| C-0022 | В кэше справочника 25 каталогов репозиториев с документами | statistics | `python bin/count.py repos` | refs-cache/ | 29.10.2026 | `repos=25` |
| C-0023 | Шаг не выполняется, если прогон уже превысил потолок шагов/времени/объёма: возврат 3 объявлен в коде, тест проверяет только предикат превышения — поведение «до запуска» тестом не покрыто | observation | `python bin/check_artifacts.py C-0023` | tests/test_budget.py | 29.10.2026 | `бюджет:` |
| C-0024 | На 29.10.2026 ключ OPENCODE_GO_API_KEY валиден, но ни одна из 12 доступных моделей не отвечает: платные 402 (нет средств), free 429 (квота), beam-free 403 RegionError | observation | `python bin/probe_api.py map --check` | вывод карты моделей, 29.10.2026 | 29.10.2026 | `доступно моделей: 0 из 12` |
| C-0025 | Ключ OpenCode Go работает на эндпоинте https://opencode.ai/inference/go/openai/v1 (не на zen): deepseek-v4.1-flash отвечает 200, списание идёт с подписки (billing_source=go); требуется заголовок x-opencode-session, иначе 400 MissingSessionID | test | `python bin/live_probe.py go` | вывод пробы, 29.10.2026 | 29.10.2026 | `"code": 200` |

| C-0026 | Живой прогон нашим циклом на deepseek-v4.1-flash: 2 шага, один вызов shell, ответ «15 .py», совпал с фактическим числом файлов | test | `python bin/check_artifacts.py C-0026` | research/evidence/20261029T194617-live.json | 29.10.2026 | `events_sha256` |
| C-0027 | Выдуманный вызов возникал из-за промпта, который упоминал инструмент при выключенных инструментах; после разделения промптов модель честно отказывается: «нет инструментов, выдумывать не буду» | observation | `python bin/check_artifacts.py C-0027` | research/evidence/20261029T212902-live.json | 29.10.2026 | `events_sha256` |
| C-0028 | Модель без инструментов (deepseek-v4.1-flash, max_tokens 16000) нашла в docs/STATUS.md строку 7 — утверждение о готовности без владельца; после добавления ссылки на selftest и test_m1_journal на тот же запрос отвечает «нет» | test | `python bin/check_artifacts.py C-0028` | research/evidence/20261029T200945-live.json | 29.10.2026 | `events_sha256` |
| C-0029 | Рассуждение модели считается в max_tokens: при 4096 ответ пустой (всё уходит в reasoning), при 16000 — ответ есть | observation | `python bin/check_artifacts.py C-0029` | research/evidence/20261029T203812-live.json, research/evidence/20261029T204205-live.json | 29.10.2026 | `events_sha256` | пустой ответ модели` | completion_tokens` |
| C-0030 | glm-5.3-flash нестабилен: два прогона подряд оборвались (RemoteDisconnected), третий прошёл за 2,8 с — это нестабильность соединения, а не отказ модели | observation | `python bin/check_artifacts.py C-0030` | runs/glm-failure.log | 29.10.2026 | `done` |
| C-0031 | `hs live --auto` выбирает профиль по классу задачи из routes: «проверь README про число репозиториев» → T-0002 аудит, tools=true, 8 шагов, 8000 токенов | test | `python bin/live_cases.py` | bin/live_cases.py | 29.10.2026 | `class=T-0002` |
| C-0032 | С инструментом grep аудит STATUS.md занял 4 шага и дал проверяемый результат: ссылок C-XXXX в файле нет, строка 64 — утверждение без опоры (оба факта проверены отдельно) | test | `python bin/check_artifacts.py C-0032` | research/evidence/20261029T201912-live.json | 29.10.2026 | `events_sha256` |
| C-0033 | Живые прогоны по классам: T-0001 (4 шага, ответ 0 — верно), T-0003 (3 шага, файл создан), T-0004 (2 шага, 5/5), T-0005 (1 шаг, отказ без инструментов), T-0006 (3 шага после list_dir: 60 прогонов, 35 live), T-0007 (1 шаг, честное «нет данных») | test | `python bin/check_artifacts.py C-0033` | runs/step-measure.json | 29.10.2026 | `T-0006` |
| C-0034 | Необратимое действие отбивается харнессом до вызова модели: «опубликуй без подтверждения» → action=refuse, rc=3, прогон не создаётся | test | `python bin/live_cases.py` | bin/live_cases.py | 29.10.2026 | `decision=REFUSE` |
| C-0035 | Класс «уточнение» с краткой справкой о проекте отвечает верно: herness = her + harness (впрягать под конкретного человека) | test | `python bin/check_artifacts.py C-0035` | research/evidence/20261029T202926-live.json | 29.10.2026 | `events_sha256` |
| C-0036 | Замер шагов по классам: T-0001 4, T-0002 4, T-0003 3, T-0004 2, T-0006 4, T-0007 1; пороги в profiles.json = замер + 2 | statistics | `python bin/check_artifacts.py C-0036` | runs/step-measure.json | 29.10.2026 | `T-0001` |
| C-0037 | Если класс задачи не определён, харнесс не угадывает: возвращает action=ask, rc=4, модель не вызывается | test | `python bin/live_cases.py` | bin/live_cases.py | 29.10.2026 | `action=ask` |
| C-0038 | Повтор задач из архива: 8 из 8 отвечены после повтора с удвоенным лимитом; на T-01 модель повторила ошибку эталона (считает путь через view рабочим), хотя прогон на PostgreSQL 17.2 (C-0017) это опроверг | test | `python bin/check_artifacts.py C-0038` | research/evidence/20261029T204205-live.json | 29.10.2026 | `events_sha256` |
| C-0039 | Внешний аудит: три HIGH закрыты — контур CI, единственный владелец ожидания, сверка свидетельств вместо неисполняемых команд | test | `python bin/check_artifacts.py C-0039` | docs/AUDIT-2026-10-29.md | 29.10.2026 | `Что сделано` |
| C-0040 | Последняя доступная flash-модель у ключа — deepseek-v4.1-flash (created 2026-10-29); других flash-версий нет, модель закреплена гейтом `модели` | observation | `python bin/check_artifacts.py C-0040` | docs/MODELS.md | 29.10.2026 | `Закреплено` |
| C-0041 | Инструменты не отдают секреты: read_file и list_dir отказывают по deny-листу (`.secrets`, `.git`, `.ssh`, `*.pem`, `*.key`, `.env`) | test | `python tests/test_tools.py` | tests/test_tools.py | 29.10.2026 | `инструменты: 6/6 ok` |
| C-0042 | По переписи 19 репозиториев: цикл, инструменты и состояние универсальны; денежный бюджет и отчёт с границами — редкость; звёзды из ответов моделей расходятся с API до 15 раз | statistics | `python bin/check_artifacts.py C-0042` | research/HARNESS-CENSUS-2026-10-29.md | 29.10.2026 | `153 854` |
| C-0043 | Реестр 19 харнессов: звёзды/лицензии/даты проверены API, свойства помечены как непроверенные; 2 проекта давно не обновлялись (MetaGPT 21.01.2026, aider 22.05.2026) | statistics | `python bin/harness.py --stale` | harnesses.json | 29.10.2026 | `MetaGPT` |
| C-0044 | Справочник 11 проблем харнесса: у каждой 4–5 подходов; наши отличия (свидетельства, запрет секретов, журнал) — в редких клетках, дыры (изоляция, восстановление, параллельность) названы | statistics | `python bin/problems.py --brief` | problems.json | 29.10.2026 | `P11` |
| C-0045 | Разметка по путям: изоляция есть у 20 из 30, интерфейс у 23, параллельность у 19, плагины/навыки у 24 — это базовый уровень, а не редкость; не размечено только «ядро» | statistics | `python bin/matrix.py` | harnesses.json | 30.10.2026 | `236` |
| C-0046 | WSL: Ubuntu 24.04.5 LTS, WSL2, ядро 6.6.114.1, systemd работает, glibc 2.39, python 3.12.3, git 2.43; свободно на C: 13.3 ГБ — Lean 4 с mathlib не влезает | observation | `wsl -d Ubuntu-24.04 -- bash -lc "df -h /; python3 -V"` | docs/ADR-0030-wsl-os.md | 30.10.2026 | `glibc 2.39` |
| C-0047 | В nixpkgs есть пакет lean4 (файл pkgs/by-name/le/lean4/package.nix отдаётся, HTTP 200); наличие zstd/postgresql не проверено | observation | `python bin/hs.py py --code "..."` + raw.githubusercontent | docs/ADR-0031-os-choice.md | 30.10.2026 | `lean4/package.nix` |
| C-0048 | Четыре ответа сходятся: системный откат есть у NixOS, Guix, openSUSE, Silverblue; у Debian, Ubuntu, RHEL, Arch и Alpine — нет. Спорно: наличие lean4 в Guix/openSUSE/Silverblue | statistics | `python bin/oses.py --splits` | oses.json | 30.10.2026 | `unanimous` |
