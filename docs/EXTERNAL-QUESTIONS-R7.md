# R7 — развилки, которые R6 не закрыл

**Дата:** 17.11.2026.
**Кому:** внешней модели или человеку, который готов дать независимый инженерный разбор.
**Что это:** бриф, а не approval. Ответы — рекомендации; решения принимает владелец.
**Канон:** [mak777uh/herness](https://github.com/mak777uh/herness), ветка `main`.
**Базовая линия кода:** `9c8af80`.
**Снимок:** [`3d988f8`](https://github.com/mak777uh/herness/tree/3d988f8033a4df942855fc1bf799d128ee62e792) — шесть сырых ответов R6, README и синтез; код не менялся.
**Решения владельца Q1–Q10:** [`DECISIONS-R5-2026-11-16.md`](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/DECISIONS-R5-2026-11-16.md).

Все ссылки ниже прибиты к снимку `3d988f8`. Сводка агента (`R6-SYNTHESIS.md`) в этот бриф
намеренно не включена: это мнение одной стороны, а не вход для независимого разбора.
Сырые ответы A–F — вход; не считать их консенсусом.

---

## 0. Как читать и как отвечать

Ответ полезен, если в нём есть:

- **ANSWER** — прямое решение развилки, а не пересказ вопроса;
- **CHOSEN** — что выбрано и что отвергнуто;
- **WHY** — критерий выбора, включая цену и риск;
- **ARTIFACT** — схема, алгоритм, таблица, тест или команда, которую можно воспроизвести;
- **TESTS** — положительный и отрицательный контроль, включая «прибор слеп»;
- **FAILURE MODE** — как этот выбор даст ложное зелёное;
- **NOT PROVEN** — что выбор не доказывает;
- **CONFIDENCE** — `high` / `medium` / `low` с причиной.

Приоритет — `P0`. Если вопрос вне вашей компетенции, скажите прямо. Не выдумывайте факты
о репозитории: если нужен код, назовите файл и строку, которые вы проверили. Если ссылка
не открывается — скажите, а не достраивайте.

**Чего этот бриф не просит:**

- не менять конституцию, policy, registry, схему, словарь отказов, код или пре-регистрацию;
- не публиковать ответы, ключи, токены или реальные секреты;
- не выдавать `policy_checked` за `K9_proven`, TCG за границу безопасности, JSON Schema
  за доказательство поведения, а отсутствие событий — за отсутствие нарушений;
- не принимать решения за владельца. Владелец решает Q11–Q18; вы даёте технический разбор.

---

## 1. Контекст за один экран

`herness` — харнесс, который должен безопасно порождать свои инструменты из закрытого пула
законов. Конституция K1–K11 задаёт запреты: не читать/писать вне корня, не выходить в сеть
иначе как через объявленный мост, не выносить секрет, не молчать при ошибке, не терять
provenance, не нарушать композицию, не менять себя и не допускать чужое без разрешения.
Первая комната — защищённое пространство владельца; мосты дальше могут иметь свои правила,
только если доказуемо не нарушают конституцию.

Сделано:

- шесть сырых ответов R6 сохранены байт-в-байт с SHA-256;
- `tool-card-v1` — черновик, `head` — пример карточки, фикстура 471 Б / 10 строк;
- `HEAD-SLICE-R1` — пре-регистрация среза, `closed: false`;
- QEMU 11.1.0 на Windows: `whpx` и `tcg`, `microvm` стартует; WSL2 kernel `6.6.114.1`
  имеет `/dev/kvm`, QEMU в WSL не установлен;
- `card_atoms` проходит 31 проверку; гейты — 30 из 32, N/A 2.

Не сделано: формальное ядро, `LawRecord`, semantic validator, admission, owner-ключ,
QEMU-комната, ограниченное чтение в Rust, promotion, генератор, пилот.

### 1.1. Проверяемые факты снимка

Это не мнения R6, а поведение кода на снимке; проверяйте сами.

| факт | где |
|---|---|
| `read` делает `resolve_in` → `metadata` → `read_to_string`, то есть проверяет путь отдельно от открытия и читает файл целиком | [`loopmod.rs`](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/core-rs/src/loopmod.rs), `resolve_in` ~587, `tool_read_in` ~821 |
| `search` читает каждый файл целиком через `read_to_string` | там же, `tool_search_in` ~625 |
| `write_beneath` ставит только `RESOLVE_BENEATH \| RESOLVE_NO_SYMLINKS` | там же, ~936 |
| `resource_of` для пути вне корня подставляет `/mnt` заново; `policy_allows("read","read", …)` на таком ресурсе может вернуть `true`; `resolve_in` до этого проверяет `starts_with(root)` | там же, `resource_of` ~547, `resolve_in` ~607 |
| `resolve_in` всегда проверяет политику как `("read","read")`, независимо от вызывающего инструмента; вызывают `read`, `list`, `search`, `seal` | там же |
| `seal` и `netprobe` запускают себя через `Command::new(current_exe())` | там же, ~295 и ~374 |
| у `head` нет разрешающего правила в policy; `card_atoms --check head` даёт `rc=3` | [`policy.json`](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/lab/tools/policy.json), [`head.json`](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/lab/tools/cards/head.json) |
| в `registry.jsonl` шесть записей хранят `"status": "active"`, включая `search`; Q8 отверг `search` | [`registry.jsonl`](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/lab/tools/registry.jsonl) |
| проверки admission в коде нет; `K11_ADMISSION_REQUIRED` есть только как строка словаря | [`refusal_codes.py`](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/bin/refusal_codes.py) |
| seccomp-фильтр в госте зависит от `NET`; ядро без `NET` даёт `Invalid argument`; `pre_exec` даёт `ENOSYS`, фильтр ставит сам процесс | [`seccomp-net-dependency.txt`](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/research/outputs/seccomp-net-dependency.txt), [`pre-exec-seccomp.txt`](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/research/outputs/pre-exec-seccomp.txt) |
| схема требует `process_spawn: false` и `max_processes: const 1`; в `head` draft `max_bytes_read = 65536`, `output_bytes = 8192` | [`tool-card-v1.schema.json`](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/lab/tools/tool-card-v1.schema.json), [`head-v1.draft.json`](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/lab/tools/drafts/head-v1.draft.json) |

### 1.2. Что уже решено владельцем и не переоткрывается

| id | решение |
|---|---|
| Q1 | пять файловых `kind`: `file_read`, `directory_read`, `file_write`, `digest`, `bridge_request` |
| Q2 | `tool-card-v1` — draft, не действующий закон |
| Q3 | словарь отказов v2: `K4_RESOURCE_LIMIT`, `K6_DATA_CLASS_UNKNOWN`, `K6_SECRET_EGRESS`, `K11_ADMISSION_REQUIRED` |
| Q4 | первый срез — только синтетический `model_visible` fixture |
| Q5 | TCG — симуляция; security-утверждение требует аппаратной виртуализации |
| Q6 | K6 v0 fail-closed: `public`/`model_visible`; `unknown`/`secret` — отказ |
| Q7 | генератор отделён от promoter; owner-подпись + host-side promoter |
| Q8 | `search` в первом срезе отвергнут |
| Q9 | scorecard — черновик пре-регистрации |
| Q10 | сырые ответы остаются в репозитории с хешами |

Конституция: [`CONSTITUTION-v0-2026-11-16.md`](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/CONSTITUTION-v0-2026-11-16.md).
Пре-регистрация: [`HEAD-SLICE-R1.json`](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/lab/prereg/HEAD-SLICE-R1.json).
Сырые ответы R6: [A](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/research/external/2026-11-17-R6-answer-A.txt),
[B](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/research/external/2026-11-17-R6-answer-B.txt),
[C](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/research/external/2026-11-17-R6-answer-C.txt),
[D](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/research/external/2026-11-17-R6-answer-D.txt),
[E](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/research/external/2026-11-17-R6-answer-E.txt),
[F](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/research/external/2026-11-17-R6-answer-F.md).

---

## 2. Что именно осталось открытым

Ниже — только расхождения; общие места R6 не переспрашиваются.

Соответствие решениям владельца: Q11 → R7-F01, Q12 → R7-S02, Q13 → R7-R01,
Q14 → R7-R02, Q15 → R7-R03, Q16 → R7-T02, Q17 → R7-S05, Q18 → R7-T01.
R7-F04, R7-A01 и R7-AUDIT — дополнительные P1-вопросы, не отдельные решения Q.

1. **Канонический semantic validator.** A, B, C, D, E выбирают Rust; F — Python с
   receipt'ом для runtime. Нужно решить, где живёт единственная семантика и что именно
   доверяет promoter.
2. **Семантика `file_read_stream`.** Шесть таблиц различаются по CRLF, частичной строке,
   смыслу `truncated`, учёту read-ahead, коду для невалидного UTF-8 и отсутствующего файла.
   E в S02 читает один байт сверх бюджета для EOF-проверки и выдаёт частичную строку.
3. **Комната.** A/B/E/F тянут к WSL2+KVM, C — к WHPX, D — к обоим с оговорками. QEMU в WSL
   нет; `/dev/kvm` есть. В NET-less госте seccomp не ставится; `pre_exec` не работает.
4. **Модель процессов.** `max_processes: const 1` конфликтует со схемой «PID1 supervisor +
   один инструмент». Нужно определить, что считается процессом.
5. **Наблюдение.** A/B — seccomp+отдельный канал; C/D — ptrace/strace; E —
   seccomp-unotify+барьер; F — инструментирование+strace. C предупреждает о TOCTOU
   указателей в seccomp-unotify. Нужен механизм, который реально работает в этой комнате.
6. **Owner-ключ.** A/E — recovery root + operational; B — sign+revoke без восстановления
   подписи; C — active+standby; D/F — один ключ + backup/re-admission. Разный ответ на
   вопрос, может ли recovery выдать допуск.
7. **Реестр.** Все согласны, что `active` производный, но текущий `registry.jsonl` хранит
   `active`, а `search` активен вопреки Q8. Нужен план миграции и точная формула.
8. **Генератор.** A/D — один шаблон; B/C — три; E — четыре; F — 12 spec на 5 kind. Разные
   пороги и held-out. Нужен наименьший пилот, который ещё что-то доказывает.
9. **Порядок отказов.** B/E: `K11 > K6_EGRESS > K6_UNKNOWN > S6 > K4 > S1`; C:
   `K11 > K6 > scope > K4 > S1`; F: `K11 > K6_EGRESS > K6_UNKNOWN > K4 > S6 > S1`.
   Нужно решить, что первично при «вне корня + неизвестный класс» и `K4` vs `S6`.

---

## 3. Вопросы

### R7-F01 [P0] Где живёт единственная семантика карточки

**Контекст.** Сейчас есть `bin/card_atoms.py`, `bin/tool_card.py` и JSON Schema; Rust
semantic validator отсутствует. R6: A/B/C/D/E — Rust, F — Python + receipt.

**Ответьте:**

1. Где должен исполняться канонический валидатор: CI, promoter, runtime или всё сразу?
2. Если Python канонический, что именно подписывается/доверяется в receipt, как promoter
   проверяет версию правил, digest входа и отсутствие подмены, и почему это не второй путь
   разрешения?
3. Если Rust канонический, как он сосуществует с текущим Python-checker без двух семантик:
   кто эталон, какие векторы, что происходит при расхождении?
4. Какие проверки обязательны сверх JSON Schema, а какие можно убрать из v0?
5. Как валидатор узнаёт, что карточка описывает именно этот template/binary, а не только
   сама себе непротиворечива?

**ARTIFACT:** таблица «правило → что отвергает → положительный тест → отрицательный тест»,
точные файлы/функции, формат векторов, политика расхождений.

**TESTS:** хотя бы: `head` с пустым scope; `file_write` с пустым write; `bridge_request`
без моста; wildcard в пути; `process_spawn: true`; неизвестный `kind`; `max_bytes_read`
больше лимита карточки; пример, который проходит схему, но не проходит семантику.

**NOT PROVEN:** что валидатор проверяет поведение кода, а не только декларацию.

---

### R7-S02 [P0] Одна точная таблица `file_read_stream`

**Контекст.** Шесть ответов дают разные таблицы. Пре-регистрация требует: обычный fixture —
ровно первые 3 строки; `bytes_read <= max_bytes_read` во всех прогонах; при файле больше
лимита не выдано ни одного байта сверх лимита; три повтора детерминированы. Менять пороги
нельзя.

**Ответьте одной таблицей «вход → `lines` / `bytes_read` / `truncated` / `stop_reason` /
код отказа» для случаев:**

1. пустой файл;
2. ровно N строк, `line_count = N`, EOF сразу после последнего `LF`;
3. файл без завершающего `LF`;
4. CRLF и одиночный `CR`;
5. byte cap ровно на границе строки;
6. byte cap внутри строки;
7. byte cap внутри многобайтового UTF-8;
8. `line_count` достигнут до EOF;
9. `line_count` достигнут ровно на EOF;
10. невалидный UTF-8;
11. файла нет;
12. путь ведёт на каталог/FIFO/устройство;
13. файл вырос/уменьшился во время чтения (для v0 fixture `immutable: true` — что всё равно
    должно быть в контракте, а что можно отложить).

**Обязательные ограничения:**

- `bytes_read` — только реально полученные из FD сырые байты, включая разделители; он
  никогда не больше `max_bytes_read`;
- нельзя читать лишний байт «для проверки EOF» сверх бюджета;
- частичная строка не выдаётся как полная;
- `truncated` не должен означать «файл длиннее вывода» и «байтовый лимит» одновременно без
  явного `stop_reason`;
- `line_count` и `max_bytes_read` — разные причины остановки;
- `output_bytes` не подменяет `bytes_read`.

**ARTIFACT:** псевдокод с сырым `read` (без `BufReader::take`), правила UTF-8, таблица
ожидаемых значений для fixture 471 Б / 10 строк, включая `line_count=3, max_bytes=4096` и
`line_count=200, max_bytes=64`.

**TESTS:** положительный контроль (обычное чтение работает), отрицательный (byte cap не
превышен), граница ровно-в-лимит, длинная строка, CRLF, отсутствие `LF`, невалидный UTF-8.
Для каждого — что именно доказывает тест и что он не доказывает.

**FAILURE MODE:** read-ahead увеличивает `bytes_read`; частичная строка выглядит полной;
`truncated=false` при обрезке; EOF-проверка читает сверх лимита; счётчик не включает
прочитанный хвост чанка.

---

### R7-R01 [P0] Комната, которая действительно запустится на этой машине

**Контекст.** Windows QEMU 11.1.0: `whpx` и `tcg`, `microvm` стартует. WSL2 kernel
`6.6.114.1`: `/dev/kvm` есть, QEMU не установлен. В госте без `NET` seccomp-фильтр не
ставится; `pre_exec` даёт `ENOSYS`.

**Ответьте:**

1. Какой один security-путь выбирать для v0: WSL2+KVM или Windows+WHPX? Что именно нужно
   измерить, чтобы выбор был фактом, а не верой?
2. Дайте точную команду QEMU с **одним** `-accel`, без fallback на TCG, с `microvm`,
   `-nic none`, без 9p/virtiofs/host mounts, и объясните каждое устройство.
3. Как доказать, что ускоритель действительно использован: QMP, лог, маркер из гостя,
   digest? Что должно попасть в evidence, чтобы TCG нельзя было выдать за security-run?
4. Как в этой комнате поставить seccomp, если фильтр зависит от `NET`, а `pre_exec` не
   работает? Выберите: `NET=y` без NIC, Landlock, harden_self, отказ от seccomp — и
   объясните последствия.
5. PID1 — supervisor или инструмент? Что считает `max_processes: const 1` — дерево
   инструмента или всю комнату? Как это записать в схеме, не ослабив K4?
6. Что входит в TCB, а что нет? Где заканчивается «измеренная конфигурация» и начинается
   «безопасность QEMU/гипервизора», которую вы не доказываете?

**ARTIFACT:** команда, ожидаемые логи/маркеры, таблица TCB, профиль cgroup/rlimit/Landlock,
негативные контроли (сеть, запись, host mount, побег из root FD).

**NOT PROVEN:** отсутствие 0-day в QEMU/гипервизоре, изоляция гостя как таковая.

---

### R7-R02 [P0] Наблюдение, которое не врёт

**Контекст.** R6 предлагает seccomp+канал (A/B), ptrace/strace (C/D), seccomp-unotify (E),
инструментирование+strace (F). В NET-less госте seccomp не ставится; `pre_exec` не работает;
C предупреждает о TOCTOU указателей в seccomp-unotify.

**Ответьте:**

1. Какой минимальный механизм наблюдения реально работает в этой комнате и что он видит:
   syscall-имена, пути, байты, потоки, детей?
2. Как отличить `observed_independent` от `observed_self_reported`? Что именно можно
   утверждать в v0, не выдавая self-report за независимое наблюдение?
3. Как обнаружить слепой монитор: ноль событий при чтении, пропущенные потоки,
   `dropped_events`, устаревшая версия, отсутствие трассы?
4. Как записывать attempted vs observed effects и как решение по указателю не превращается
   в TOCTOU?
5. Какие негативные контроли обязательны: попытка чтения вне карточки, сеть, spawn, запись,
   секрет; что должно произойти и в трассе, и в стене?
6. Что делать, если монитор и стена расходятся: трасса видит событие, а стена пропустила,
   или наоборот?

**ARTIFACT:** точный формат `effects-observation-v1`, поля, правило `verdict` (within_card /
breach / unknown), правило провала, как digest'ы связывают run/card/binary/room.

**NOT PROVEN:** полнота наблюдения, отсутствие скрытых каналов, эквивалентность поведения
под трассировкой и без.

---

### R7-R03 [P0] Owner-ключ без второго пути допуска

**Контекст.** Один владелец, Windows, offline-подпись, HSM не обязателен; в репозитории
ключа ещё нет. R6 расходится: recovery root (A/E), sign+revoke (B), active+standby (C),
single+backup (D/F).

**Ответьте:**

1. Может ли recovery-ключ добавлять новый signing key? Если да, чем это отличается от
   второго пути допуска и как это ограничить доменом/полномочиями?
2. Если recovery не может выдавать допуск, что происходит при потере единственного ключа:
   полный re-admission, ручная замена trust anchor, что именно?
3. Где хранится trust anchor promoter'а, чтобы агент с правом записи в репозиторий не мог
   его подменить? Копия в git — только для чтения или нет?
4. Дайте точные offline-команды для Windows (генерация, backup, подпись, проверка,
   ротация, отзыв), без секретов в ответе. Если предлагаете SSHSIG вместо «голого»
   Ed25519 — объясните, что это меняет в проверке и что нужно записать в решении.
5. Как связать `key_id`, `epoch`, `not_before/expires`, `revoked` и манифест так, чтобы
   старый подписанный манифест не стал снова валидным после отката часов/файлов?
6. Какие тесты доказывают, что recovery не является backdoor, а потеря ключа не даёт
   автоматического допуска?

**ARTIFACT:** схема keyring/revocations, процедура церемонии, команды, тесты, что именно
считается компрометацией.

**NOT PROVEN:** безопасность offline-машины, токена, passphrase и физического хранения;
что владелец понимает, что подписывает.

---

### R7-T01 [P0] Переход от stored `active` к производному статусу

**Контекст.** `registry.jsonl` хранит `"status": "active"` у шести инструментов, включая
`search`, который Q8 отверг. У `head` нет policy-правила (`card_atoms rc=3`). R6 согласен,
что `active` — предикат, но расходится в состояниях и указателе.

**Ответьте:**

1. Дайте точный набор состояний и формулу `active(tool, env)`; какие digest'ы входят и что
   сбрасывает статус.
2. Что делать с шестью legacy-записями: `quarantined`, `needs_revalidation`, оставить как
   исторические? Как не сломать работающий цикл и не ослабить K8/K11?
3. Что делать с `search`: оставить в коде как исторический, убрать из registry, пометить
   `rejected`? Кто и каким действием это фиксирует?
4. Кто пишет registry: только promoter? Генератор — только candidate? Как это проверить
   технически, а не обещанием?
5. Формат append-only: `seq`, `prev_digest`, JCS, подпись владельца, атомарный pointer.
   Где хранится pointer и как он перепроверяется при старте?
6. Как отличить «отозван» от «истёк» и «не проходил revalidation»? Что видит модель, что
   видит журнал?

**ARTIFACT:** схема записи, FSM, миграционная таблица legacy → новое состояние, тесты на
подмену pointer, разрыв hash-chain, повторную активацию отозванного digest'а, изменение
policy на 1 байт.

---

### R7-T02 [P0] Наименьший пилот генератора, который что-то доказывает

**Контекст.** R6: 1 шаблон (A/D), 3 (B/C), 4 (E), 12 spec на 5 kind (F). Все согласны,
что пороги фиксируются до прогона и что числа — инженерный гейт, не статистика.

**Ответьте:**

1. Какой объём выбрать для v0 и почему именно он отделяет «генератор» от «заранее
   написанного шаблона»?
2. Дайте замороженный набор: число функциональных задач, атак/мутаций, held-out,
   повторов, что именно считается критическим контролем.
3. Какие условия «нельзя начинать»? Что должно быть зелёным до первого запуска?
4. Как избежать Goodhart: генератор знает гейт, мутанты известны, held-out утекает?
5. Что остаётся человеком: подпись, review, расширение авторитета? Сколько времени
   владельца считается приемлемым и как это измерить?
6. Что будет считаться «не успехом» и «kill criteria»? Как сохранить все попытки, а не
   лучший из незаписанных вариантов?

**ARTIFACT:** таблица метрик с порогами и знаменателями, состав candidate bundle, список
проверок promoter'а, шаблон отчёта.

**NOT PROVEN:** обобщение на другие шаблоны/kind, статистическая надёжность, безопасность
произвольного кода.

---

### R7-S05 [P1] Порядок отказов и комбинированные нарушения

**Контекст.** B/E: `K11 > K6_EGRESS > K6_UNKNOWN > S6 > K4 > S1`; C:
`K11 > K6 > scope > K4 > S1`; F: `K11 > K6_EGRESS > K6_UNKNOWN > K4 > S6 > S1`.
E предлагает собирать все коды и сортировать; F — сначала scope, класс не запрашивать.

**Ответьте:**

1. Что фиксируется первым: порядок **вычисления** или порядок **выдачи**? Приведите
   конвейер.
2. «Вне корня + неизвестный класс»: какой первичный код и почему? Запрашивается ли класс
   вне корня?
3. `K4` vs `S6`: что важнее для метрик и что видит модель?
4. Что писать в журнал, чтобы не утекали пути/секреты, но было видно все сработавшие
   законы?
5. Как быть с пробелами словаря: невалидный UTF-8 и отсутствующий файл не имеют точного
   кода в v2. Интерим `S1_SCHEMA`/`S2_ARTIFACT_MISSING` или поправка словаря?

**ARTIFACT:** таблица приоритетов, конвейер, пример комбинированного отказа, тесты.

---

### R7-F04 [P1] Лестница статусов и доказательств

**Контекст.** Все согласны: `policy_checked` ≠ `K9_proven`; `K9_proven` в v0 запрещён.
Расходятся в числе и именах ступеней.

**Ответьте:**

1. Дайте точный набор статусов v0 и что доказывает каждый.
2. Какой артефакт обязателен для перехода на ступень и кто его создаёт?
3. Как статус сбрасывается при смене card/source/binary/policy/room digest'а?
4. Как представлять статус в registry/manifest, чтобы его нельзя было «нарисовать»?
5. Какие негативные тесты доказывают, что `policy_checked` не выдают за `K9_proven`, а
   `K11_admitted` — за безопасность?

---

### R7-A01 [P1] Привязка admission к точным байтам

**Контекст.** R6 согласен по JCS + domain separation + Ed25519 + digest'ам, но расходится
в деталях: `stored == JCS(stored)`, SSHSIG vs RFC 8032, `execveat`/`memfd` vs проверка
digest перед запуском, поля манифеста.

**Ответьте:**

1. Дайте минимальную схему `admission-manifest-v1` с обязательными полями и точным
   доменным префиксом.
2. Требовать ли, чтобы сохранённый манифест уже был в JCS? Что это ловит и что ломает?
3. Как привязать запуск к подписанным байтам на Windows/WSL: `execveat`/`memfd` или
   digest-перед-exec? Где остаётся TOCTOU?
4. Как проверять срок, epoch, отзыв и повторное использование манифеста?
5. Какие тесты: подмена байта, пере-сериализация, дублирующийся JSON-ключ, неизвестное
   поле, чужой домен, просроченный манифест, отозванный ключ.

---

### R7-AUDIT [P1] Проверка утверждений R6 по коду

**Контекст.** R6 ответы различаются по качеству проверки: B не читал тела функций, C не
открывал ссылки, D не заявляет проверок, F проверял код.

**Ответьте:** какие конкретные утверждения A–F о снимке `3d988f8` **ложны или не
проверены**? Для каждого — файл/строка и правильная формулировка. Особое внимание:
`resource_of` и `resolve_in`, `max_processes`, `seal`/`netprobe`, seccomp/NET, registry,
`card_atoms`, `head` draft. Не пересказывайте ответы; проверяйте код.

---

## 4. Что будет сделано с ответами

1. Сырые ответы будут сохранены с SHA-256, как R5/R6; они не станут решениями.
2. Утверждения будут проверены по коду; несогласие с ответом фиксируется, а не сглаживается.
3. Владелец решает Q11–Q18; только после этого меняются policy/registry/схема/код.
4. `HEAD-SLICE-R1` остаётся `closed: false`, пока нет комнаты, admission, ограниченного
   чтения и 8/8 негативных контролей.
5. Генератор не начинается до зелёного ручного среза и замороженных порогов.

---

## 5. Ссылки

### 5.1. Решения и контекст

- [Конституция v0](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/CONSTITUTION-v0-2026-11-16.md)
- [Решения Q1–Q10](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/DECISIONS-R5-2026-11-16.md)
- [R5-синтез](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/R5-SYNTHESIS.md)
- [R6-бриф](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/EXTERNAL-QUESTIONS-R6.md)
- [Сырые ответы R6](https://github.com/mak777uh/herness/tree/3d988f8033a4df942855fc1bf799d128ee62e792/docs/research/external)
- [Scorecard — черновик](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/docs/PILOT-SCORECARD-2026-11-16.md)

### 5.2. Схемы, данные, пре-регистрация

- [tool-card-v1.schema.json](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/lab/tools/tool-card-v1.schema.json)
- [head draft](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/lab/tools/drafts/head-v1.draft.json)
- [policy.json](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/lab/tools/policy.json)
- [registry.jsonl](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/lab/tools/registry.jsonl)
- [refusal codes](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/bin/refusal_codes.py)
- [HEAD-SLICE-R1](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/lab/prereg/HEAD-SLICE-R1.json)
- [fixture manifest](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/lab/fixtures/model_visible/manifest.json)

### 5.3. Код и замеры

- [loopmod.rs](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/core-rs/src/loopmod.rs)
- [qemu-accel-2026-11-16.txt](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/research/outputs/qemu-accel-2026-11-16.txt)
- [seccomp-net-dependency.txt](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/research/outputs/seccomp-net-dependency.txt)
- [pre-exec-seccomp.txt](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/research/outputs/pre-exec-seccomp.txt)
- [landlock-probe.c](https://github.com/mak777uh/herness/blob/3d988f8033a4df942855fc1bf799d128ee62e792/core-rs/landlock-probe.c)

### 5.4. Первичные внешние источники

- [RFC 8785 — JCS](https://www.rfc-editor.org/rfc/rfc8785)
- [RFC 8032 — Ed25519](https://www.rfc-editor.org/rfc/rfc8032)
- [openat2(2)](https://man7.org/linux/man-pages/man2/openat2.2.html)
- [seccomp_unotify(2)](https://man7.org/linux/man-pages/man2/seccomp_unotify.2.html)
- [QEMU Security](https://www.qemu.org/docs/master/system/security.html)
- [QEMU microvm](https://www.qemu.org/docs/master/system/i386/microvm.html)
