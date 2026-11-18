# SELF-TOOLING — след смены 16–18.11.2026

> **Обновление 18.11.2026, два разрыва допуска закрыты (без активации).** Promoter
> теперь принимает `--job` только как данные и связывает его с уже проверенным admission:
> `root`, fixture-манифест, шесть digest-путей, manifest/sig/anchor и расположение
> fixture-каталога; per-case override запрещён, несовпадение — отказ до store/launch.
> Job передаётся хосту точными байтами через запечатанный memfd и унаследованный
> `--job-fd`, а не путём. Runtime `head` сверяет не только размер, но и **sha256
> содержимого** фикстуры; `MAX_HASH_BYTES = 8 MiB` даёт `K4` вместо неограниченного
> чтения, хешируются ровно те байты, которые затем выдаются. Проверки: Rust lib —
> **133 passed** (2 новых: same-size/different-bytes → `K11`, файл выше предела → `K4`);
> promoter self-test — **18/18 Windows**, **21/21 WSL**; активационная репетиция —
> **34/34 WSL**, **22/22 Windows**; owner-церемония — **57/57 WSL**, **45/45 Windows**;
> HEAD-SLICE host+QEMU — **PASS**. Evidence:
> [`PROMOTER-JOB-BINDING-R1-2026-11-18.txt`](../research/outputs/PROMOTER-JOB-BINDING-R1-2026-11-18.txt),
> [`HEAD-EDGE-R1-2026-11-17.txt`](../research/outputs/HEAD-EDGE-R1-2026-11-17.txt),
> [`ACTIVATION-REHEARSAL-R1-2026-11-17.txt`](../research/outputs/ACTIVATION-REHEARSAL-R1-2026-11-17.txt),
> [`OWNER-CEREMONY-DRY-RUN-R1-2026-11-17.txt`](../research/outputs/OWNER-CEREMONY-DRY-RUN-R1-2026-11-17.txt),
> [`HEAD-SLICE-R1-2026-11-18.txt`](../research/outputs/HEAD-SLICE-R1-2026-11-18.txt), C-0322/C-0323.
> Файл `HEAD-SLICE-R1-2026-11-17.txt` оставлен неизменным: его digest заморожен в
> `PILOT-GENERATOR-R1`; повтор после добавления sha256 — отдельный файл `...-18.txt`.
> Production `head` остаётся `candidate`, `active` пуст; настоящий owner-ключ не создавался,
> admission не подписан, `K9_proven` не выдан, наружу ничего не публиковалось.
> Оставшиеся границы: реестр не проверяет подпись и не имеет allowlist owner-anchor;
> `run_tool_g` не имеет ветки `head`; promoter не реализует полную семантику карточки.
>
> **Обновление 17.11.2026, R8 реализован.** Владелец делегировал выбор рекомендаций R8
> («делай сам все поочерёдно»); решения Q11–Q18, F04 и A01 записаны агентом в
> [`docs/DECISIONS-R8-2026-11-17.md`](DECISIONS-R8-2026-11-17.md) с явной пометкой, что
> это не approval внешних моделей и не изменение конституции. Пройдены этапы 0–11 плана:
> policy — один источник с `!`, сегментами и parity-гейтом; write — create-new через
> `O_EXCL` и `NO_XDEV`; legacy `read`/`search`/`list` починены; KVM_RUN измерен в WSL2
> (`-M microvm -accel kvm`, QMP, tracepoint `kvm:kvm_entry`, отрицательный контроль без
> `/dev/kvm`); admission/promoter v0 на эфемерных test-only ключах; `file_read_stream` и
> HEAD-SLICE-R1 — **PASS** (8/8 критических контролей, host + QEMU/KVM); реестр — genesis
> events и производный `active` (шесть legacy `quarantined`, `search` rejected, `active`
> пуст); пилот PILOT-GENERATOR-R1 — **PASS** (20/20 спецификаций, 16/16 критических и 8/8
> функциональных мутантов, 3/3 детерминированных повтора); этап 11 — test-only
> активационная репетиция **33/33 PASS** (guard явного `test_only:false`, песочный
> `admitted_inactive`, promoter verify/store и launch через memfd/execveat в WSL);
> CI job `admission` — **31/31** без `--build` (бинарь собирается отдельным шагом),
> CI `44159576484` — success. После красного `44155903515` исправлено только
> представление: проба гейта теперь откатывает байты, карточка head запиннена CRLF
> (`700d516`); запечатанные digest'ы и пороги не менялись. Проверенный handoff-коммит —
> `d0fb60d`, CI `44165290004` — success; docs-правки после него не меняют код.
> Этап 12 — сухая owner-церемония в песочнице (`fe143b6`): эфемерный ключ с anchor
> `test_only:false`, **30/30 PASS** в WSL (28/28 в CI без `--build`, 19/19 на Windows без
> launch), promoter без `--allow-test-only`, песочный `active=[head]`; production `head`
> остаётся `candidate`, production `active` пуст. CI `44163715508` — success, все 6 job'ов.
> Это проверка положительной ветки, **не** owner approval: настоящий ключ не создавался.
> `head` остаётся candidate: настоящий owner-ключ не создан, admission не выдан, ни один
> инструмент не `active`, `K9_proven` нет. Следующий шаг — владелец читает evidence и
> [`docs/OWNER-RUNBOOK-2026-11-17.md`](OWNER-RUNBOOK-2026-11-17.md) и, если согласен,
> проводит церемонию ключа и подписывает admission; только после этого возможна активация.
> Детали — §1.11, §1.12 и [`docs/WHERE-I-STOPPED.md`](WHERE-I-STOPPED.md).

**Статус:** документ для следующего агента. Не отчёт о завершённой работе: часть проверок —
исторические снимки, часть — проектные решения, часть — открытые вопросы.
**Каноническая линия:** GitHub `main`; снимок предыдущей смены — коммит
[`ef3828871f1c25e093cce7b80ec22e0928a0660e`](https://github.com/mak777uh/herness/tree/ef3828871f1c25e093cce7b80ec22e0928a0660e)
(handoff; R5 — `c2fc552`, R4 — `4d1fae5`, evidence — `ded2cf2`, починенный checker — `ae926ef`,
сырые ответы R5 байт-в-байт — `9c8af80`, R6-бриф — `09a6acf`, сырые ответы R6 и синтез — `3d988f8`,
сырые ответы R7 и синтез — `c63f3b8`, бриф R8 и handoff — `e5182b7`, handoff R8 — `04e8b31`,
сырые ответы R8 и синтез — `384d804`; R8 реализован этапами 0–11: `e82dc22` (решения и
словарь v3), `d95c533` (policy и репро), `96470e9` (write), `318eb9e` (legacy), `729fee8`
(KVM_RUN), `f790ef5` (admission/promoter), `8d1f542` (head slice), `a6e7292` (реестр),
`92963cf` (пилот генератора), `a95fe58` (guard `test_only:false`), `c063ded` (test-only
репетиция), `8c30f27` (CI-гейты), `700d516` (байтовый откат проб и CRLF-пин карточки),
`fe143b6` (сухая owner-церемония в песочнице); CI `44159576484` — success).
**Предыдущая точка:** `b22eaec` (rolling-карта).
**Главные артефакты:** [`docs/DECISIONS-R5-2026-11-16.md`](DECISIONS-R5-2026-11-16.md) —
решения владельца Q1–Q10; [`docs/DECISIONS-R8-2026-11-17.md`](DECISIONS-R8-2026-11-17.md) —
решения Q11–Q18/F04/A01, выбранные агентом по делегированию; [`docs/R8-SYNTHESIS.md`](R8-SYNTHESIS.md) — синтез пяти ответов R8,
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

### 1.11. R8 реализован: этапы 0–9 и что именно измерено

План исполнения — `C:\Users\Admin\.qoder\plans\coastal-stone-osprey.md` (вне репозитория);
решения и границы — [`docs/DECISIONS-R8-2026-11-17.md`](DECISIONS-R8-2026-11-17.md).
Каждый этап — отдельный коммит с тестом; гейты не ослаблялись, N/A не выдавался за зелёный.

| этап | коммит | что сделано | evidence |
|---|---|---|---|
| 0 | `e82dc22` | решения R8, S02, словарь отказов v3 (28 кодов), карточки | `lab/refusal-codes.json`, `docs/DECISIONS-R8-2026-11-17.md` |
| 1 | `d95c533` | красные репро до патчей (policy 19/14, `!`, write `..`, `O_TRUNC`, read, search, list, admission) | `research/outputs/REPRO-R8-2026-11-17.txt` |
| 2 | `d95c533` | policy — один источник; matcher с `!`, сегментами, deny-wins; parity-гейт | `bin/check_policy_parity.py`, `lab/tools/policy.json` |
| 3 | `96470e9` | write create-new: `O_EXCL`, `NO_XDEV`, `..` не выходит из work; `S14_ALREADY_EXISTS` | `core-rs/src/loopmod.rs`, Rust-тесты |
| 4 | `318eb9e` | legacy read/search/list, единая точка derived authority | `core-rs/src/loopmod.rs` |
| 5 | `729fee8` | KVM_RUN: `-M microvm -accel kvm`, QMP, tracepoint, отрицательный контроль | `research/kvm/KVM-RUN-2026-11-17.txt` |
| 6 | `f790ef5` | admission v0 (JCS, Ed25519 verify, epoch/revoke), promoter (digest'ы, exact bytes, memfd на Linux) | `bin/admission.py`, `bin/promoter.py` |
| 7 | `8d1f542` | `file_read_stream`, HEAD-SLICE-R1 — PASS | `research/outputs/HEAD-SLICE-R1-2026-11-17.txt` |
| 8 | `a6e7292` | реестр: genesis events, JCS/prev/seq, производный `active`; legacy quarantined, search rejected | `lab/tools/registry.events.jsonl`, `registry.state.json` |
| 9 | `92963cf` | генератор одного шаблона и пилот: 20 спецификаций, 24 мутанта, 3 повтора — PASS | `lab/pilot/`, `lab/candidates/`, `research/outputs/PILOT-GENERATOR-R1-2026-11-17.txt` |
| 10 | `fe27d07`, `edbf085` | handoff, claims, push; после первого LF-CI — CRLF-пиннинг запечатанных digest | `docs/`, `CLAIMS.md`, `.gitattributes` |
| 11 | `a95fe58`, `c063ded`, `8c30f27`, `700d516` | test-only репетиция: guard `test_only:false`, песочный реестр, promoter verify/store и launch в WSL; 33/33 PASS на тот момент (CI 31/31 без сборки; после job-проверки — 34/34, этап 13); байтовый откат проб и CRLF-пин карточки; CI `44159576484` — success | `bin/activation_rehearsal.py`, `research/outputs/ACTIVATION-REHEARSAL-R1-2026-11-17.txt`, C-0317 |
| 12 | `fe143b6` | сухая owner-церемония: эфемерный ключ с anchor `test_only:false`, promoter без `--allow-test-only`, песочный `active=[head]`; production не изменён; 30/30 WSL, 28/28 CI без `--build`, 19/19 Windows без launch (после негативных контролей — 56/56 WSL на тот момент, 45/45 Windows; сейчас 57/57 WSL после job-проверки, §1.15); CI `44163715508` — success | `bin/owner_ceremony_dry_run.py`, `research/outputs/OWNER-CEREMONY-DRY-RUN-R1-2026-11-17.txt` |
| 13 | `a999037` | promoter связывает `--job` root/fixture/checks/admission и запрещает per-case override; job идёт в launch запечатанным memfd через `--job-fd`; runtime `head` сверяет sha256 содержимого с пределом `MAX_HASH_BYTES`; 133 Rust-теста, 34/34 WSL, 22/22 Windows, HEAD-SLICE host+QEMU PASS | `bin/promoter.py`, `core-rs/src/head.rs`, `core-rs/src/bin/head_slice_host.rs`, `research/outputs/PROMOTER-JOB-BINDING-R1-2026-11-18.txt`, `research/outputs/HEAD-SLICE-R1-2026-11-18.txt`, C-0322/C-0323 |

CI на чистом LF checkout поймал то, чего CRLF-дерево не показывало: `lawset_digest`
в provenance карточки head и 20 карточек кандидатов, а также SHA-256
`HEAD-SLICE-R1` prereg, замороженный в `PILOT-GENERATOR-R1`, были измерены на
CRLF-байтах. `edbf085` пиннит эти два запечатанных входа через `eol=crlf`;
карточки, evidence и пороги не менялись. CI `44149087189` — success.

Первый прогон этапа 11 (`44155903515`) показал ещё два места, которые не были
представлением на бумаге, а становились им во время прогона: проба гейта
«пре-регистрация» откатывала in-place правки через `read_text/write_text` и тем
самым нормализовала CRLF→LF у `HEAD-SLICE-R1.json`, а карточка head не имела
CRLF-пина и получала LF от общего `*.json`. `700d516` вернул откат проб
байт-в-байт, добавил CRLF-пин карточки и selftest, проверяющий точные байты;
запечатанные digest'ы и пороги не менялись. CI `44159576484` — **success**.
Граница: digest привязан к представлению, объявленному в `.gitattributes`;
смена представления требует перепечатки карточек и нового прогона, а не тихого
пересчёта.

Точные результаты:

- policy: 23 правила JSON — единственный источник (19 до R8 + 4 правила `head`); parity-гейт
  ловит удаление deny;
- write: перезапись существующего файла — отказ, `..` и symlink наружу — отказ;
- read: потолок выдачи 8192 B, строка сверх потолка не выдаётся; `search` не падает
  на Unicode; `list` — один `resolve_in`;
- KVM: QMP `present=true, enabled=true`, `kvm:kvm_entry=63898` в пробе; отрицательный
  контроль без `/dev/kvm` отказал, TCG не подставлялся;
- head: 8/8 критических контролей отвергнуты точными кодами; normal — 3 строки/144 B/
  `truncated=true`; 3 повтора совпали; host и QEMU/KVM связаны digest'ами;
- реестр: `active` пуст; все шесть legacy `quarantined`; `search` rejected; `net` —
  отдельный bridge path;
- пилот: 3/3 идентичные генерации, 20/20 спецификаций, baseline PASS, 16/16 + 8/8
  мутантов, 3/3 повтора; кандидаты не активированы.

Чего это не доказывает: KVM_RUN — факт исполнения, не изоляция; head slice — механизм
чтения и допуска, не поведение всех инструментов; promoter v0 не видел настоящей
owner-подписи; пилот — инженерный scorecard одного шаблона, не статистическое
доказательство. `K9_proven` не выдан ни на одном этапе.

### 1.12. Test-only активационная репетиция (этап 11)

Владелец сказал «делай пока с тестовой подписью все». Это разрешило прогнать цепочку
допуска на эфемерном ключе, но не создавать настоящий owner-ключ и не активировать
production. Найден и закрыт дефект: `admitted` с `test_only:true` и `owner_signed:true`
мог стать `active`. Теперь `active` требует **явного** `test_only:false`; test-only,
отсутствие поля и не-bool дают `admitted_inactive`. Это объявленное поле, а не подпись:
подпись проверяет promoter.

`bin/activation_rehearsal.py` создаёт ключ и рабочий каталог вне репозитория, подписывает
манифест, проверяет отказ без `--allow-test-only` и приём с ним, ловит изменённый байт,
выполняет `promoter verify/store`, строит временный registry-песочный журнал и запускает
`head_slice_host` через `memfd + F_SEAL_* + execveat` на Linux. В WSL: **33/33 PASS**
на тот момент; после job-проверки — **34/34** (§1.15),
normal — 3 строки/144 B/`line_cap`, outside-root — `S6_CLOSURE_BREACH`; production
`registry.jsonl`, `registry.events.jsonl`, `registry.state.json` не изменены, `head`
остаётся `candidate`, `active` пуст. CI job `admission` проходит ту же цепочку без
`--build` (бинарь собирается отдельным шагом) — **31/31 PASS**; CI `44159576484` —
success. Красный `44155903515` был только расхождением представления: проба гейта
нормализовала CRLF у prereg, а карточка не была запиннена; `700d516` исправил откат
проб на байты и добавил CRLF-пин, digest'ы не менялись. Evidence:
[`research/outputs/ACTIVATION-REHEARSAL-R1-2026-11-17.txt`](../research/outputs/ACTIVATION-REHEARSAL-R1-2026-11-17.txt).
Runbook владельца: [`OWNER-RUNBOOK-2026-11-17.md`](OWNER-RUNBOOK-2026-11-17.md).

Граница: test-only ключ не является owner-ключом; реестр не проверяет подпись;
`run_tool_g` по-прежнему не имеет ветки `head`, поэтому conversational loop не запускает
head даже после активации — запуск идёт через promoter. `K9_proven` нет.

### 1.13. Сухая owner-церемония в песочнице (этап 12)

Test-only репетиция доказывает отказ, но не проверяла положительную ветку: манифест с
`test_only:false` и promoter **без** `--allow-test-only`. Этот разрыв закрыт песочным
прибором [`bin/owner_ceremony_dry_run.py`](../bin/owner_ceremony_dry_run.py). Он создаёт
эфемерный ключ вне репозитория с anchor `test_only:false`, подписывает манифест из точных
байтов, проверяет `admission.verify` без разрешения, выполняет `promoter verify/store` без
разрешения, строит временный registry-песочный журнал с событием `admitted` и запускает
`head_slice_host` через promoter на Linux. Seed не печатается; CLI `keygen` по-прежнему
отказывается создавать что-либо, кроме test-only, — новый помощник вызывается только
прибором, не пользовательской командой.

Результаты: в WSL **56/56 PASS** на тот момент; после job-проверки — **57/57** (§1.15)
(после добавления негативных контролей и сверки содержимого
фикстуры), включая `memfd/execveat`, normal 3 строки/144 B/`line_cap` и outside-root
`S6_CLOSURE_BREACH`; на Windows без launch — **45/45**. В песочном реестре `head` = `active`,
`active=[head]`; production-файлы реестра до и после совпали, production `head` остаётся
`candidate`, production `active` пуст. CI job `admission` запускает прибор после test-only
репетиции, без `--build` (бинарь уже собран). Evidence:
[`research/outputs/OWNER-CEREMONY-DRY-RUN-R1-2026-11-17.txt`](../research/outputs/OWNER-CEREMONY-DRY-RUN-R1-2026-11-17.txt).

Границы. Эфемерный ключ — не owner-ключ; anchor `test_only:false` — объявление для
песочницы, а не approval. Реестр не верифицирует подпись. Событие связывает
`admission_digest`, а манифест содержит `key_fingerprint`, но **allowlist owner-anchor в
реестре отсутствует**: владелец обязан сверить fingerprint и anchor вне канала до
добавления события. `run_tool_g` по-прежнему не имеет ветки `head`; `K9_proven` не выдан.

### 1.14. Аудит допуска: строгий JCS, дифференциальная проверка, края `head`, owner-отчёт

Это продолжение безопасных работ 17.11.2026; настоящий owner-ключ, production `active`,
`K9_proven` и публикация по-прежнему не выполнялись.

**Строгий JCS в двух реализациях.** Python admission и Rust admission теперь отвергают
повтор ключа, float, integer вне `±(2^53−1)` и не-ASCII ключи до проверки подписи.
Добавлен независимый Rust-помощник `core-rs/src/bin/canonical_check.rs` и прибор
[`bin/differential_admission.py`](../bin/differential_admission.py): 32 случайных JCS-вектора
и 25 проверок манифеста дают **0 расхождений** Python/Rust по каноническим байтам, допуску
и отказу. Rust lib: **131 тест** на тот момент (было 118; после §1.15 — 133). Evidence:
[`research/outputs/DIFFERENTIAL-ADMISSION-R1-2026-11-17.txt`](../research/outputs/DIFFERENTIAL-ADMISSION-R1-2026-11-17.txt), C-0318.

**Сухая церемония усилена негативными контролями.** К положительной ветке добавлены:
CLI `keygen` без `--test-only` и попытка записать ключ в репозиторий; изменённые байты
манифеста, подписи и anchor; чужой fingerprint; просроченный и ещё не вступивший admission;
`seq=0`; отсутствующий `test_only`; повтор ключа; integer вне JCS-диапазона; повтор `seq`
и разрыв `prev` в песочном журнале; `test_only:true`, отсутствие и не-bool значение в
событии реестра. Evidence различает digest **манифеста фикстуры** и digest **содержимого**
`head-slice.txt` (471 B), сверяя содержимое с записью в манифесте. WSL — **56/56 PASS** на
тот момент (сейчас 57/57 после job-проверки, §1.15),
Windows без launch — **45/45**. C-0319.

**Края `head`.** 13 новых Rust-тестов на тот момент (всего 131 в lib; после §1.15 — 133): частичная строка при EOF и при
`byte_cap`, граница `line_cap`/`byte_cap`, CR без `\n`, UTF-8, разорванный между чанками,
невалидный UTF-8 в невыданной части, огромная строка → `output_cap`, ровно `OUTPUT_BYTES`,
пустой файл/пустая строка, несовпадение размера → K11, дубликат ключа fixture-манифеста →
S1, 48 сгенерированных входов с инвариантами и повторностью. Fixture-манифест теперь
разбирается строгим JCS-парсером. Evidence:
[`research/outputs/HEAD-EDGE-R1-2026-11-17.txt`](../research/outputs/HEAD-EDGE-R1-2026-11-17.txt), C-0321.

**Owner-side verify-only.** [`bin/verify_owner_package.py`](../bin/verify_owner_package.py)
читает манифест, подпись, anchor, шесть точных артефактов, fixture-манифест и его
содержимое, evidence и production-состояние реестра; ничего не пишет, ключ не читает.
`test_only=true` по умолчанию считается провалом; `--allow-test-only` только осматривает.
Self-test на эфемерном пакете: **5 сценариев** (годный пакет, test-only без разрешения,
изменённая карточка, изменённое содержимое фикстуры, изменённая подпись), C-0320. На
тот момент это была единственная проверка **sha256 содержимого** фикстуры; в §1.15 runtime
`head` тоже начал сверять содержимое, поэтому owner-прибор остаётся независимой второй
проверкой, а не единственной.

**Известные границы после аудита.** Promoter не реализует полную семантику карточки
(связывание `--job` root/fixture/checks/admission закрыто в §1.15); реестр не проверяет
подпись и не имеет allowlist owner-anchor; `run_tool_g` не имеет ветки `head`. Ни один из
этих пунктов не закрашен «зелёным».

### 1.15. Job привязан к admission, содержимое фикстуры сверяется (18.11.2026)

Продолжение «делай первые два»: закрыты два разрыва, названные в §1.14, без активации
production. Настоящий owner-ключ не создавался, `K9_proven` не выдавался.

**Promoter: `--job` как данные, а не доверенная конфигурация.** `bin/promoter.py` читает
job строгим JCS-парсером (`admission.load_json_bytes`), требует ровно шесть полей
(`root`, `now_unix`, `fixture_manifest`, `admission`, `checks`, `cases`) и сверяет каждое
значение с уже проверенными CLI-путями:

- `job.root` — существующий каталог; fixture-манифест должен лежать ровно в
  `root/<fixture_root>`, а `fixture_root` — безопасный сегмент без `/`, `\`, `..`;
- `job.fixture_manifest` равен пути `--fixture`, прошедшему digest-проверку;
- `job.checks` содержит ровно шесть полей и каждый путь равен соответствующему
  `--card/--source/--binary/--fixture/--policy/--room`;
- `job.admission` содержит ровно `manifest/sig/anchor` и каждый путь равен
  `--manifest/--sig/--anchor`;
- `cases` — непустой массив; per-case override `admission`, `checks` или
  `fixture_manifest` запрещён, иначе один кейс мог бы отключить допуск внутри запуска;
- `--job-fd` зарезервирован promoter; дубликат `--job` (включая `--arg=--job`) —
  отказ, а не «последний победил».

Точные проверенные байты job сохраняются в `exact_bytes.job` и в `store/job.json`;
`promotion.json` содержит `job.sha256`. `head promote` без job отказывает до store и
launch. На Linux job и binary передаются через два запечатанных memfd; job-memfd намеренно
не `CLOEXEC`, binary — `CLOEXEC`; `_argv_with_job` убирает путь `--job` и добавляет
`--job-fd <fd>`, после чего `execveat` заменяет процесс. Хост читает унаследованный fd,
делает `seek(0)` (иначе offset после `os.write` даёт пустой JSON) и не имеет path-fallback.

**Runtime `head`: размер и sha256.** `file_read_stream` после `openat2`/`fstat` сверяет
`st_size` с манифестом, затем предел `MAX_HASH_BYTES = 8 MiB` (`K4`, а не частичное чтение),
читает ровно объявленный размер (+1 для обнаружения роста), сравнивает `sha256` с записью
манифеста (`K11` при расхождении) и отдаёт **те же** байты через `Cursor`. Между проверкой
хеша и выдачей нет повторного чтения пути, поэтому TOCTOU-подмена не проходит. Два новых
Rust-теста: файл того же размера с другими байтами (`abd` против хеша `abc`) отвергнут
`K11_ADMISSION_REQUIRED` с упоминанием `sha256`; файл `MAX_HASH_BYTES + 1` отвергнут
`K4_RESOURCE_LIMIT` без чтения содержимого. Всего в lib — **133 passed**.

**Чем это не является.** Job-связывание не реализует полную семантику карточки и не
доказывает, что `head` ведёт себя правильно на всех входах; `now_unix` не подписан, но
promoter проверяет допуск на `--now`, а хост — на `now_unix`, поэтому обе точки остаются
fail-closed. Предел 8 MiB означает, что большая фикстура отвергается, а не читается
потоково. Реестр по-прежнему не проверяет подпись и не имеет allowlist owner-anchor;
`run_tool_g` по-прежнему без ветки `head`; production `head` — `candidate`, `active` пуст.
`K9_proven` не выдан.

Evidence: [`PROMOTER-JOB-BINDING-R1-2026-11-18.txt`](../research/outputs/PROMOTER-JOB-BINDING-R1-2026-11-18.txt)
(18/18 Windows, 21/21 WSL), [`HEAD-EDGE-R1-2026-11-17.txt`](../research/outputs/HEAD-EDGE-R1-2026-11-17.txt)
(133 passed), [`ACTIVATION-REHEARSAL-R1-2026-11-17.txt`](../research/outputs/ACTIVATION-REHEARSAL-R1-2026-11-17.txt)
(34/34 WSL, 22/22 Windows), [`OWNER-CEREMONY-DRY-RUN-R1-2026-11-17.txt`](../research/outputs/OWNER-CEREMONY-DRY-RUN-R1-2026-11-17.txt)
(57/57 WSL, 45/45 Windows), [`HEAD-SLICE-R1-2026-11-17.txt`](../research/outputs/HEAD-SLICE-R1-2026-11-17.txt)
(host+QEMU PASS). C-0322/C-0323.

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
| 1 | K6 не обеспечен полностью: `head` fail-closed на unknown class, но legacy-код остаётся | конституция, WSL CONTROL | частично; legacy `quarantined`, P0 |
| 2 | K7 не проверяется | конституция | открыт, P1 |
| 3 | K9 не обеспечен: admission v0 проверяет подпись, но owner-ключа нет | конституция, WSL N/A | частично; активации нет, P0 |
| 4 | K11 не обеспечен: admission v0 есть, настоящей owner-подписи нет | конституция, WSL N/A | частично; церемония ключа за владельцем, P0 |
| 5 | типизированные I/O 0/6 | TOOL-CARD-FIT | открыт, P0 |
| 6 | `kind` не закрыт формально | TOOL-CARD-FIT, DESIGN-0002 | открыт, P0 |
| 7 | `new_tool.py` не написан | DESIGN-0002 | **закрыт** 17.11.2026: пилот PASS, кандидаты не активны |
| 8 | `bin/tool_examples.py` упомянут в лестнице, но отсутствует в коммите | DESIGN-0002 | хвост |
| 9 | `tool_card.py --render` не показывает `closure.net` | R3 C44 | хвост |
| 10 | `netprobe` требует повторного замера после K3 | TOOL-CARD-FIT | хвост |
| 11 | второй клон и локальный `nomos` не каноничны | `C:\111\herness`, `parts/nomos` | решение владельца |
| 12 | CRLF-шум в working tree | git status | не коммитить `git add -A` |
| 13 | `card_atoms` синтезировал чтение и проверял конфликт в одну сторону | R5 §3, C-0313 | **закрыт** 16.11.2026, 31 проверка |
| 14 | `read`/`search` TOCTOU и `head` читает файл целиком | R5 §3, `loopmod.rs` | **закрыт** Stage 4/7: head потоковый, legacy починен |
| 15 | Q1–Q10 не были зафиксированы | R5 §7 | **закрыт** 16.11.2026, решения и словарь v2 |
| 16 | `tool-card-v1` не имеет полного semantic validator | Q2, S01 R6 | частично: promoter v0 сверяет digest'ы и подпись, схема — draft |
| 17 | QEMU-комната не построена полностью | Q5, R01 R6 | KVM_RUN измерен; head slice в microvm без сети/диска; TCG не граница |

---

## 3. Где именно остановились

Все этапы 0–12 исполнены и закоммичены; рабочее дерево, кроме pre-existing
CRLF-шумов, чистое. Положительная ветка проверена в песочнице (этап 12), но это не
настоящая церемония: `head` остаётся **candidate**, настоящий owner-ключ не создавался и
не читался, admission не подписан, `registry.state.json` даёт пустой `active`, ни один
инструмент не активирован, `K9_proven` не выдан. Кандидаты пилота лежат в
`lab/candidates/` как артефакты, а не как допущенные инструменты.

Что готово к следующему шагу:

1. Владелец читает evidence: `research/outputs/REPRO-R8-2026-11-17.txt`,
   `research/kvm/KVM-RUN-2026-11-17.txt`, `research/outputs/HEAD-SLICE-R1-2026-11-17.txt`,
   `research/outputs/PILOT-GENERATOR-R1-2026-11-17.txt`; проверяет решения
   [`docs/DECISIONS-R8-2026-11-17.md`](DECISIONS-R8-2026-11-17.md).
2. Если решения приняты — церемония настоящего owner-ключа (вне репозитория и вне
   контекста агента), затем подпись admission для `head` по exact bytes и активация через
   registry event. До этого `head` обязан отвечать `S13_TOOL_INACTIVE`.
3. После активации — отдельный эксперимент на живой инструмент: `head` в комнате с
   наблюдением `observed_*`, без сети/записи/host mounts. Это новый порог, не продолжение
   HEAD-SLICE-R1.
4. Пилот генератора не является разрешением на второй шаблон: расширение — новый prereg
   с порогами до данных.
5. Долги, не закрытые R8: K7, полный semantic validator карточки, `tool_examples.py`,
   `tool_card.py --render` без `closure.net`, `netprobe` после K3, второй клон и `nomos`.

Если следующий агент захочет «упростить» — сначала прочитать §4.4 и
[`docs/WHERE-I-STOPPED.md`](WHERE-I-STOPPED.md): ослабление гейта запрещено.

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

Ожидание: HEAD и `origin/main` включают R8-этапы `e82dc22`, `d95c533`, `96470e9`,
`318eb9e`, `729fee8`, `f790ef5`, `8d1f542`, `a6e7292`, `92963cf`, guard `a95fe58`,
репетицию `c063ded`, CI `8c30f27`, байтовый откат проб `700d516` и сухую церемонию
`fe143b6`, плюс docs-handoff после них. R8 evidence — `384d804`; R7 — `c63f3b8`;
R8-бриф — `e5182b7`; R6-бриф — `09a6acf`; R5 — `c2fc552`; R4 — `4d1fae5`. В status
только pre-existing CRLF-модификации, которых мы не трогали. **Не делать `git add -A`.**
Добавлять только конкретные пути.

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
- не считать пилот генератора разрешением на активацию: кандидаты в `lab/candidates/`
  не допущены и не являются `active`;
- не создавать настоящий owner-ключ, не читать его в контекст и не подписывать admission
  без владельца; тестовый admission и песочную owner-церемонию не выдавать за approval;
- не менять конституцию K1–K11: это право владельца, агент может только просить.

---

## 5. Решения R8 закрыты делегированием; что осталось владельцу

Q1–Q10 приняты владельцем и не переоткрывались. Q11–Q18, F04 и A01 выбраны агентом
17.11.2026 по прямому делегированию «делай сам все поочерёдно» и записаны в
[`docs/DECISIONS-R8-2026-11-17.md`](DECISIONS-R8-2026-11-17.md); это **не** approval
внешних моделей и **не** изменение конституции. Каждый выбор подкреплён кодом, тестом
или evidence; расхождения ответов R8 не «усреднялись».

| id | выбор | где реализован |
|---|---|---|
| Q11 | полная семантика карточки — на promoter; runtime — admission, exact bytes, тонкая проверка digest, data class, K4 | `bin/promoter.py`, `core-rs/src/loopmod.rs` |
| Q12 | `CHUNK=4096`, `bytes_read` — конец последней выданной строки, EOF только `read()==0`, CR сохраняется, `output_cap` — не отказ | `core-rs/src/head.rs`, `lab/prereg/HEAD-SLICE-R1.json` |
| Q13 | WSL2 + KVM, `-M microvm`, без TCG-fallback | `bin/kvm_probe.py`, `bin/head_slice.py` |
| Q14 | наблюдение — измерение, не self-report; claim только `observed_in_guest`/`enforced_by_kernel` | `research/kvm/`, HEAD evidence |
| Q15 | operational Ed25519 + offline backup; реальный ключ — только владелец | `bin/admission.py`, test-only self-test |
| Q16 | пилот: 20 спецификаций, 24 мутанта, 3 повтора; пороги до данных | `bin/pilot_generator.py`, `lab/pilot/` |
| Q17 | порядок K11 → S1 → S6 → K6 → объект → K4 → S12; словарь v3 | `lab/refusal-codes.json` |
| Q18 | реестр заморожен; genesis events; legacy `quarantined`; `active` производный | `lab/tools/registry.events.jsonl`, `bin/registry_state.py` |
| F04 | две оси: подпись и право запуска; `activated` не хранится | `bin/registry_state.py` |
| A01 | JCS + detached Ed25519 + exact-byte binding; promoter на хосте; Linux memfd+`F_SEAL`, Windows — verify/store | `bin/promoter.py` |

Осталось владельцу (агент не имеет права):

1. Прочитать evidence и решения; сказать «да»/«нет» по каждому пункту.
2. Провести церемонию настоящего owner-ключа; приватный ключ не должен попасть в
   контекст агента или git. В отчётах — только fingerprint. Реестр не содержит allowlist
   owner-anchor: fingerprint и anchor нужно сверить вне канала до добавления события.
3. Подписать admission для `head` (или отказать). Только после этого возможна активация
   через registry event; `K9_proven` не выдаётся.
4. Решить, публиковать ли что-либо наружу; без «да» публикации нет.
5. Решить судьбу второго клона `C:\111\herness` и локального `nomos`.

Если ответы владельца, R7 или R8 противоречат друг другу — не выбирать «среднее». Нужен
эксперимент, который различит варианты, или явное решение владельца.

---

## 6. Полезные ссылки

- [Конституция v0](CONSTITUTION-v0-2026-11-16.md)
- [Где остановились](WHERE-I-STOPPED.md)
- [Решения R8: Q11–Q18, F04, A01](DECISIONS-R8-2026-11-17.md)
- [Исполнение и проверки R8](../research/outputs/R8-IMPLEMENTATION-2026-11-17.txt)
- [Репро R8](../research/outputs/REPRO-R8-2026-11-17.txt)
- [KVM_RUN](../research/kvm/KVM-RUN-2026-11-17.txt)
- [HEAD-SLICE-R1 evidence](../research/outputs/HEAD-SLICE-R1-2026-11-17.txt)
- [PILOT-GENERATOR-R1 evidence](../research/outputs/PILOT-GENERATOR-R1-2026-11-17.txt)
- [Производное состояние реестра](../lab/tools/registry.state.json)
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
- Что KVM_RUN доказывает изоляцию комнаты: он доказывает исполнение под KVM, не
  отсутствие каналов утечки.
- Что HEAD-SLICE-R1 доказывает поведение всех инструментов: только `file_read_stream`
  на синтетической фикстуре с test-only admission.
- Что PILOT-GENERATOR-R1 доказывает безопасность генератора: это инженерный scorecard
  одного шаблона, не статистика и не проверка настоящего owner-ключа.
- Что Landlock audit или ptrace дают полноту наблюдения; это ограниченное свидетельство.
- Что конституция K1–K11 достаточно полна.
- Что WSL-симуляция что-то доказывает про ноутбук.

Это карта смены: что сделано, где остановились, что проверить. Следующий агент обязан
самостоятельно перепроверить предпосылки, а не доверять этому тексту на слово.
