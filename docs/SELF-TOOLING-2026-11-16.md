# SELF-TOOLING — след смены 16–17.11.2026

> **Обновление 17.11.2026, R8.** Получены и прочитаны по очереди пять сырых ответов R8
> (A–E), сохранены байт-в-байт с SHA-256; написан [`docs/R8-SYNTHESIS.md`](R8-SYNTHESIS.md).
> Ответы сходятся в Rust-каноне, WSL2+KVM, точных байтах admission, сыром потоковом чтении
> с жёстким потолком, наблюдении как измерении, производном `active`, заморозке legacy и
> запрете `K9_proven`; расходятся по runtime-валидатору, таблице S02, механизму наблюдения,
> топологии ключа, статусам legacy, объёму пилота, порядку отказов и новым кодам. Проверка
> по коду подтвердила расхождение policy (19 JSON против 14 Rust), статический обход
> write-scope через `..`, `O_TRUNC` без `NO_XDEV`, чтение файла целиком при обещанных
> 8 KiB, молчаливые пропуски в `search` и отсутствие admission в runtime. Код не менялся:
> Rust-срез `head`, admission/ключ/комната/promoter/реестр/генератор не начаты. R8 не даёт
> approval; решения Q11–Q18, F04 и A01 ждут владельца.

**Статус:** документ для следующего агента. Не отчёт о завершённой работе: часть проверок —
исторические снимки, часть — проектные решения, часть — открытые вопросы.
**Каноническая линия:** GitHub `main`; снимок предыдущей смены — коммит
[`ef3828871f1c25e093cce7b80ec22e0928a0660e`](https://github.com/mak777uh/herness/tree/ef3828871f1c25e093cce7b80ec22e0928a0660e)
(handoff; R5 — `c2fc552`, R4 — `4d1fae5`, evidence — `ded2cf2`, починенный checker — `ae926ef`,
сырые ответы R5 байт-в-байт — `9c8af80`, R6-бриф — `09a6acf`, сырые ответы R6 и синтез — `3d988f8`,
сырые ответы R7 и синтез — `c63f3b8`, бриф R8 и handoff — `e5182b7`, handoff R8 — `04e8b31`;
сырые ответы R8 и синтез — коммит после `04e8b31`).
**Предыдущая точка:** `b22eaec` (rolling-карта).
**Главные артефакты:** [`docs/DECISIONS-R5-2026-11-16.md`](DECISIONS-R5-2026-11-16.md) —
решения владельца Q1–Q10; [`docs/R8-SYNTHESIS.md`](R8-SYNTHESIS.md) — синтез пяти ответов R8,
проверенные факты и рекомендуемый порядок; [`docs/EXTERNAL-QUESTIONS-R8.md`](EXTERNAL-QUESTIONS-R8.md) —
открытые развилки; [`docs/R7-SYNTHESIS.md`](R7-SYNTHESIS.md) — синтез пяти ответов R7;
[`docs/R6-SYNTHESIS.md`](R6-SYNTHESIS.md) — синтез шести ответов R6;
[`docs/EXTERNAL-QUESTIONS-R7.md`](EXTERNAL-QUESTIONS-R7.md) — прошлый бриф;
[`docs/R5-SYNTHESIS.md`](R5-SYNTHESIS.md) — синтез двух ответов R5;
[`docs/research/external/`](research/external/README.md) — сырые ответы R5–R8;
[`docs/EXTERNAL-QUESTIONS-R6.md`](EXTERNAL-QUESTIONS-R6.md) — бриф R6;
[`docs/EXTERNAL-QUESTIONS-R5.md`](EXTERNAL-QUESTIONS-R5.md) — 24 вопроса
предыдущего круга; [`docs/EXTERNAL-QUESTIONS-R4.md`](EXTERNAL-QUESTIONS-R4.md) — 45 вопросов
круга до него.

---

## 1. Что сделано в этой смене

### 1.1. Перенесены в репозиторий три Evidence-документа

Коммит `ded2cf2`:

| файл | что внутри | размер |
|---|---|---|
| [`docs/CONSTITUTION-v0-2026-11-16.md`](CONSTITUTION-v0-2026-11-16.md) | K1–K11, юрисдикция, матрица шести инструментов, открытые вопросы | ~39.8 КБ |
| [`docs/TOOL-CARD-FIT-2026-11-16.md`](TOOL-CARD-FIT-2026-11-16.md) | бумажный замер шести инструментов на язык карточки | ~14.7 КБ |
| [`docs/WSL-SIM-2026-11-16.md`](WSL-SIM-2026-11-16.md) | симуляция комнаты и цепочки мостов в WSL | ~8.2 КБ |

Ссылки внутри конституции поправлены: `wsl-sim/` → `WSL-SIM-2026-11-16.md`;
`OPEN-QUESTIONS.md` → `EXTERNAL-QUESTIONS-R4.md`. Заголовок больше не говорит «репозиторий не
менялся»: документ теперь канонический.

### 1.2. Написан бриф R4

Коммит `4d1fae5`, файл [`docs/EXTERNAL-QUESTIONS-R4.md`](EXTERNAL-QUESTIONS-R4.md):

- 45 вопросов: 23 `P0`, 17 `P1`, 5 `P2`;
- блоки: `C` конституция и нормативный язык, `L` язык карточек и генератор, `G` доверие/допуск/
  композиция, `R` runtime/комната/WSL, `M` метрики/экономика/процесс, `P` восприятие пространства
  моделью;
- в каждом вопросе — контекст, что именно ответить, какой артефакт считать полезным;
- зафиксированы решения владельца D1–D12;
- перечислены принятые решения R2/R3 (C37–C44), которые нельзя переоткрывать без аргумента;
- есть ссылки на pinned-коммит и ответный шаблон.

### 1.3. Зафиксирована рабочая модель

В R4 и конституции:

- иерархия «владелец → территория → уровень «Я» → adjacent bridge → downstream bridge → карточка →
  policy → код» — **гипотеза**, не догма;
- три слоя, которые нельзя смешивать: нормативный (K1–K11), потолок возможностей комнаты, контракт
  инструмента;
- формула допустимости:
  `closure ⊆ ceiling ∧ behavior ⊆ contract ∧ contract ⊆ K1..K11 ∧ refusals явные ∧ provenance`;
- центральный разрыв: `behavior ⊆ contract` пока не определено. Карточка не выражает главное право
  5/6 инструментов; типизированных I/O 0/6.

### 1.4. Получены ответы R4; написан R5

Коммит `c2fc552`, файл [`docs/EXTERNAL-QUESTIONS-R5.md`](EXTERNAL-QUESTIONS-R5.md):

- 24 вопроса: 18 `P0`, 6 `P1`, 0 `P2`;
- R5 не повторяет R4, а закрывает развилки: `kind`, формальное ядро, уровень «Я», approval,
  generator → promotion, схемы, checker, K6/K9/K11, комната, метрики и план;
- в R5 §2 — сводка двух ответов R4: 15 согласованных пунктов и 10 расхождений;
- в R5 §3 — подтверждённые дефекты на `a4bcae5`: синтетическое чтение в `card_atoms.py`,
  односторонний `conflicts()`, TOCTOU чтения/поиска, чтение всего файла в `head`;
- полные тексты ответов R4 в репозиторий не добавлены: они большие и существуют у владельца.
  Каноническая сводка — R5 §2; если нужен полный текст, запросить у владельца, не додумывать.

R5 — следующий вход для внешних моделей. После ответов R5 принимаются решения, а не до них.

### 1.5. Получены ответы R5; написан синтез; починен checker

Ответы получены 16.11.2026: два независимых текста, A (18 550 Б, только четыре
фундаментальных вопроса) и B (97 483 Б, все 24 вопроса). Сырые тексты лежат в
[`docs/research/external/`](research/external/README.md) с SHA-256; это не решения
владельца и не approval.

Синтез — [`docs/R5-SYNTHESIS.md`](R5-SYNTHESIS.md):

- согласие: карточка не grant; пустой массив — не wildcard; deny сильнее allow;
  четырёхсторонняя монотонность; `openat2` от root FD; K6/K9/K11 в v0 не обеспечены;
  WSL — только разработка; генератор отделён от promotion;
- расхождения: набор `kind` (4 смысловых против 5 файловых), `search` в первом срезе,
  TCG как граница безопасности, строгость K6, коды отказа, `head`, promotion, метрики;
- рекомендации агента (не решения): B для v0 по `kind` и K6, `search` reject, TCG не
  называть границей, новые коды не добавлять без поправки словаря; 10 вопросов владельцу
  в §7.

Починен `bin/card_atoms.py` (C-0313):

- пустой `fs.read` больше не синтезирует право `read /mnt/**`;
- отсутствующие обязательные поля — `S1_SCHEMA`, а не пустой эффект;
- объявленные `write`/`net` дают положительные атомы; отсутствие эффекта — универсальный
  запрет `**`, а не «всё, кроме `/mnt/work`»;
- `conflicts()` двусторонний: allow против запрета карточки, deny против права карточки,
  лишний allow — скрытое разрешение;
- `--check` возвращает 3 при `uncovered`; `head` без правил политики теперь честно
  `uncovered`, а не «ok»;
- 31 проверка в `tests/test_card_atoms.py`, провалов 0; регрессия на `/mnt2` vs `/mnt`
  и на синтетический `netprobe` с пустым чтением.

Гейты после правки: `python bin/hs.py gates` → rc=0, 30 из 32, N/A 2 (журналы, индекс
прогонов). N/A не «зелёный». Coverage-артефакт пересобран: 306 утверждений, 306 закрытых,
strict 0.56.

### 1.6. Чего в этой смене не делали до решений Q1–Q10

- не начинали `bin/new_tool.py` и генератор;
- не делали `tool-card-v1` действующей схемой: это draft, нужен approval владельца;
- не добавляли коды `K4_*`, `K6_*`, `K11_*` до поправки словаря (после решения Q3 они
  добавлены, см. §1.7);
- не меняли Rust `read`/`search`/`head` на `openat2`: это следующий срез после решения
  по Q1–Q10;
- не трогали конституцию, policy, approval и pre-existing CRLF-файлы.

### 1.7. Решения Q1–Q10 приняты; реализованы как артефакты, не как генератор

Владелец 16.11.2026 ответил «давай все как рекомендуешь». Запись — в
[`docs/DECISIONS-R5-2026-11-16.md`](DECISIONS-R5-2026-11-16.md) и `docs/decision-log.md`.
Принято:

| id | что принято | артефакт |
|---|---|---|
| Q1 | пять файловых `kind`: `file_read`, `directory_read`, `file_write`, `digest`, `bridge_request` | [`lab/tools/tool-card-v1.schema.json`](../lab/tools/tool-card-v1.schema.json) |
| Q2 | `tool-card-v1` — draft, не подключён к `bin/tool_card.py` | пример [`head-v1.draft.json`](../lab/tools/drafts/head-v1.draft.json) |
| Q3 | словарь отказов v2: `K4_RESOURCE_LIMIT`, `K6_DATA_CLASS_UNKNOWN`, `K6_SECRET_EGRESS`, `K11_ADMISSION_REQUIRED` | [`lab/refusal-codes.json`](../lab/refusal-codes.json), `VERSION = 2`, 23 кода |
| Q4 | первый срез только на синтетическом `model_visible` fixture | [`lab/fixtures/model_visible/`](../lab/fixtures/model_visible/manifest.json) |
| Q5 | TCG — симуляция; security-утверждение требует аппаратной виртуализации | [`research/outputs/qemu-accel-2026-11-16.txt`](../research/outputs/qemu-accel-2026-11-16.txt) |
| Q6 | K6 v0 — fail-closed `public`/`model_visible`; `unknown`/`secret` — отказ | решения, §K6 |
| Q7 | генератор отделён от promoter; owner-подпись Ed25519 + host-side promoter | решения, §Q7; ключ ещё не создан |
| Q8 | `search` в первом срезе отвергнут | [`lab/prereg/HEAD-SLICE-R1.json`](../lab/prereg/HEAD-SLICE-R1.json) |
| Q9 | scorecard B — черновик пре-регистрации | [`docs/PILOT-SCORECARD-2026-11-16.md`](PILOT-SCORECARD-2026-11-16.md) |
| Q10 | сырые ответы A/B остаются в репозитории с SHA-256 | [`docs/research/external/`](research/external/README.md) |

Создан [`docs/EXTERNAL-QUESTIONS-R6.md`](EXTERNAL-QUESTIONS-R6.md): 22 оставшихся вопроса
(F01–F04, S01–S06, R01–R05, T01–T04, I01–I03), с принятыми решениями и измеренными фактами.
R6 — вход для внешней модели, неapproval; ответы не станут решением автоматически.

Что важно не спутать:

- схема проверена `jsonschema` Draft202012Validator (0 ошибок), но это проверка формы,
  а не semantic validator и не поведение Rust;
- фикстура синтетическая; её метка `model_visible` — не доказательство K6;
- QEMU-проба показывает доступность `whpx`/`tcg` и `microvm`, но не изоляцию;
- пре-регистрация `HEAD-SLICE-R1` запечатана и привязана к эксперименту E-0030 (status
  `planned`); прогона нет;
- генератор, admission, ключ, promotion и Rust-срез не начаты.

### 1.8. R6: шесть ответов, синтез и бриф R7

Получены шесть ответов на R6: A, B, C, D, E (`.txt`) и F (`.md`). Все сохранены
байт-в-байт в [`docs/research/external/`](research/external/README.md), размеры и SHA-256
сверены с исходниками и с blob'ами в git. `.gitattributes` запрещает нормализацию
переводов строк для этих файлов.

| ответ | что проверил | главная позиция |
|---|---|---|
| A | независимый разбор | Lean-ядро, Rust-валидатор, WSL2+KVM |
| B | код и JCS-векторы | Lean+Kani, Rust, WSL2+KVM; нашёл `max_processes` и `resource_of` |
| C | ссылки не открывал | Lean + Rust-дифференциал, WHPX |
| D | только P0 | малая Lean-модель, WHPX/KVM, честные границы |
| E | все F/S/R/T | Lean+proptest, 4 шаблона, seccomp-unotify; S02 читает 1 байт сверх бюджета |
| F | код | Lean-инфраструктура, Python-валидатор, WSL2+KVM; нашёл `NO_MAGICLINKS`/`NO_XDEV` |

Синтез — [`docs/R6-SYNTHESIS.md`](R6-SYNTHESIS.md). Он не является approval и не выбирает
за владельца. Согласие шести: Lean/LawRecord как направление, один semantic validator,
`openat2` от root FD, аппаратная виртуализация, JCS/Ed25519 admission, производный `active`,
генератор заблокирован до ручного среза. Расхождения: Rust против Python-валидатора,
точная таблица S02, KVM против WHPX и смысл `max_processes`, механизм наблюдения,
топология owner-ключа, объём генератора, порядок отказов S05, миграция реестра.

Проверено по коду, а не принято на слово:

- `tool_read_in` проверяет путь и затем читает файл целиком — TOCTOU и обход `max_bytes_read`;
- `write_beneath` ставит только `RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS`; `NO_MAGICLINKS`
  влечётся `NO_SYMLINKS` (openat2(2)), реальный пробел — `NO_XDEV`;
- `resource_of` подставляет `/mnt` для пути вне корня, но `resolve_in` сначала отвергает
  такой путь; это дефект, а не доказанный побег;
- `resolve_in` всегда проверяет `("read","read")`, даже когда вызван из `list`/`search`/`seal`;
- `seal`/`netprobe` запускают себя, что противоречит `process_spawn:false`;
- `head` не имеет policy-allow; `python bin/card_atoms.py --check lab/tools/cards/head.json`
  даёт `rc=3`, а `--check head` — `rc=2` «нет файла»; проверять нужно точный путь;
- реестр хранит `"status":"active"` у шести инструментов, включая отвергнутый `search`;
- enforcement admission в коде отсутствует; `run_tool_g` знает только granted-list;
- `tool_write_in` не вызывает `resolve_in`, а `write_beneath` использует `O_TRUNC`;
- `resource_matches` не понимает `!`; в Rust `POLICY` 14 правил против 19 в `policy.json`,
  пять `implied` deny не реализованы;
- `read` обещает в карточке 8192, а `MAX_READ` в коде — 24 KiB;
- `tool_search_in` молча пропускает нечитаемые/слишком большие файлы, считая их в `scanned`;
- seccomp в NET-less госте не ставится, `pre_exec` даёт `ENOSYS`.

Создан [`docs/EXTERNAL-QUESTIONS-R7.md`](EXTERNAL-QUESTIONS-R7.md): P0 — валидатор,
S02, комната/процессы, наблюдение, ключ, реестр, генератор; P1 — порядок отказов,
лестница статусов, привязка admission, аудит утверждений R6. Все ссылки прибиты к
снимку `3d988f8`. Ответы R7 не станут решением автоматически.

### 1.9. R7: пять ответов, синтез и бриф R8

Получены пять ответов на R7: A, B, C, E (`.txt`) и D (`.md`). Все сохранены
байт-в-байт в [`docs/research/external/`](research/external/README.md); размеры и
SHA-256 сверены с исходниками и с blob'ами в git. `.gitattributes` запрещает
нормализацию переводов строк для этих файлов.

| ответ | что проверил | главная позиция |
|---|---|---|
| A | снимок на GitHub, код | Rust-валидатор, WSL2+KVM, ptrace; сырой Ed25519, один ключ+backup; legacy в карантин; 2 шаблона/6 spec |
| B | код не открывал | Rust-валидатор, WSL2+KVM, отказ ядра+канарейки; `bytes_received`/`bytes_consumed`; recovery обновляет anchor; только карточка в пилоте |
| C | код не открывал | Rust-канон V01–V13 + векторы, runtime-revalidation; ptrace+seccomp TRACE; `output_cap`; 3 шаблона/12 spec |
| D | Arena Agent Mode, файлы снимка | Rust-валидатор, WSL2+KVM; Landlock audit (на 6.6 недоступен); recovery revoke/rotate; 3 шаблона/108 прогонов |
| E | снимок через raw, исполнял S02 | Rust-валидатор, WSL2+KVM, seccomp+ptrace; один operational+backup; native inventory; 2 шаблона/20 spec; нашёл policy drift 14 vs 19 |

Синтез — [`docs/R7-SYNTHESIS.md`](R7-SYNTHESIS.md). Он отделяет согласие от
развилок и фиксирует проверенные факты; approval не даёт. Согласие пяти: Rust-канон,
сырое потоковое чтение с жёстким потолком, WSL2+KVM без сети и host mounts,
наблюдение как измерение (не доказательство), owner-подпись admission, производный
`active`, точные байты манифеста, пилот только после ручного среза, запрет
`K9_proven`, один primary-отказ при вычислении всех нарушений.

Проверено по коду и первичным источникам, а не принято на слово:

- Rust `POLICY` — 14 правил, `policy.json` — 19; пять `implied` deny с `!` не
  реализованы, `resource_matches` не понимает `!`;
- `tool_write_in` не вызывает `resolve_in`; `write_beneath` использует `O_TRUNC` и
  не ставит `NO_XDEV`; `NO_MAGICLINKS` влечётся `NO_SYMLINKS` — прежняя запись R6
  исправлена;
- `read` обещает 8192, код даёт 24 KiB; `tool_search_in` молча пропускает файлы;
- `card_atoms` работает со старым форматом; полный путь даёт `rc=3`, имя без пути —
  `rc=2`;
- `run_tool_g` проверяет только granted-list; admission в runtime отсутствует;
- Landlock audit — ABI v7 / Linux 6.15, на ядре 6.6 недоступен; Landlock не
  ограничивает других писателей хоста (утверждение D о TOCTOU неверно);
- D содержит внутренние противоречия в `bytes_read`, глобальный `monotonic_counter`
  и указатель реестра внутри агентского дерева; они перечислены в синтезе, а не
  «усреднены».

Создан [`docs/EXTERNAL-QUESTIONS-R8.md`](EXTERNAL-QUESTIONS-R8.md): одиннадцать
вопросов (F01, S02, R01–R03, T01–T02, S05, F04, A01, AUDIT) с точными таблицами,
командами и evidence-полями. Все ссылки прибиты к `c63f3b8`; наши выводы в бриф не
входят. Ответы R8 не станут решением автоматически.

### 1.10. R8: пять ответов, синтез и проверка дефектов

Получены пять ответов на R8: A, B, C, E (`.txt`) и D (`.md`). Все сохранены
байт-в-байт в [`docs/research/external/`](research/external/README.md); размеры и
SHA-256 сверены с исходниками. `.gitattributes` запрещает нормализацию переводов
строк для этих файлов. Метки A–E — порядок вложений, а не самоидентификация моделей.

| ответ | что проверил | главная позиция |
|---|---|---|
| A | снимок `c63f3b8`, код и конфиг | Rust-валидатор у promoter + тонкий runtime; WSL2+KVM `microvm`; seccomp TRACE+ptrace; SSHSIG `herness-admission-v1`; legacy — `needs_revalidation`; пилот 20/20/20; policy codegen |
| B | репозиторий не открывал | Rust-валидатор дважды (accept + каждая загрузка); WSL2+KVM q35; ptrace; SSHSIG; `read`/`list` — `needs_revalidation`, `write`/`seal`/`netprobe` — карантин; пилот 12/16; S1 вторым |
| C | ссылки не открывал | Rust-crate у promoter и при каждой загрузке; WSL2+KVM q35, `microvm` отдельным профилем; отказ ядра + канарейки; сырой Ed25519 + `K_rev`; все шесть native — карантин; пилот 12/24 |
| D | снимок `c63f3b8` | полный семантический валидатор один раз у promoter, runtime — только digest; Windows QEMU `-accel whpx -M microvm` (выброс); seccomp+cgroup+канарейки; SSHSIG; все шесть native — карантин; пилот 2 шаблона |
| E | снимок `c63f3b8`, исполнял S02 | полный host-валидатор + тонкий runtime; WSL2+KVM `microvm`; seccomp TRACE+ptrace; сырой Ed25519 + узкое recovery; все шесть native — карантин; пилот 1 шаблон 20/24; вердикт `NOT READY` |

Синтез — [`docs/R8-SYNTHESIS.md`](R8-SYNTHESIS.md). Согласие: Rust-канон, WSL2+KVM
без сети и host mounts (D — единственный WHPX-выброс), сырое потоковое чтение с
жёстким потолком, точные байты admission, наблюдение как измерение, один owner-путь
допуска, производный `active`, заморозка legacy, `search` вне среза, две оси статусов,
JCS + detached-подпись, генератор только после зелёного ручного среза.

Развилки: полная runtime-перевалидация (B/C) против тонкого runtime (A/E) против
digest-only (D); определение `bytes_read` и доказательство EOF; `truncated`;
поведение строки 6; CR; переполнение вывода; имена новых кодов; WHPX против WSL2+KVM;
q35 против `microvm`; лимит процессов; TRACE+ptrace против канареек; SSHSIG против
сырого Ed25519; recovery; `needs_revalidation` против `quarantined`; пилот по
карточкам против пилота по коду; порядок отказов; обязательность runtime для
`admitted`; поля манифеста и исполнение на Windows.

Проверено по коду и первичным источникам, а не принято на слово:

- `lab/tools/policy.json` — 19 правил, `POLICY` в Rust — 14; шесть `implied`, четыре
  правила с `!`; пять именованных deny отсутствуют в Rust. Комментарий Rust о parity
  и гейте этой parity ложен;
- `tool_write_in` не вызывает `resolve_in`; `resource_of` не нормализует `..`, поэтому
  `/mnt/work/../work2/x` статически матчится с `file:/mnt/work/**`, а `openat2`
  разрешает путь в `/mnt/work2/x` (FACT-CODE, без прогона); `write_beneath` использует
  `O_TRUNC` и не ставит `RESOLVE_NO_XDEV`; `NO_MAGICLINKS` влечётся `NO_SYMLINKS`;
- `read` обещает 8 KiB, код читает файл целиком с потолком 24 KiB и проверяет потолок
  до добавления строки — одна строка может его превысить; `head` не имеет
  policy-allow;
- `search` считает `scanned` до цикла, молча пропускает ошибки и oversize-файлы,
  использует байтовый индекс `find` как индекс строки — возможна паника на Unicode;
- `list` делает `resolve_in` дважды, молча теряет ошибки `read_dir`/`metadata`;
- `seal` и `netprobe` перезапускают текущий exe; `run_tool_g` проверяет только
  granted-list, без admission/active/digest/room;
- реестр: шесть записей, все `active`, включая `search`; `net` есть в `KNOWN_TOOLS`,
  но отсутствует в реестре; это stored-статус, а не производный;
- фикстура: 471 Б, 10 строк, суммы 41/87/144/197/243/303/361/401/447/471;
- словарь отказов — v2, 23 кода; новых кодов R8 в нём нет.

Ошибки и противоречия ответов перечислены в §5 синтеза, а не «усреднены»: у D —
WHPX, строка 6 как `ok` вопреки пре-регистрации, срезание CR, `bytes_read` 49,
`S6` для не-regular файла, исполнение через Windows handle; у E — строка 6
`K4`+`truncated`, `K4` вместо `output_cap`; у C — невалидная строка 9, `fstat` как
доказательство EOF, сомнительный `syscall_nr` из wait-status; у B — `truncated=false`
в строках 1/4/9, логический префикс в `bytes_read`, q35; у A — S1 последним при
Q2 S1 до I/O, `K4` раньше ошибок объекта, осторожный `truncated` в строке 5.

---

## 2. Что именно показали замеры (и что они не доказывают)

### 2.1. Бумажный замер

- карточек 6, валидных 5;
- главное право сохранено **1/6** (только `read`);
- точное покрытие контракта **0/6**;
- глаголы **10/21 (47.6%)**;
- типизированные входы/выходы **0/6**;
- `netprobe` — исторический FAIL (2) из-за старой схемы: `read` был обязателен, сеть запрещена;
- порог `DESIGN-0002 §9` (≥4/6 уложились) **не пройден**.

Поправка: замер сделан **до** решения K3. После разрешения мостов `netprobe` надо перемерить;
цифры 5/6 и 0/6 не переписаны, это исторический снимок.

**Не доказывает:** что генератор невозможен. Доказывает, что текущий язык карточки слишком узок и
что `kind`/типы/оракул — не косметика.

### 2.2. WSL-симуляция

- **30 PASS, 0 FAIL, 2 CONTROL, 5 N/A**;
- CONTROL — ожидаемо небезопасный прямой доступ к фиктивному секрету/ключу; он показывает, что
  нефильтрованный путь нарушает K6;
- N/A: K8, K9-код, K11-намерение, «хост не заблокирован», реальные секреты;
- WSL — **не граница безопасности**: root, `/etc/ld.so.cache`, IPC видны; K6 распознаёт только
  фиктивные маркеры; K9 проверяет только политику, не код; лимиты моста не enforced.

**Не доказывает:** что ноутбук защищён. Доказывает, что политику и негативные контроли можно
прогонять в изоляции, не трогая чужой проект в WSL.

### 2.3. Что осталось красным

| # | хвост | где | статус |
|---|---|---|---|
| 1 | K6 не обеспечен: `read`/`head`/`search` могут вынести секрет | конституция, WSL CONTROL | открыт, P0 |
| 2 | K7 не проверяется | конституция | открыт, P1 |
| 3 | K9 не обеспечен: policy-only, код не инспектируется | конституция, WSL N/A | открыт, P0 |
| 4 | K11 не обеспечен: хеш ≠ намерение | конституция, WSL N/A | открыт, P0 |
| 5 | типизированные I/O 0/6 | TOOL-CARD-FIT | открыт, P0 |
| 6 | `kind` не закрыт формально | TOOL-CARD-FIT, DESIGN-0002 | открыт, P0 |
| 7 | `new_tool.py` не написан | DESIGN-0002 | Q1–Q10 приняты; старт после зелёного Rust-среза |
| 8 | `bin/tool_examples.py` упомянут в лестнице, но отсутствует в коммите | DESIGN-0002 | хвост |
| 9 | `tool_card.py --render` не показывает `closure.net` | R3 C44 | хвост |
| 10 | `netprobe` требует повторного замера после K3 | TOOL-CARD-FIT | хвост |
| 11 | второй клон и локальный `nomos` не каноничны | `C:\111\herness`, `parts/nomos` | решение владельца |
| 12 | CRLF-шум в working tree | git status | не коммитить `git add -A` |
| 13 | `card_atoms` синтезировал чтение и проверял конфликт в одну сторону | R5 §3, C-0313 | **закрыт** 16.11.2026, 31 проверка |
| 14 | `read`/`search` TOCTOU и `head` читает файл целиком | R5 §3, `loopmod.rs` | открыт, следующий срез |
| 15 | Q1–Q10 не были зафиксированы | R5 §7 | **закрыт** 16.11.2026, решения и словарь v2 |
| 16 | `tool-card-v1` не имеет semantic validator | Q2, S01 R6 | открыт; схема — draft, не закон |
| 17 | QEMU-комната не построена; замер — только доступность | Q5, R01 R6 | открыт; TCG не граница |

---

## 3. Где именно остановились

Ответы R8 прочитаны, сырые тексты и синтез лежат в репозитории; Q1–Q10 не
переоткрывались. Код не менялся: `read` по-прежнему делает `resolve_in` + чтение
файла целиком с потолком 24 KiB, `write_beneath` без `NO_XDEV` (но с `NO_SYMLINKS`,
который влечёт `NO_MAGICLINKS`), `head` не имеет policy-allow, реестр хранит
`active`, enforcement admission отсутствует. Rust-срез `head`, комната, ключ,
promoter, миграция реестра и генератор не начаты.

Порядок, который рекомендуется синтезом R8 (решение — за владельцем):

1. Владелец читает [`docs/R8-SYNTHESIS.md`](R8-SYNTHESIS.md) и решает Q11–Q18,
   F04 и A01. Ответы R8 — рекомендации; перед принятием утверждения проверяются
   по коду, а расхождения — failing-репро.
2. До решений не писать `head`, admission, комнату, promoter, миграцию и генератор;
   не менять policy/registry/схему/конституцию. Допустимая работа — сохранение
   материалов, failing-репро тесты и документы.
3. Сначала — дешёвые обратимые починки с воспроизводимыми репро: parity policy
   JSON↔Rust, нормализация write-scope, `NO_XDEV`, потолок `read`/`head`, молчаливые
   пропуски `search`/`list`, ложный `active` в реестре. Каждая — отдельным коммитом
   с тестом, без ослабления гейта.
4. Затем — измеренная комната: один `-accel kvm`, без fallback, `KVM_RUN` как
   событие; QEMU-проба 16.11 показывает только доступность ускорителей, не изоляцию.
5. После решений по валидатору (Q11 → F01), комнате (Q13 → R01) и семантике S02
   (Q12 → S02) — Rust-срез `file_read_stream` и прогон `HEAD-SLICE-R1` по
   запечатанному порогу. При провале сохранить FAIL, не ослаблять критерий.
6. После решений по ключу (Q15 → R03) и admission (A01) — promoter с проверкой
   допуска, но без права голоса генератора; затем миграция реестра (Q18 → T01),
   чтобы `active` стал производным, а `search` — не допущенным.
7. Только после зелёного ручного среза и замороженных порогов (Q16 → T02) — пилот
   генератора. `K9_proven` не выдавать ни на одной ступени.

Если ответы владельца, R7 или R8 противоречат друг другу — не выбирать «среднее». Нужен
эксперимент, который различит варианты, или явное решение владельца.

---

## 4. Что проверить перед продолжением

### 4.1. Git

```bash
cd /c/Users/Admin/Documents/Qoder/2026-11-16/7e4ba6fe/herness
git rev-parse HEAD
git ls-remote --heads origin main
git status --short
```

Ожидание: HEAD и `origin/main` — `04e8b31` или следующий docs-коммит после него
(R8 evidence — коммит с сырыми ответами и синтезом; R7 evidence — `c63f3b8`,
R8-бриф — `e5182b7`); R6-бриф — `09a6acf`, R5 — `c2fc552`, R4 — `4d1fae5`; синтез и
сырые ответы — в коммитах после `b22eaec`. В status только pre-existing CRLF-модификации,
которых мы не трогали. **Не делать `git add -A`.** Добавлять только конкретные новые файлы.

### 4.2. Документы

```bash
wc -c docs/CONSTITUTION-v0-2026-11-16.md \
      docs/TOOL-CARD-FIT-2026-11-16.md \
      docs/WSL-SIM-2026-11-16.md \
      docs/EXTERNAL-QUESTIONS-R4.md \
      docs/EXTERNAL-QUESTIONS-R5.md \
      docs/R5-SYNTHESIS.md \
      docs/DECISIONS-R5-2026-11-16.md \
      docs/EXTERNAL-QUESTIONS-R6.md \
      docs/R6-SYNTHESIS.md \
      docs/EXTERNAL-QUESTIONS-R7.md \
      docs/R7-SYNTHESIS.md \
      docs/EXTERNAL-QUESTIONS-R8.md \
      docs/R8-SYNTHESIS.md \
      docs/research/external/2026-11-16-R5-answer-A.md \
      docs/research/external/2026-11-16-R5-answer-B.md \
      docs/research/external/2026-11-17-R8-answer-A.txt \
      docs/research/external/2026-11-17-R8-answer-B.txt \
      docs/research/external/2026-11-17-R8-answer-C.txt \
      docs/research/external/2026-11-17-R8-answer-D.md \
      docs/research/external/2026-11-17-R8-answer-E.txt
grep -c '^#### [CLGRMP][0-9][0-9]' docs/EXTERNAL-QUESTIONS-R4.md
grep -c '^#### [DSCTGRE][0-9][0-9]' docs/EXTERNAL-QUESTIONS-R5.md
grep -c '^#### [FSRTI][0-9][0-9]' docs/EXTERNAL-QUESTIONS-R6.md
grep -c '^### R7-' docs/EXTERNAL-QUESTIONS-R7.md
grep -c '^### R8-Q' docs/EXTERNAL-QUESTIONS-R8.md
sha256sum docs/research/external/2026-11-16-R5-answer-*.md
sha256sum docs/research/external/2026-11-17-R6-answer-*
sha256sum docs/research/external/2026-11-17-R7-answer-*
sha256sum docs/research/external/2026-11-17-R8-answer-*
```

Ожидание: R4 — 45 вопросов, R5 — 24 вопроса, R6 — 22 вопроса, R7 — 11 вопросов (7 P0,
4 P1), R8 — 11 вопросов (F01, S02, R01–R03, T01–T02, S05, F04, A01, AUDIT); синтез R7 —
59 123 Б, бриф R8 — 63 890 Б, синтез R8 — 78 960 Б; сырые ответы R5 — 18 550 и 97 483 Б;
R6 — 45 918, 68 106, 49 539, 52 252, 123 014, 81 488 Б; R7 — 68 505, 47 167, 85 057,
80 488, 71 976 Б; R8 — 65 172, 62 585, 54 519, 70 034, 72 409 Б; их SHA-256 совпадают с
[`docs/research/external/README.md`](research/external/README.md).

### 4.3. Ссылки

Проверить, что pinned-ссылки в R4, R5, R6, R7 и R8 открываются:
`https://github.com/mak777uh/herness/blob/4d1fae5.../docs/...`,
`https://github.com/mak777uh/herness/blob/c2fc552.../docs/...`,
`https://github.com/mak777uh/herness/blob/c63f3b8.../docs/...`,
`https://github.com/mak777uh/herness/blob/004249a.../docs/...`,
`https://github.com/mak777uh/herness/blob/3d988f8.../docs/...`.
Если GitHub отдаёт 404 — проверить, что коммит запушен, а не только локальный.

### 4.4. Чего не делать

- не трогать чужие файлы в WSL и глобальные настройки;
- не менять сеть/firewall хоста;
- не коммитить секреты, ключи, токены, пароли;
- не ослаблять гейт, чтобы «стало зелёным»;
- не выдавать WSL-симуляцию за границу безопасности;
- не выдавать Lean-модель за Rust-реализацию;
- не публиковать ничего наружу без явного «да» владельца;
- не запускать `new_tool.py` до зелёного `HEAD-SLICE-R1` и semantic validator; Q1–Q10 уже
  приняты, но это не делает схему законом и не запускает генератор;
- не начинать реализацию `head`/admission/комнаты/реестра до решений Q11–Q18: синтез R8 —
  вход для разбора, а не разрешение.

---

## 5. Открытые решения, которые нужны от владельца

Q1–Q10 приняты и не переоткрываются без аргумента. Оставшиеся развилки вынесены в R8; таблица
ниже показывает, что именно ещё не решено. Ответы R8 — вход, а не решение.

| id | решение | почему сейчас | где R8 |
|---|---|---|---|
| Q11 | Канонический validator: Rust или Python с receipt; runtime-роль | без одной семантики promoter не знает, чему доверять | R8-Q1 (F01) |
| Q12 | Точная таблица `file_read_stream` (EOF, счётчики, CRLF, частичная строка, `truncated`, UTF-8, `output_cap`) | от неё зависит Rust-срез и негативные контроли | R8-Q2 (S02) |
| Q13 | Комната: WSL2+KVM или WHPX; seccomp и модель процессов; подача fixture | без измеренной комнаты нет security-run | R8-Q3 (R01) |
| Q14 | Механизм наблюдения и граница `observed_*` | без него evidence — self-report | R8-Q4 (R02) |
| Q15 | Топология owner-ключа, recovery и trust anchor | admission без ключа невозможен | R8-Q5 (R03) |
| Q16 | Объём и пороги пилота генератора | иначе успех не отличить от самообмана | R8-Q7 (T02) |
| Q17 | Порядок вычисления и выдачи отказов; новые коды | комбинированные нарушения сейчас недетерминированы | R8-Q8 (S05) |
| Q18 | Миграция stored `active`, legacy-шесть и `search` | текущий registry утверждает ложное | R8-Q6 (T01) |

Дополнительно, без отдельного Q: лестница статусов (R8-Q9, F04), привязка admission к
байтам (R8-Q10, A01) и аудит дефектов/порядок починки (R8-Q11, AUDIT).

R4 закрыл направления, R5 дал варианты, Q1–Q10 зафиксировали решения владельца, R6 дал
шесть независимых архитектур, R7 сузил их до пяти, R8 проверил пять против кода и свёл
расхождения в таблицы. Рекомендация синтеза по каждому пункту — в §6
[`docs/R8-SYNTHESIS.md`](R8-SYNTHESIS.md); это не решение. Окончательное решение — за
владельцем, не за агентом и не за внешней моделью.

---

## 6. Полезные ссылки

- [Конституция v0](CONSTITUTION-v0-2026-11-16.md)
- [Синтез R8](R8-SYNTHESIS.md)
- [Бриф R8](EXTERNAL-QUESTIONS-R8.md)
- [Синтез R7](R7-SYNTHESIS.md)
- [Синтез R6](R6-SYNTHESIS.md)
- [Бриф R7](EXTERNAL-QUESTIONS-R7.md)
- [Синтез R5](R5-SYNTHESIS.md)
- [Решения Q1–Q10](DECISIONS-R5-2026-11-16.md)
- [Scorecard](PILOT-SCORECARD-2026-11-16.md)
- [Сырые ответы R5–R8](research/external/README.md)
- [Бумажный замер](TOOL-CARD-FIT-2026-11-16.md)
- [WSL-симуляция](WSL-SIM-2026-11-16.md)
- [Бриф R4](EXTERNAL-QUESTIONS-R4.md)
- [Бриф R5](EXTERNAL-QUESTIONS-R5.md)
- [Бриф R6](EXTERNAL-QUESTIONS-R6.md)
- [Бриф R7](EXTERNAL-QUESTIONS-R7.md)
- [tool-card-v1 (draft)](../lab/tools/tool-card-v1.schema.json)
- [head-v1.draft.json](../lab/tools/drafts/head-v1.draft.json)
- [Словарь отказов v2](../lab/refusal-codes.json)
- [Fixture](../lab/fixtures/model_visible/manifest.json)
- [Пре-регистрация HEAD-SLICE-R1](../lab/prereg/HEAD-SLICE-R1.json)
- [Замер QEMU](../research/outputs/qemu-accel-2026-11-16.txt)
- [DESIGN-0002](DESIGN-0002-tool-generation.md)
- [PROPOSAL-0001](PROPOSAL-0001-task-written-bridges.md)
- [RESEARCH NOTE R1–R3](../research/RESEARCH-NOTE.md)
- [R2 brief](EXTERNAL-QUESTIONS-R2.md)
- [R3 brief](EXTERNAL-QUESTIONS-R3.md)
- [Карточка `head`](../lab/tools/cards/head.json)
- [Контракты](../lab/tools/contracts.json)
- [Политика](../lab/tools/policy.json)
- [Реестр](../lab/tools/registry.jsonl)
- [bridge_parts.py](../bin/bridge_parts.py)

---

## 7. Что этот документ не доказывает

- Что R4/R5/R6/R7/R8-вопросы правильные и полные.
- Что ответы моделей A–F верны или совместимы с конституцией; ошибки R8 перечислены в
  [`docs/R8-SYNTHESIS.md`](R8-SYNTHESIS.md) §5 и не «усреднены».
- Что ответы R6/R7/R8 станут решением автоматически: их разбирает владелец; синтез —
  карта расхождений, не approval.
- Что `tool-card-v1` проверяет поведение: это форма, semantic validator ещё нет.
- Что синтетическая фикстура доказывает K6.
- Что QEMU-проба доказывает изоляцию: она показывает только доступность ускорителей.
- Что Landlock audit или ptrace дают полноту наблюдения; это ограниченное свидетельство.
- Что конституция K1–K11 достаточно полна.
- Что WSL-симуляция что-то доказывает про ноутбук.
- Что генератор можно писать прямо сейчас.

Это карта смены: что сделано, где остановились, что проверить. Следующий агент обязан
самостоятельно перепроверить предпосылки, а не доверять этому тексту на слово.
