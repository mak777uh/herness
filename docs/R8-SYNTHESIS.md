# R8 — синтез пяти ответов и развилки

**Дата:** 17.11.2026. **Снимок кода:** `c63f3b8` (его открывали A, D и E; B и C
работали только по брифу). **HEAD при записи:** `04e8b31`.

**Вход:** пять сырых ответов R8, сохранённых байт-в-байт в
[`docs/research/external/`](research/external/README.md):
[A](research/external/2026-11-17-R8-answer-A.txt),
[B](research/external/2026-11-17-R8-answer-B.txt),
[C](research/external/2026-11-17-R8-answer-C.txt),
[D](research/external/2026-11-17-R8-answer-D.md),
[E](research/external/2026-11-17-R8-answer-E.txt). Метки A–E — порядок вложений
владельца, а не самоидентификация моделей.

**Статус.** Это разбор рекомендаций внешних моделей, а не решения владельца и не
approval. Решения Q11–Q18, F04 и A01 принимает владелец. Код, `policy.json`,
`registry.jsonl`, схема `tool-card-v1`, словарь отказов и пре-регистрация в этом круге
**не менялись**. Совпадение нескольких ответов не является согласованием: это только
сужение развилки. Там, где ответ ссылается на собственный прогон, это помечено как
«по ответу»; независимо такие прогоны не повторялись.

---

## 0. Как читать этот документ

Пометки:

- **FACT** — проверено по репозиторию чтением или read-only командой; команда и
  результат указаны.
- **FACT-CODE** — следствие чтения кода, отдельного прогона нет.
- **CLAIM** — утверждение ответа, независимо не проверенное.
- **РЕКОМЕНДАЦИЯ** — предложение агента; владелец может его отклонить.
- **РАЗВИЛКА** — выбор, который нельзя «усреднить»: варианты меняют контракт,
  evidence или TCB.

Прочитаны все пять ответов целиком. Независимо проверены:

- `lab/tools/policy.json` — 19 правил; шесть `implied`; четыре правила с `!`;
  пять названных deny отсутствуют в Rust, шестое (`net-deny-fs`) присутствует;
- `core-rs/src/loopmod.rs` — `POLICY` (14 правил), `policy_allows`, `resource_matches`,
  `resource_of`, `resolve_in`, `tool_read_in`, `tool_search_in`, `tool_list_in`,
  `tool_write_in`, `write_beneath`, `tool_seal`, `tool_netprobe`, `tool_net`,
  `run_tool_g`, `KNOWN_TOOLS`, лимиты;
- `lab/tools/registry.jsonl` — шесть записей, все `version: 3`, все
  `status: "active"`, включая `search`; `net` в registry отсутствует;
- `lab/tools/cards/head.json` и `lab/tools/drafts/head-v1.draft.json` — две разные
  карточки `head` в разных форматах;
- `lab/prereg/HEAD-SLICE-R1.json` — `closed: false`, восемь критических контролей,
  критерий «все 8 отвергнуты точным кодом»;
- `lab/fixtures/model_visible/head-slice.txt` — 471 Б, 10 строк, длины с LF
  `41, 46, 57, 53, 46, 60, 58, 40, 46, 24`, первые три строки 144 Б, вторая
  заканчивается на байте 87, SHA-256
  `b5157f948c0833f80ac96ad64916c93d747e07df253801dfcd5674e59ce76850`;
- `bin/refusal_codes.py` — версия 2, 23 кода; ни одного из новых кодов R8 там нет;
- `docs/CONSTITUTION-v0-2026-11-16.md` — K11 не применяется к native, K1–K10
  применяются; native-инструменты не становятся «доверенными» от того, что они
  встроены.

Не проверены и не выдаются за факт: прогоны QEMU/KVM, `KVM_RUN`, ptrace, seccomp,
Landlock; JCS/Ed25519/SSHSIG-векторы; сборки и репро D/E; точные версии QEMU и ядра;
поведение `memfd`/`execveat` на этой машине; Windows ACL и службы; воспроизводимость
«девяти мутантов» и «73 файлов» корпуса. Это остаётся `UNVERIFIED` до отдельных
измерений.

---

## 1. Пять ответов: кто, что проверял, главный вывод

| | файл | размер | доступ к репозиторию | главный вывод |
|---|---|---:|---|---|
| **A** | `2026-11-17-R8-answer-A.txt` | 65 172 Б | открывал снимок `c63f3b8`, читал код и конфиги; средняя часть кода — `FACT-CROSS` | полный Rust-валидатор на promoter; runtime — тонкий слой V02/V04/V05/V06/V12 + admission/digest; WSL2+KVM `microvm`; ptrace; SSHSIG; пять native `needs_revalidation`; карточный пилот 20/20/20 |
| **B** | `2026-11-17-R8-answer-B.txt` | 62 585 Б | репозиторий не открывал; факты только из брифа | один Rust-валидатор вызывается дважды (приём и каждая загрузка), C01–C12; WSL2+KVM `q35`; ptrace; SSHSIG; `read`/`list` — `needs_revalidation`, `write`/`seal`/`netprobe` — `quarantined`; карточный пилот 12/16 |
| **C** | `2026-11-17-R8-answer-C.txt` | 54 519 Б | ссылки не открывал; факты из брифа | один Rust-крейт на приёме и при каждой загрузке, CV-01–CV-13; WSL2+KVM `q35`, `microvm` — отдельный профиль; отказы ядра + канарейки; raw Ed25519 + `K_rev`; все шесть native `quarantined`; карточный пилот 12/24 |
| **D** | `2026-11-17-R8-answer-D.md` | 70 034 Б | снимок `c63f3b8`, метки FACT/ASSUMPTION/RECOMMENDATION; в тексте есть иностранные токены и самоисправления | полная семантика один раз на promoter, runtime — только digest; **Windows QEMU `-accel whpx -M microvm`** (главный выброс); seccomp+cgroup+канарейки; SSHSIG; все шесть native `quarantined`; кодовый пилот на двух шаблонах; строка 6 S02 — `ok`, что противоречит пре-регистрации |
| **E** | `2026-11-17-R8-answer-E.txt` | 72 409 Б | открывал снимок `c63f3b8`, читал код; заявляет `NOT READY` | полный host-валидатор + тонкий runtime; WSL2+KVM `microvm`; seccomp TRACE + ptrace; raw Ed25519 + узкий recovery; все шесть native `quarantined`; кодовый пилот 20/24; явно говорит, что цепочка пока не работает |

**Главный вывод, с которым согласны A, C и E, а B и D не опровергают:**
на снимке `c63f3b8` нет работающей проверяемой вертикали. Есть схема, черновик
карточки, пре-регистрация, registry с ложным `active` и набор решений, но нет
Rust-среза `file_read_stream`, admission, комнаты с доказанным `KVM_RUN`,
promoter и генератора. E формулирует это как `NOT READY`; A — как «FACT-CROSS,
цепочка не проверена»; C — как «контракт не исполнялся». Это не приговор
архитектуре, а описание состояния.

---

## 2. В чём пять ответов согласны

1. **Канон семантики карточки — Rust, Python ненормативен.** Все пять оставляют
   Python (`card_atoms.py`, `tool_card.py`) линтом, генератором векторов или
   dev-удобством. Python не выдаёт `schema_valid`, `admitted` или `active`, не
   подписывает и не разрешает запуск. F-вариант «Python + receipt» не выбран
   никем.
2. **Admission привязан к точным байтам, а не к пути или «красивому JSON».**
   JCS (RFC 8785), domain separation, detached signature, SHA-256 по card/source/
   binary/template/policy/room/schema, проверка на хосте до запуска. Один
   изменённый байт карточки или бинаря — отказ, а не предупреждение.
3. **`file_read_stream` — сырые байты из FD с жёстким потолком.** `CHUNK=4096`
   у всех; `max_bytes_read` — потолок безопасности, `line_count` — лимит API;
   `read_to_string` и `BufReader::take` не годятся; за бюджетом не читается ни
   один байт; частичная строка не выдаётся; `truncated` и `stop_reason`
   обязательны; невалидный UTF-8 — отказ, а не замена на U+FFFD.
4. **EOF доказывается только `read()==0` в пределах бюджета.** `fstat.size` —
   диагностика или снимок, но не истина EOF; зонд на один байт сверх cap
   запрещён. C предлагает `fstat`-снимок как истину — это расхождение, а не
   согласие.
5. **`cap` меньше первой полной строки — не успешный пустой ответ.** Четыре из
   пяти (A, B, C, E) требуют отказа `K4_RESOURCE_LIMIT`; D говорит `ok, 0 строк`.
   Это прямое расхождение с критическим контролем `HEAD-SLICE-R1`.
6. **Комната — WSL2 + KVM, без сети и host mounts, один ускоритель без
   fallback.** Четыре из пяти (A, B, C, E) выбирают WSL2+KVM; D выбирает
   Windows WHPX и откладывает WSL. Все требуют `-nic none`, `-nodefaults`/
   `-no-user-config`, отсутствие 9p/virtiofs, доказательство ускорителя и
   digest QEMU/ядра/initramfs. TCG — только симуляция, не security-граница.
7. **Наблюдение — измерение, а не доказательство.** Никто не выдаёт
   `observed_code_effects ⊆ card_effects` за доказательство для произвольного
   кода. `observed_independent` в v0 не заявляется никем. «Нет событий» — не
   зелёный; слепой монитор обязан дать провал; self-report инструмента не
   считается независимым.
8. **Один путь допуска, recovery не подписывает admission.** Owner-ключ
   подписывает admission; offline backup восстанавливает тот же ключ; recovery,
   если он есть, может отзывать и повышать `min_epoch`, но не вводить новые
   ключи и не подписывать допуск. Потеря ключа — fail-closed, а не «второй
   путь».
9. **`active` — производный предикат, а не хранимое поле.** Источник истины —
   append-only журнал событий/манифестов; указатель — кэш, который
   перепроверяется; генератор пишет только в candidate inbox; registry пишет
   только promoter; указатель и журнал — вне агентского дерева; у каждого tool
   свой `seq`.
10. **K11 не применяется к native, но `active` у них не восстанавливается
    автоматически.** Конституция освобождает шесть встроенных инструментов от
    K11; K1–K10 остаются. Текущий registry со шестью `status:"active"` — не
    доказательство. `search` не активируется: Q1/Q8 уже отвергли его в первом
    срезе.
11. **Порядок отказов: K11 первым, K6 до K4, все нарушения считаются, модель
    получает один primary.** Сырой путь вне корня не логируется; класс данных
    не запрашивается для пути вне корня; detail не несёт содержимого. Новые
    коды для отсутствующего файла, не-regular и невалидного UTF-8 нужны всем;
    переиспользовать `K6_DATA_CLASS_UNKNOWN` для UTF-8 нельзя.
12. **Генератор — только после зелёного ручного `head`.** Held-out хешируется до
    первого запуска; пороги фиксируются до данных; авто-approval нет; `3/n` —
    инженерный gate, не статистическое доказательство. `K9_proven` в v0
    запрещён; `admitted` не значит «безопасен».

---

## 3. Где расходятся: Q11–Q18, F04, A01, AUDIT

### 3.1. R8-Q1 / Q11 — канон карточки и runtime-роль

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| канон | Rust-валидатор на promoter | один Rust-валидатор | Rust-крейт `card-check` | полная семантика один раз на promoter | Rust-библиотека `herness-card-validator` |
| runtime | тонкий слой V02, V04, V05, V06, V12 + admission/digest | **полная** проверка при каждой загрузке | **полная** проверка при каждой загрузке | только digest, семантику не повторяет | тонкий admission/digest, без полной семантики |
| Python | векторы, линт, миграционный оракул | векторы | вторая реализация, затем выводится | dev-only | линт/векторы |
| правила | V01–V14, ~73 файла | C01–C12 | CV-01–CV-13 | V01–V10 | C01–C11, 40 положительных + 80 мутантов |
| подмена card | K11 `card_digest_mismatch` | K11 | `K11_DIGEST_MISMATCH` (v3) | digest mismatch | K11 |

**Согласие:** полная семантика должна быть на хосте/promoter; runtime обязан
проверить admission и точные байты; Python не решает. **Развилка:** полная
перепроверка при каждой загрузке (B, C) против тонкого слоя (A, E) против
только digest (D). Полная перепроверка дороже и добавляет версию валидатора в
TCB, но ловит ошибочную интерпретацию карточки. Только digest (D) ловит
подмену файла, но не семантический дрейф; A прямо называет это риском.
Тонкий слой (A, E) — компромисс, но требует, чтобы «тонкие» правила были
действительно эквивалентны полным; это надо доказывать дифференциальными
тестами.

**Совместимость:** `tool-card-v1` — черновик (Q2). Пока владелец не утвердит
схему как действующую, V/C-правила применяются только к draft-пайплайну;
старый валидатор не ломается. A и E это фиксируют, B/C/D — нет.

### 3.2. R8-Q2 / Q12 — одна таблица `file_read_stream`

Согласовано: `CHUNK=4096`; сырой `read`; `cap` — жёсткий потолок; EOF только
`read()==0`; частичная строка не выдаётся; `truncated`/`stop_reason` обязательны;
`line_count=0` — `S1_SCHEMA` до I/O; `output_cap` — четвёртая причина остановки.
Расходятся пять осей:

1. **Что такое `bytes_read`.** A и C: байты до конца последней выданной строки
   (эмитированный префикс); B: логический префикс, при `byte_cap` равен `cap`;
   D: байты, полученные из FD, включая read-ahead; E: два счётчика
   (`bytes_read` — получено, `bytes_consumed` — позиция парсера). Это не
   косметика: от определения зависят инварианты и негативные тесты.
2. **Когда `truncated=false`.** B — только при `lines_complete`; A/C/D/E — при
   доказанном EOF; A консервативно ставит `true` на точной границе `cap=size`,
   B/C/D/E — `false` (C — по `fstat`-снимку). C's `fstat`-снимок как истина EOF
   отвергнут A/B/D/E: растущий файл даёт ложный EOF.
3. **CRLF.** A/B/C сохраняют CR; D и E удаляют CR из логического содержимого,
   но считают его в байтах. Это противоречит байтовой верности: D сам заявляет
   «CR — обычный байт», а затем снимает его при выдаче.
4. **Переполнение `output_bytes`.** A/B/C/D — штатная остановка `output_cap`
   (`ok`, целые строки, `truncated=true`); E — атомарный отказ `K4`.
5. **Новые коды.** A: `S10_NOT_FOUND`, `S11_NOT_REGULAR`, `S12_ENCODING`,
   `S13_TOOL_INACTIVE`, `S14_ALREADY_EXISTS`; B: `IO_NOT_FOUND`,
   `IO_NOT_REGULAR`, `DATA_NOT_UTF8`; C: `S8_ENCODING`, `S9_NOT_REGULAR`,
   `S10_FILE_CHANGED`, `S11_NOT_FOUND`, `K11_DIGEST_MISMATCH`; D:
   `S2_INPUT_MISSING`, `S2_CONTENT_ENCODING`, `S2_INPUT_TYPE`; E:
   `K1_SCOPE_VIOLATION`, `K2_SCOPE_VIOLATION`, `FS_PATH_NOT_FOUND`,
   `FS_OBJECT_TYPE_UNSUPPORTED`, `S2_ENCODING_INVALID`,
   `S2_SEARCH_ENTRY_SKIPPED`, `S1_TOOL_NOT_ACTIVE`.

**Матрица ключевых строк** (формат: `строк / bytes_read / truncated / stop или
код`; у E в скобках — `bytes_consumed`):

| # | A | B | C | D | E |
|---|---|---|---|---|---|
| 1 `N=3, cap=4096` | 3/144/да/line_count | 3/144/нет/lines_complete | 3/144/да/line_limit | 3/144/да/line_count | 3/471 (144)/да/line_limit |
| 2 `N=200, cap=64` | 1/41/да/byte_cap | 1/64/да/byte_cap | 1/41/да/byte_cap | 1/64/да/byte_cap | 1/64 (64)/да/byte_cap |
| 4 `N=3, cap=144` | 3/144/да/line_count | 3/144/нет/lines_complete | 3/144/да/line_limit | 3/144/да/line_count | 3/144 (144)/да/line_limit |
| 5 `N=10, cap=471` | 10/471/да/line_count | 10/471/нет/lines_complete | 10/471/нет/eof | 10/471/нет/eof | 10/471 (471)/нет/eof_at_open_size |
| 6 `N=200, cap=40` | отказ K4 | отказ K4 | отказ K4 | **ok, 0/40/да/byte_cap** | отказ K4 (+truncated) |
| 7 `N=200, cap=42` | 1/41/да/byte_cap | 1/42/да/byte_cap | 1/41/да/byte_cap | 1/42/да/byte_cap | 1/42 (42)/да/byte_cap |
| 8 `N=200, cap=87` | 2/87/да/byte_cap | 2/87/да/byte_cap | 2/87/да/byte_cap | 2/87/да/byte_cap | 2/87 (87)/да/byte_cap |
| 9 без финального LF | 3/144/да/line_count | 3/144/нет/lines_complete | **как записана = строке 1; C предлагает 10/470/нет/eof** | 3/144/да/line_count | 3/470 (144)/да/line_limit |
| 10 CRLF | 10/481/нет/eof, CR сохранён | 10/481/нет/eof, CR сохранён | 10/481/нет/eof, CR сохранён | 10/481/нет/eof, **CR снят** | 10/481 (481)/нет/eof, **CR снят** |
| 11 invalid UTF-8 | `S12_ENCODING` | `DATA_NOT_UTF8` | `S8_ENCODING` | `S2_CONTENT_ENCODING` (bytes 49) | `S2_ENCODING_INVALID` |
| 12 нет/каталог/symlink | `S10` / `S11` / `S6` | `IO_NOT_FOUND` / `IO_NOT_REGULAR` / K1 | `S11` / `S9` / K1 | `S2_ARTIFACT_MISSING` / `S6` / `S6` | `FS_PATH_NOT_FOUND` / `FS_OBJECT_TYPE_UNSUPPORTED` / `K1_SCOPE_VIOLATION` |
| 13 output > 8192 | 119/7616/да/output_cap | k≥1/output_cap; k=0 K4 | output_cap | output_cap | **K4** |
| 14 `line_count=0` | `S1_SCHEMA` | `S1_SCHEMA` | `S1_SCHEMA` | `S1_SCHEMA` | `S1_SCHEMA` |

**Строка 6 — критическая.** `HEAD-SLICE-R1` содержит контроль «`max_bytes_read`
меньше первой строки»; критерий — отказ точным кодом. D даёт `ok, 0 строк`,
что делает этот контроль «принятым» и одновременно неотличимым от пустого
файла. Принять D нельзя без явной поправки пре-регистрации **до** данных; это
не стилистическое расхождение.

**Строка 9 у C.** В таблице C она совпадает со строкой 1; C это замечает и
предлагает заменить её на `10/470/нет/eof`. Как записано — невалидна; как
предложение — совпадает с B по `eof`, но расходится с A/E по `bytes_read`.

**Строка 13.** A даёт 119 строк и 7616 Б при frame 8175 Б; это арифметически
возможно, но зависит от формата кадра. B/C/D дают `output_cap` без отказа; E
требует `K4`. Для v0 безопаснее не отдавать частичный JSON; вопрос лишь в том,
считать ли остановку отказом или успехом с `truncated=true`.

**Словарь.** Ни один из новых кодов не существует в v2. Любой v3 — поправка
владельца, аддитивная, без переименования v2. Draft-карточка `head` ожидает
`S6_CLOSURE_BREACH` для outside-root; если вводить `K1_SCOPE_VIOLATION`, пример
карточки нужно править одновременно. Это ограничение важнее названий кодов.

### 3.3. R8-Q3 / Q13 — комната, команда и доказательства

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| ускоритель | WSL2+KVM | WSL2+KVM | WSL2+KVM | **Windows QEMU WHPX** | WSL2+KVM |
| машина | `microvm` | `q35` | `q35` по умолчанию, `microvm` — отдельный профиль | `microvm` | `microvm` |
| fixture | initramfs, RO | initramfs | initramfs | отдельный RO-образ + `-add-fd`/virtio-blk + root drive | initramfs, RO |
| seccomp | доверенный guest launcher до candidate | в `main` шаблона после открытия fd | runner после открытия fixture-fd | в первой строке tool | доверенный guest launcher до candidate |
| процессы | cgroup `pids.max=2` (supervisor + tool) | `RLIMIT_NPROC=1` | `RLIMIT_NPROC`/cgroup | cgroup `pids.max=1` | cgroup `pids.max=1`, supervisor вне |
| KVM proof | QMP `query-kvm` + fd + `KVM_RUN` | QMP + `/dev/kvm` | QMP + `/dev/kvm` | отложен, WHPX основной | QMP + fd + `KVM_RUN`; без него срез закрыт |

**Согласие:** WSL2+KVM, без сети и host mounts, один `-accel kvm`, никакого
fallback на TCG/WHPX в security-профиле; seccomp ставит доверенный компонент,
а не `pre_exec` (в этом снимке `pre_exec` даёт `ENOSYS`); лимит процессов — не
«надежда на RLIMIT», а cgroup/RLIMIT с отрицательным контролем.
**Развилка:** D выносит WHPX в основной путь и откладывает KVM; A/C/E считают
WHPX недопустимым fallback; B/C выбирают `q35`, A/E — `microvm`. `microvm`
поддерживается QEMU как security-машина по документации (A), но C не смог это
подтвердить; B тоже не проверял. Пока нет фактического `KVM_RUN`, `microvm`
и `q35` — конкурирующие профили, а не факт.

**Про `CONFIG_NET`.** A/B фиксируют, что seccomp-фильтр требует `CONFIG_NET`;
без него установка фильтра может дать `EINVAL`. Это не деталь: «сеть выключена
на уровне QEMU» и «сеть выключена в ядре» — разные вещи; для seccomp нужен
`CONFIG_NET=y`, а `CONFIG_INET=n` — отдельная настройка. Проверять надо на
конкретном ядре, а не по памяти.

### 3.4. R8-Q4 / Q14 — наблюдение и уровень притязания

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| механизм | seccomp TRACE + ptrace в госте | seccomp TRACE + ptrace | отказы ядра + канарейки | seccomp + cgroup + канарейки | seccomp TRACE + ptrace |
| claim | `observed_in_guest` + `enforced_by_kernel` | `observed_in_guest` | `enforced_by_kernel` / `canary_verified` | `enforced_by_kernel` / `canary_verified` / `observed_within_card` | `observed_in_guest` |
| независимая трасса | нет | нет | нет | нет | нет |
| «нет событий» | провал | провал | провал | провал | провал |

**Согласие:** `observed_independent` в v0 не заявляется; «нет событий» не
зелёный; слепой монитор обязан дать `S7_GATE_BLIND` или `observation_invalid`;
self-report инструмента не считается независимым. **Развилка:** TRACE+ptrace
даёт событие до исполнения syscall и позволяет утверждать `observed_in_guest`,
но добавляет ptrace-supervisor в TCB и требует обработки гонок. Отказы ядра +
канарейки проще, но утверждают меньше: только `enforced_by_kernel` и
`canary_verified`, без «мы видели все эффекты». C в этом варианте заявляет
`syscall_nr` из `wait status` — это не следует из `SECCOMP_RET_KILL` без
TRACE/SIGSYS; утверждение нужно проверить или снять.

### 3.5. R8-Q5 / Q15 — ключ, подпись, recovery, trust anchor

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| подпись | SSHSIG, ns `herness-admission-v1`, sha512 | SSHSIG | raw Ed25519 + domain separation | SSHSIG | raw Ed25519 |
| recovery | нет | нет; локальный deny-only без подписи | `K_root` offline + `K_rev` (только revoke/quarantine) | нет | operational + backup + узкий recovery (revoke/raise `min_epoch`) |
| anchor | Windows + зеркало WSL | не фиксирует | WSL ext4 | не фиксирует | Windows, ACL службы |
| анти-откат | epoch/seq/prev/revocation | epoch/seq/prev, deny-list | epoch/seq/prev | epoch/seq/prev | epoch/seq/prev + внешний high-water mark (не проверен) |

**Согласие:** один owner-путь к admission; recovery не подписывает admission и
не вводит ключи; offline owner; anti-rollback; отзыв обязателен; компрометация
host administrator — вне модели. **Развилка:** SSHSIG (A/B/D) против raw
Ed25519 (C/E); наличие recovery (C/E) против его отсутствия (A/B/D); anchor на
Windows против WSL. `K_rev`/recovery, который умеет только отзывать и повышать
`min_epoch`, — наименее опасный компромисс, если владелец хочет восстановление
после потери ключа. Любой recovery, который может добавить ключ или подписать
admission, восстанавливает второй путь допуска и должен быть отвергнут.

### 3.6. R8-Q6 / Q18 — производный `active`, legacy-шесть и `search`

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| `read`/`list` | `needs_revalidation` | `needs_revalidation` | `quarantined` | `quarantined` | `quarantined` |
| `write` | `needs_revalidation` | `quarantined` | `quarantined` | `quarantined` | `quarantined` |
| `seal`/`netprobe` | `needs_revalidation` | `quarantined` | `quarantined` | `quarantined` | `quarantined` |
| `search` | rejected | rejected | rejected | rejected | rejected |
| legacy-loop | с баннером | не фиксирует | только диагностика | не фиксирует | не фиксирует |

**Согласие:** заморозить текущий registry как исторический снимок; записать
genesis event; `active` вычислять; журнал append-only; писать может только
promoter; указатель и журнал — вне агентского дерева; `seq` на tool; K11 к
native не применять; `search` не активировать; при изменении digest —
`needs_revalidation`/`stale`. **Развилка:** `needs_revalidation` (A, B для
read/list) против `quarantined` (C/D/E). `quarantined` честнее: у нас нет
revalidation-событий, а `status:"active"` — ложное утверждение. `needs_revalidation`
допускает запуск legacy-loop до проверки, что противоречит «инструмент
недоверенный». `net` отсутствует в registry, но есть в `KNOWN_TOOLS`; его нужно
учесть как отдельный bridge path, выключенный в offline `head`-профиле, а не
потерять.

### 3.7. R8-Q7 / Q16 — минимальный пилот генератора

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| пилот | карточный | карточный | карточный | **кодовый, 2 шаблона** | **кодовый, 1 шаблон** |
| spec | 20 = 16 + 4 held-out | 12 = 8 + 4 | 12 = 8 + 4 | 12 = 6/шаблон + 4 held-out | 20 = 12 + 8 |
| мутанты | 20 | 16 | 24 | 14 | 24 = 16 критических + 8 |
| повторы | 3 | 3 | 3 | 3 | 3 |
| время владельца | ~3 ч | ~2 ч | не оценивает | 20–30 ч | 3–5 ч |

**Согласие:** никакого авто-approval; held-out хешируется до первого запуска;
пороги фиксируются до данных; пилот только после ручного зелёного `head`;
`3/n` — инженерный gate, не статистика. При нуле ошибок верхняя 95%-граница
примерно `3/n`: ~15% при `n=20`, ~12.5% при `n=24`. **Развилка:** карточный
пилот (A/B/C) проверяет только генерацию карточки, а не кода; кодовый (D/E)
проверяет вертикаль, но дороже. D предлагает два шаблона — это расширяет
первый срез за «один kind — один шаблон» (Q1) и добавляет независимую
переменную; E — один шаблон, что ближе к принятому Q1. Карточный пилот может
быть дешёвым pre-pilot, но он не отвечает на вопрос «умеет ли harness
генерировать код».

### 3.8. R8-Q8 / Q17 — приоритет отказов и словарь

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| порядок | K11 → S6 → K6_SECRET → K6_UNKNOWN → K4 → S10/S11/S12 → S1 | K11 → S1 → K1 → S6 → K6_EGRESS → K6_UNKNOWN → IO → K4 → UTF-8 | K11 → S1 → K1 → S11 → S9 → K6 → K4 → S8 → S10 | K11 → S1 → scope → K6 → S2_ENCODING → S6 → K4 → output_cap | K11 → S1 → K1/K2 → K6 → S6 → K4 → FS/encoding |
| S1 | последним | вторым | вторым | вторым | вторым |
| S6 vs K6 | S6 выше | S6 выше | K1 выше, S6 нет | S6 после K6/encoding | S6 после K6 |
| output overflow | `output_cap`, ok | `output_cap`, ok; k=0 K4 | `output_cap`, ok | `output_cap`, ok | **K4** |
| новые коды | S10–S14 | IO_*, DATA_NOT_UTF8 | S8–S11, K11_DIGEST | S2_* | K1/K2/FS/S2/S1_TOOL |

**Согласие:** K11 первым; K6 до K4; для пути вне корня класс не запрашивается;
все нарушения считаются, модель получает один primary; сырой путь вне корня не
логируется; UTF-8 — отдельный код, не K6; отсутствующий файл и не-regular —
отдельные коды; `output_cap` — не утечка, а остановка (кроме E, который
требует K4). **Развилка:** S1 вторым (B/C/D/E) или последним (A); S6 выше K6
(A/B) или ниже (D/E); вводить ли `K1_SCOPE_VIOLATION` (B/C/E) или сохранять
`S6_CLOSURE_BREACH` для scope (A, draft-карточка). **Проблема
исполнимости:** A ставит K4 перед `S10/S11/S12`, но если файла нет, K4
невычислим; E ставит FS-коды после K4 — та же проблема. Порядок должен быть
исполнимым: schema → scope → class → open/fstat → объектные ошибки → K4 →
encoding → output. Иначе «приоритет» превращается в список кодов, а не в
алгоритм.

**Совместимость с draft.** Пример `head-v1.draft.json` для outside-root ожидает
`S6_CLOSURE_BREACH`. Если владелец выбирает `K1_SCOPE_VIOLATION`, нужно
одновременно поправить пример и, возможно, семантику S6. Это не косметика:
иначе карточка и runtime говорят на разных языках.

### 3.9. R8-Q9 / F04 — лестница статусов и две оси

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| evidence | none → schema → semantic → policy → conformance → room_observed | declared → schema → semantic → policy → room_ran → observed_in_guest | declared → schema → semantic → policy → room_run_passed | none → schema → policy → room_observed | declared → schema → semantic → policy → room_run_passed → observed_in_guest |
| authority | none → candidate → admitted → revoked/expired | none / candidate / K11_admitted / revoked | none / admitted / revoked / quarantined | `admitted: bool` | not_admitted → owner_signed → admitted_inactive → activated; terminal revoked/expired/needs_revalidation/quarantined |
| admitted без runtime | нет (требует evidence) | **запрещено в v0** | да, но `active` требует room_run | да | да, как `admitted_inactive` |
| room без admission | да | да | да | да | да, только quarantine |
| observed обязателен | для `active` | для admission | нет в v0 | нет | для `activated` |

**Согласие:** две оси; `admitted` не значит «безопасен»; `K9_proven` запрещён;
закрытые enum; изменение digest инвалидирует evidence/authority; статус
вычисляет promoter. **Развилка:** admission требует runtime-evidence (A/B/C)
или нет (D/E); `observed_in_guest` обязателен для active (A/B/E) или нет
(C/D); названия состояний. Для v0 модель E (`admitted_inactive` → `activated`)
лучше разделяет «подпись есть» и «можно запускать»; но она требует, чтобы
`activated` вычислялся, а не хранился.

### 3.10. R8-Q10 / A01 — admission-манифест и точные байты

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| подпись | SSHSIG, ns `herness-admission-v1`, sha512 | SSHSIG | raw Ed25519 `K_root` | SSHSIG | raw Ed25519 |
| поля | A7: card/source/binary/template/deps/toolchain/policy/room/schema/lawset/evidence | плюс `policy_slice_digest`, `constitution_digest`, `journal_prev` | плюс `validator_digest`, `card_effects_digest`, `refusal_dict_*` | базовый набор | базовый набор + `refusal_vocab_sha256` |
| Windows | только хранение, исполнение запрещено | отказ от исполнения admitted | хост не исполняет | **handle + ACL, исполнение** | только хранение |
| runtime bytes | memfd + `F_SEAL_*` + `execveat` | memfd + seals + `execveat` | memfd + seals + `execveat` | memfd/seals; Windows handle | memfd + seals + `execveat` |
| approvals | одна owner-запись | одна | одна | одна | одна |

**Согласие:** JCS, detached signature, exact bytes, SHA-256, domain separation,
host-side promoter, owner offline key, epoch/seq/prev/revocation, evidence
digests, Linux `memfd` + `F_SEAL_*` + `execveat`, `seal`/`netprobe` вне v0.
**Развилка:** SSHSIG (A/B/D) против raw Ed25519 (C/E); Windows handle+ACL (D)
против «не исполнять на Windows» (A/B/C/E); `expires_at` обязателен (A/B/E)
или advisory (C); набор полей. D's Windows-путь противоречит консенсусу и
оставляет path-based loader window; B/C/E прямо отказываются от исполнения
на Windows. Для v0 безопаснее не исполнять candidate на Windows.

### 3.11. R8-Q11 / AUDIT — независимые дефекты и порядок починки

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| источник policy | `policy.json` → codegen | `policy.json` → codegen/include | `include_str` + digest | codegen или `policy_sync.py` | типизированный IR из `policy.json` |
| `!` | отдельный matcher, `implied` — происхождение | явный allow/deny после Q1 | deny-pass до allow | `!` мёртв | `Within`/`Outside`/`Equals`/`NotEquals` |
| первый приоритет | policy drift → `resource_of`/`resolve_in` → write → read → search → admission | write → policy drift → normalize → MAX_READ → search → cards → processes → self-exec → admission | drift → пять deny → write → read → TOCTOU → search → self-exec → processes → cards → admission | drift → read/TOCTOU → write → search → cards → processes → self-exec → admission | search → drift → write → admission → read → processes → cards → search skip |

**Согласие по существу:** `policy.json` — единственный редактируемый источник;
Rust должен получать сгенерированное/проверяемое представление, а не ручную
копию; `!` должен стать реальным matcher или явным deny; `write` — create-new
(`O_EXCL`), нормализация пути до policy-check, `RESOLVE_NO_XDEV`; `read` —
потоковый лимит, а не `read_to_string`; `search` — отключить в v0, а не
чинить обход; две карточки `head` — разные форматы, без fallback;
`max_processes` — применять; `seal`/`netprobe` — вне admitted-пути;
`run_tool_g` — fail-closed по admission; `list` — не терять ошибки; `resolve_in`
— не смешивать path resolution и authorization; `resource_of` — не отображать
путь вне корня в `/mnt/...`. **Развилка:** codegen против sync-скрипта; порядок
P0/P1; чинить ли `search` обход или только отключать. Для v0 «отключить» —
единственное, что соответствует Q1/Q8; «починить обход» — расширение среза.

---

## 4. Проверенные факты репозитория

### 4.1. Policy: 19 против 14, шесть `implied`, четыре `!`

`lab/tools/policy.json` содержит **19** правил. `core-rs/src/loopmod.rs` `POLICY`
содержит **14**. Комментарий над `POLICY` (строка 490) утверждает: «Совпадает с
`lab/tools/policy.json`; расхождение ловит гейт». Фактическое расхождение
означает, что гейт этого не ловит или сравнивает неполно. Это дефект прибора,
а не только policy.

Шесть правил помечены `implied: true`:

- `read-deny-outside` — `file:!/mnt/**`, есть `!`, **нет в Rust**;
- `write-deny-outside` — `file:!/mnt/work/**`, есть `!`, **нет в Rust**;
- `seal-deny-outside` — `file:!/mnt/work/**`, есть `!`, **нет в Rust**;
- `netprobe-deny-other` — `net:!10.0.2.2:8790`, есть `!`, **нет в Rust**;
- `netprobe-deny-fs` — `file:/mnt/**`, **без `!`**, **нет в Rust**;
- `net-deny-fs` — `file:/mnt/**`, **без `!`**, **есть в Rust**.

Отсюда уточнение к брифу R8: фраза «пять `implied` deny с `!`» неточна. Пять
deny отсутствуют в Rust, но `!` есть только у четырёх; шестое implied-правило
(`net-deny-fs`) реализовано, а `netprobe-deny-fs` — нет. `netprobe-deny-other`
содержит `!` после схемы (`net:!...`), а не в начале; наивный prefix-matcher
его не поймает.

`resource_matches` (строки 569–585) обрабатывает только `**` и `*`; `!` не
обрабатывается. Поэтому четыре deny с `!` мертвы в Rust. Для `read` путь вне
корня всё равно отсекается `resolve_in` (`starts_with`), но для `write` и
прямых вызовов `policy_allows` это не так. `policy_allows` реализует
deny-wins/default-deny корректно, если правило совпало; вопрос в том, что
правила с `!` не совпадают.

### 4.2. `write`: policy на ненормализованном пути, `O_TRUNC`, нет `NO_XDEV`

`tool_write_in` (877–895) не вызывает `resolve_in`. Он делает
`resource_of(target, root)`, затем `policy_allows("write","write", resource)`,
затем `write_beneath`. `resource_of` (547–557) не нормализует путь: если
`strip_prefix(root)` не сработал, он берёт весь абсолютный путь и добавляет
`/mnt/`. Для `/mnt/work/../work2/x` `strip_prefix` срабатывает, ресурс
получается `file:/mnt/work/../work2/x`, и `write-allow` (`file:/mnt/work/**`)
совпадает по префиксу. `write_beneath` открывает `work/../work2/x` относительно
`/mnt`; `openat2` разрешает это в `/mnt/work2/x` — **вне объявленного
`/mnt/work/**`**, но внутри корня. Это следствие кода (FACT-CODE); отдельного
прогона нет. Оно не является выходом из комнаты, но нарушает объявленный scope
записи и четырёхстороннюю монотонность.

`write_beneath` (904–937) использует
`O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC`, `RESOLVE_BENEATH |
RESOLVE_NO_SYMLINKS`; `NO_XDEV` отсутствует. `NO_MAGICLINKS` влечётся
`NO_SYMLINKS`, поэтому его отсутствие — не дефект. `O_TRUNC` противоречит
принятому Q1 (`file_write` — create-new, без overwrite). Отсутствие `NO_XDEV`
оставляет переход точки монтирования; в WSL2 это особенно важно из-за drvfs.

### 4.3. `read`: файл целиком, 24 KiB, переполнение одной строкой

`tool_read_in` (821–864): `resolve_in` → `metadata` → `read_to_string` целого
файла; `MAX_READ = 24 * 1024` (409); контракт `read` в `contracts.json` и запись
реестра обещают `output_bytes: 8192`. Проверка `out.len() >= MAX_READ` стоит
**до** добавления следующей строки (842–845), поэтому одна длинная строка может
превысить `MAX_READ`.
`read_to_string` также читает файл целиком до проверки выхода, то есть
`max_bytes_read` карточки не является потолком чтения. Это подтверждает
описание брифа и ответы A/C/D/E.

### 4.4. `search`: молчаливые пропуски и Unicode-баг

`tool_search_in` (625–...) делает `scanned = files.len()` до цикла; в цикле
`metadata`/`read_to_string` ошибки и файлы больше `MAX_FILE` молча
`continue` (660–664). Итог «найдено 0» может означать «всё пропущено».
`search` уже отвергнут Q1/Q8, поэтому чинить обход в v0 не нужно; но
исторический вызов должен быть отключён, а не оставлен как активный.

Дополнительно: в (694–700) `lower_line.find(...)` даёт **байтовую** позицию в
нижнем регистре, а `trimmed[..byte]`/`line[position..]` режут исходную строку
по этой позиции. При Unicode case-folding (например, `İ`, `ß`) позиция может
попасть внутрь UTF-8 символа и вызвать panic. D описывает это как
потенциальный panic; проверено чтением, прогона нет. Это ещё один аргумент
отключить `search` в v0.

### 4.5. `list`: TOCTOU и молчаливые ошибки

`tool_list_in` (776–809) вызывает `resolve_in` дважды (779 и 785), затем
`read_dir(&root)` (786). Между проверкой и открытием путь можно подменить;
защита — только повторная проверка, не fd. Цикл использует
`entries.flatten()` (793), `entry.metadata().ok()` (794) и
`meta.map(...).unwrap_or(0)` (798): ошибка итерации или метаданных выглядит
как обычный элемент/размер 0. Это подтверждает D/E.

### 4.6. `resolve_in` всегда проверяет `read/read`

`resolve_in` (587–611) в конце всегда вызывает
`policy_allows("read","read", &resource)` (607), независимо от вызывающего
инструмента. `list`, `search`, `seal` затем делают собственные проверки.
Это не доказанный обход, но смешение resolution и authorization: смена
read-policy влияет на все инструменты, а «list» не может иметь отдельную
policy-семантику пути. E фиксирует это как отдельный дефект.

### 4.7. Self-exec, процессы, admission, registry

- `tool_seal` (285–319) и `tool_netprobe` (364–...) запускают
  `Command::new(current_exe())`, то есть порождают процесс. Карточка
  `process_spawn: false` и `max_processes: const 1` этому противоречат.
- `run_tool_g` (1085–1101) проверяет только granted-list; admission,
  `active`, digest и room не проверяются. `active` из registry не является
  разрешением на запуск.
- `max_processes` есть в схеме (`const 1`), но runtime его не применяет.
- `registry.jsonl`: шесть записей, все `version: 3`, все `status: "active"`,
  включая `search`. `net` есть в `KNOWN_TOOLS` (7 имён), но отсутствует в
  registry; `tool_net` читает `HS_BRIDGE_TOKEN` из окружения (349–351). Это
  отдельный legacy bridge path, а не «шестой инструмент».
- Две карточки `head`: `lab/tools/cards/head.json` (старый формат) и
  `lab/tools/drafts/head-v1.draft.json` (`tool-card-v1`). Это разные форматы;
  автоматический fallback между ними недопустим.

### 4.8. Фикстура, пре-регистрация, словарь

Фикстура: 471 Б, 10 строк, длины с LF `41, 46, 57, 53, 46, 60, 58, 40, 46, 24`,
кумулятивно `41, 87, 144, 197, 243, 303, 361, 401, 447, 471`; первые три
строки 144 Б; вторая заканчивается на 87; SHA-256
`b5157f948c0833f80ac96ad64916c93d747e07df253801dfcd5674e59ce76850`.
`HEAD-SLICE-R1` открыт (`closed:false`), содержит восемь критических
контролей и критерий «все 8 отвергнуты точным кодом». Строка 6 S02
(`cap` меньше первой строки) — один из них; `ok` из ответа D несовместим с
пре-регистрацией.

Словарь v2: 23 кода; новых кодов R8 в нём нет. Draft `head` для outside-root
ожидает `S6_CLOSURE_BREACH`; это ограничивает переименование scope-кода.
`S2_ARTIFACT_MISSING` в v2 означает отсутствие артефакта, на который
ссылается утверждение, а не отсутствие входного файла; D переиспользует его
некорректно.

---

## 5. Ошибки и внутренние противоречия в ответах

Это не «дискредитация» ответов: сырые тексты остаются как есть. Но принимать
их утверждения без проверки нельзя.

### A

- **S1 последним.** В Q2 A говорит, что `line_count=0` — `S1_SCHEMA` до
  всякого I/O; в Q8 ставит S1 последним. Это внутреннее противоречие. Если S1
  — чистая схема, он должен быть вторым (после K11) или, как минимум, до
  открытия файла.
- **K4 перед объектными ошибками.** В порядке Q8 K4 стоит перед
  `S10/S11/S12`; если файла нет, K4 невычислим. Это список кодов, а не
  исполнимая последовательность.
- **Строка 5 S02.** A консервативно ставит `truncated=true` на точной границе
  `cap=size`; это честно, но это ложноположительный `truncated`, который надо
  явно объявить в контракте.
- **Q3 `microvm` и ядро 6.18.60.** A утверждает, что `microvm` поддерживается
  в security use case, и предлагает проектное ядро 6.18.60 с `CONFIG_NET=y`;
  это не проверено на этой машине. C не смог подтвердить поддержку; B тоже
  не проверял.
- **Q11 пять deny.** A перечисляет пять отсутствующих deny, но не уточняет,
  что `netprobe-deny-fs` без `!`, а `net-deny-fs` уже есть в Rust. Это не
  ошибка вывода, но ошибка точности.

### B

- **`truncated=false` на строках 1, 4 и 9.** B привязывает `truncated` к
  `lines_complete`, а не к «продолжение известно/неопровержимо». Это
  защитимо, но это другой контракт, чем у A/C/D/E; его нельзя смешивать с
  их таблицей.
- **`bytes_read` — логический префикс.** При `byte_cap` B возвращает `cap`,
  даже если последняя строка не выдана; A/C возвращают конец последней
  выданной строки. Это меняет инвариант «выдано ≤ bytes_read» и должно быть
  выбрано явно.
- **`q35`.** B выбирает `q35` и не проверяет `microvm`; это не ошибка, но
  расходится с A/E и добавляет PCI/ACPI в TCB.
- **`RLIMIT_NPROC=1`.** Если supervisor и tool делят UID, лимит может
  блокировать инфраструктуру; нужен отдельный UID/cgroup и отрицательный
  контроль. B это не уточняет.
- **Нет доступа к репозиторию.** Все факты B — из брифа; он сам это
  маркирует. Его числа и имена кодов нельзя считать проверенными.

### C

- **Строка 9 невалидна как записана.** C это признаёт и предлагает замену;
  в матрице её нельзя использовать без пометки.
- **`fstat`-снимок как истина EOF.** C считает `consumed == size` доказанным
  EOF; A/B/D/E возражают: файл может вырасти после снимка, и тогда `eof`
  ложный. Для read-only initramfs это может быть приемлемо, но это должно
  быть явно оговорено, а не выдано за общий контракт.
- **`syscall_nr` из `wait status`.** C в Q4 заявляет номер syscall при
  `SECCOMP_RET_KILL`; без TRACE/SIGSYS wait status даёт сигнал, а не номер.
  Утверждение нужно проверить или снять.
- **`q35` и `microvm`.** C не подтвердил поддержку `microvm` и выбрал `q35`;
  это осторожно, но расходится с A/E. `microvm` как отдельный профиль —
  разумная оговорка, а не факт.
- **Нет `observed_in_guest` в v0.** C оставляет только `room_run_passed`;
  это ослабляет claim по сравнению с A/B/E. Если владелец хочет
  `observed_in_guest`, C's лестница недостаточна.

### D

D — самый рискованный текст: в нём есть иностранные токены, самоисправления
и несколько прямых противоречий. Это не делает все его идеи ложными, но
требует построчной проверки.

- **WHPX как основной путь.** D выбирает Windows QEMU `-accel whpx -M microvm`
  и откладывает WSL/KVM. A/B/C/E выбирают WSL2+KVM; R7 тоже сходился на
  WSL2+KVM. WHPX — не «ещё один ускоритель»: это другой TCB, другие
  доказательства и другой профиль. Для security-run v0 это главный выброс.
- **Строка 6 S02 — `ok`.** Прямо противоречит критическому контролю
  `HEAD-SLICE-R1`. Принять нельзя без поправки пре-регистрации до данных.
- **CR снимается при выдаче.** D говорит «CR — обычный байт», но в строке 10
  удаляет CR из содержимого, сохраняя 481 Б. Это противоречие байтовой
  верности; A/B/C сохраняют CR.
- **Строка 11 — `bytes_read=49`.** При невалидном UTF-8 на байте 50 D
  показывает 49; это не согласуется с его же определением «получено из FD»
  и с остальными ответами (471/50/87). Нужен пересчёт.
- **`S6` для каталога/FIFO.** D использует `S6_CLOSURE_BREACH` для
  not-regular; это смешивает closure breach с типом объекта. B/C/E вводят
  отдельный код; A — `S11_NOT_REGULAR`. Смысл S6 в v2 — выход за замыкание,
  а не «каталог вместо файла».
- **Порядок с encoding до S6.** D ставит `S2_CONTENT_ENCODING` перед
  `S6_CLOSURE_BREACH`; это требует чтения содержимого до проверки замыкания,
  что противоречит его же правилу «не читать после барьера».
- **Windows handle+ACL.** D разрешает исполнение admitted-инструмента на
  Windows через handle+ACL; B/C/E прямо отказываются, A — только хранение.
  `CreateProcessW` не принимает image handle, поэтому остаётся path-based
  loader window. Для v0 это не тот путь, который можно назвать доказанным.
- **Два шаблона в пилоте.** D предлагает кодовый пилот на двух шаблонах;
  это расширяет принятый Q1 «один срез — один шаблон» и добавляет
  независимую переменную до первого зелёного среза.
- **Иностранные токены и самоисправления.** В тексте встречаются
  `文件読ется`, `émission`, `inside`, `existe`, `自己的`, `ceremonie`,
  `propriétaire` и т.п. Сырой файл сохраняется байт-в-байт; в синтезе
  использовать только проверяемые фрагменты.

### E

- **Строка 6: отказ K4 и `truncated=true` одновременно.** В кадре отказа
  поля успеха отсутствуют; `truncated` в отказе — лишнее/противоречивое поле.
  Нужно выбрать: либо отказ без полей успеха, либо ok с `truncated`.
- **Строка 13: `K4` на output overflow.** A/B/C/D считают `output_cap`
  штатной остановкой; E — атомарным отказом. Это развилка, а не ошибка,
  но её нельзя смешивать с «K4 — это только read cap».
- **`search` и Q8.** E говорит, что `search` «уже отвергнут Q8»; фактически
  он отвергнут Q1/Q8 в смысле первого среза, а Q8 — это порядок отказов.
  Мелочь, но показывает, что ссылки на решения нужно проверять.
- **Q11 «нельзя фиксировать до решения R6 Q11–Q18».** E называет решения
  «R6 Q11–Q18»; это решения R8 (или решения владельца Q11–Q18). Не влияет
  на суть, но нумерация кругов путается.

### Общая ошибка всех пяти

Никто не смог независимо проверить `KVM_RUN` на этой машине; никто не
прогнал JCS/Ed25519/SSHSIG-векторы; никто не собрал Rust-срез. Поэтому
«консенсус» здесь — консенсус предложений, а не измерений. Это надо
повторять в каждом отчёте.

---

## 6. Решения владельца

Ниже — вопросы, которые нельзя решить «средним» между ответами. Для каждого
дана **рекомендация агента**; это не решение и не approval.

| id | вопрос | рекомендация | почему | что блокирует |
|---|---|---|---|---|
| **Q11** | Канон карточки и runtime-роль | Полная семантика на promoter; runtime — admission + exact bytes + тонкий набор V02/V04/V05/V06/V12 | Ловит подмену и не раздувает TCB двумя полными валидаторами; тонкий слой проверяется дифференциально | Rust-валидатор, admission, `head` |
| **Q12** | Точная таблица S02 | `CHUNK=4096`; `bytes_read` — конец последней выданной строки (диагностический `bytes_received` — в лог); EOF только `read()==0`; `truncated=true` при line/byte/output limit, `false` только при доказанном EOF; `cap<первой строки` → K4; CR сохраняется; output overflow → `output_cap` (ok), не K4; UTF-8 → отдельный код | Это самая безопасная и CHUNK-инвариантная семантика; не требует `fstat`-истины и не делает `ok` из критического контроля | Rust-срез, пре-регистрация, негативные контроли |
| **Q13** | Комната | WSL2+KVM, `microvm`, initramfs RO, один `-accel kvm`, без сети/host mounts, seccomp доверенным launcher, cgroup `pids.max=1` для candidate, supervisor вне, доказать `KVM_RUN` | Совпадает с A/E и R7; `q35` — только если `microvm` не загрузится, отдельным профилем; WHPX не fallback | Комната, observation, `head` |
| **Q14** | Наблюдение | seccomp TRACE + ptrace в госте; claim только `observed_in_guest` + `enforced_by_kernel`; никогда `observed_independent`; слепой монитор — провал | Даёт событие до syscall; если ptrace недоступен, честно ограничиться `enforced_by_kernel`/`canary_verified`, а не имитировать независимость | Evidence, статусы, пилот |
| **Q15** | Ключ и recovery | Один operational Ed25519 + offline backup; recovery только revoke/raise `min_epoch`, без admission; выбрать один формат подписи до кода | Узкий recovery не создаёт второй путь; формат — компромисс TCB/инструментов (raw Ed25519 — меньше зависимостей, SSHSIG — готовый ssh-keygen) | Admission, promoter, церемония |
| **Q16** | Пилот генератора | Кодовый пилот на одном шаблоне `file_read_stream`: 20 spec (12+8), 24 мутанта (16+8), 3 повтора, пороги до данных; карточный пилот — только как дешёвый pre-pilot | Проверяет вертикаль, не расширяя Q1; 3/n — инженерный gate | Генератор, допуск |
| **Q17** | Порядок отказов и словарь | K11 → S1 → S6(scope/closure) → K6_EGRESS → K6_UNKNOWN → объектные ошибки → K4 → encoding; output_cap — stop; v3 аддитивно: S10_NOT_FOUND, S11_NOT_REGULAR, S12_ENCODING, S13_TOOL_INACTIVE, S14_ALREADY_EXISTS | Сохраняет draft-пример S6, делает порядок исполнимым, не переиспользует K6 для UTF-8; если владелец хочет K1 — одновременно править draft | Словарь, карточка, негативные контроли |
| **Q18** | Legacy-шесть и `search` | Заморозить registry, genesis event, все шесть `quarantined`; `search` rejected; `net` — отдельный bridge path вне registry; `active` — производный | Нет revalidation-событий, значит `active` ложен; quarantine честнее `needs_revalidation` | Registry, promoter, запуск native |
| **F04** | Статусы | Две оси; authority `not_admitted → owner_signed → admitted_inactive → activated`; `activated` требует текущего evidence и не хранится; `K9_proven` запрещён | Разделяет подпись и право запуска; не позволяет прочитать `admitted` как «безопасен» | Отчёты, promoter, пилот |
| **A01** | Admission-манифест | JCS + detached signature + exact bytes; host promoter; Linux memfd+F_SEAL+execveat; Windows — только хранение/образ, без прямого запуска; `seal`/`netprobe` вне v0 | Это консенсус; Windows handle+ACL D — остаточное окно | Admission, promoter, комната |
| **AUDIT** | Порядок починки | Сначала policy IR/`!`/write/read/search/две карточки/процессы/self-exec/admission; каждый патч с negative control | Пока policy и runtime расходятся, любой `head` будет «зелёным» по ложной причине | Любой код |

**Особо:** Q11–Q18 — это решения владельца, а не голосование пяти моделей.
Если ответы противоречат друг другу, нельзя выбирать «среднее»; нужен
явный выбор и запись, почему он сделан. Конституцию меняет только владелец;
агент может просить поправку, но не вправе её ввести.

---

## 7. Рекомендуемая последовательность

Это рекомендация, а не разрешение. Она минимизирует риск «зелёного прибора,
который ничего не измеряет».

### Шаг 0. Владелец читает R8 и принимает решения

Прочитать этот синтез, R8-бриф и, при необходимости, сырые ответы. Ответить
по Q11–Q18, F04, A01 и AUDIT. До этого **не** реализовывать Rust
`file_read_stream`, admission, комнату, promoter, миграцию registry и
генератор. Допустимы документы, failing-репро тесты и сохранение улик.

### Шаг 1. Записать решения и заморозить контракты

Создать `docs/DECISIONS-R8-2026-11-17.md` (или дополнение к
`DECISIONS-R5`), где по каждому Q — выбор, дата, что он не доказывает.
Зафиксировать выбранную таблицу S02 в `lab/prereg/HEAD-SLICE-R1.json` или
новой пре-регистрации **до** первого прогона. Если выбран v3 — выпустить
`bin/refusal_codes.py` версии 3, аддитивно, и одновременно поправить
draft-пример `head`, если меняется scope-код. Прогнать
`python bin/hs.py gates`; `N/A` не считать зелёным.

### Шаг 2. Добавить failing-репро без изменения поведения

Перед патчами — тесты/репро, которые падают на текущем коде и фиксируют
дефекты:

- policy parity: 19 правил JSON против 14 Rust; каждое из пяти отсутствующих
  deny — отдельный вектор; mutation test «удали deny из IR — suite падает»;
- `!`: `resource_matches("file:!/mnt/**", "file:/etc/passwd")` и
  `net:!10.0.2.2:8790`;
- write: `/mnt/work/../work2/x` не должен проходить policy; `O_TRUNC` не
  должен перезаписывать существующий файл; `NO_XDEV`;
- read: одна строка длиннее `MAX_READ`; файл больше `MAX_FILE`;
  `read_to_string` не должен читать сверх карточного cap;
- search: нечитаемый файл не должен выглядеть как «0 найдено»; Unicode
  case-folding не должен паниковать;
- list: ошибка entry/metadata не должна выглядеть как обычный элемент;
  двойной `resolve_in` — TOCTOU;
- `resolve_in` не должен всегда проверять `read/read`;
- `seal`/`netprobe` self-exec; `max_processes` не enforced;
  `run_tool_g` без admission; две карточки `head`.

Каждый тест: команда → rc → артефакт. Падающий тест — результат, а не сбой
смены.

### Шаг 3. Минимальный гигиенический патч (после явного «да»)

Порядок, который уменьшает ложные зелёные:

1. `policy.json` → типизированный Rust IR (codegen или `include_str` + digest);
   `!` — реальный matcher (`Within`/`Outside`/`Equals`/`NotEquals`); `implied`
   — происхождение, не «необязательность». Удалить ручную копию `POLICY` или
   сделать её генерируемой; гейт должен ловить расхождение.
2. `write`: нормализовать root-relative path до policy-check; `O_EXCL` вместо
   `O_TRUNC`; `RESOLVE_NO_XDEV`; отрицательные контроли на symlink/`..`/
   mount point.
3. `search`: убрать из dispatch первого профиля; код оставить историческим,
   неисполняемым; вызов должен давать явный отказ, а не «0 найдено».
4. `read`: либо временно привести `MAX_READ` к 8192 и проверять строку до
   добавления, либо сразу `file_read_stream` по выбранной таблице. Первое —
   меньший diff, но не закрывает `read_to_string`; второе — срез.
5. `max_processes`: применять cgroup/RLIMIT; `seal`/`netprobe` — вне
   admitted-пути; `run_tool_g` — fail-closed по admission/active.
6. Две карточки `head`: разделить форматы и валидаторы, без fallback.

Каждый пункт — отдельный коммит с negative control и прогоном гейтов. Не
смешивать «починку» и «новую функциональность».

### Шаг 4. Доказать KVM_RUN

В WSL2, отдельным непривилегированным пользователем/каталогом, не трогая
другие проекты: QMP `query-kvm` (`present=true, enabled=true`), fd QEMU на
`/dev/kvm`, успешный `KVM_RUN` в host trace, отрицательный контроль без прав
на `/dev/kvm` (QEMU обязан отказать, а не уйти в TCG). Если `KVM_RUN` не
подтверждён — срез остаётся `closed:false`; WHPX не подставляется
автоматически.

### Шаг 5. Rust `file_read_stream` и прогон `HEAD-SLICE-R1`

После Q12/Q13/Q14 и замороженной таблицы: реализовать `openat2` от root FD,
сырой byte loop, `max_bytes_read`, `line_count`, `truncated`, `stop_reason`,
UTF-8-отказ, `bytes_read`/диагностику. Только синтетическая фикстура
`model_visible`. Прогнать восемь критических контролей; FAIL сохраняется,
порог не ослабляется. `bytes_read > max_bytes_read`, байты вне root,
network/write/host mount, TCG как boundary — kill.

### Шаг 6. Admission и promoter

После Q15/A01: JCS-манифест, detached signature, exact-byte digest, epoch/seq/
prev/revocation, evidence digests; promoter проверяет до запуска; Linux
memfd+F_SEAL+execveat; Windows не исполняет candidate; `seal`/`netprobe` вне
v0. Один изменённый байт card/binary — отказ; запуск по пути не даёт
доказанного admission.

### Шаг 7. Registry и генератор

После Q18: заморозить registry, genesis event, `active` вычислять, все шесть
`quarantined`, `search` rejected, `net` — отдельный bridge path. После Q16 и
зелёного ручного `head`: пилот на одном шаблоне, held-out хеширован до
запуска, пороги заморожены, авто-approval нет. `K9_proven` не выдавать ни на
одной ступени.

### Что не делать

- Не выбирать «среднее» между несовместимыми таблицами S02.
- Не принимать строку 6 из D без поправки пре-регистрации до данных.
- Не переименовывать коды v2 и не переиспользовать `K6` для UTF-8.
- Не использовать WHPX/TCG как security-fallback.
- Не называть `3/n` статистическим доказательством.
- Не запускать генератор до зелёного ручного `head`.
- Не менять конституцию, policy, registry, схему или пре-регистрацию без
  явного решения владельца.
- Не пушить секреты, ключи, токены и сырые значения; только имена файлов и
  отпечатки.

---

## 8. Что этот документ не доказывает

- Что рекомендации §6 приняты владельцем: это только предложения.
- Что пять ответов образуют консенсус: они сходятся в ряде принципов и
  расходятся в контрактах; «большинство» не делает вариант безопасным.
- Что код работает: Rust-срез, admission, комната, promoter и генератор не
  реализованы; QEMU/KVM, ptrace, seccomp, JCS/Ed25519/SSHSIG не прогонялись.
- Что `c63f3b8` — последний снимок: HEAD при записи `04e8b31`, но код тот же;
  проверять хеши и дерево перед следующей сменой.
- Что `3/n` — вероятность отказа в эксплуатации: это верхняя граница при
  нуле ошибок в конечной выборке, инженерный gate.
- Что `admitted` означает «безопасен»: это полномочие, а не доказательство
  поведения; `K9_proven` в v0 запрещён.
- Что внешние ответы можно считать источником истины: D содержит прямые
  противоречия, C — невалидную строку и спорный `fstat`-EOF, A — смешение
  порядка S1, B — другой контракт `truncated`; всё проверяется по коду.

---

## 9. Где смотреть дальше

- [`docs/EXTERNAL-QUESTIONS-R8.md`](EXTERNAL-QUESTIONS-R8.md) — одиннадцать
  вопросов и pinned-ссылки на `c63f3b8`.
- [`docs/R7-SYNTHESIS.md`](R7-SYNTHESIS.md) — предыдущий слой; R8 его не
  переписывает, а уточняет.
- [`docs/DECISIONS-R5-2026-11-16.md`](DECISIONS-R5-2026-11-16.md) — принятые
  Q1–Q10; не переоткрывать без аргумента.
- [`docs/CONSTITUTION-v0-2026-11-16.md`](CONSTITUTION-v0-2026-11-16.md) —
  K1–K11 и юрисдикция; K11 не применяется к native.
- [`docs/research/external/README.md`](research/external/README.md) — сырые
  ответы R5–R8 с размерами и SHA-256.
- [`lab/prereg/HEAD-SLICE-R1.json`](../lab/prereg/HEAD-SLICE-R1.json) —
  запечатанная пре-регистрация среза.
- [`lab/tools/policy.json`](../lab/tools/policy.json),
  [`lab/tools/registry.jsonl`](../lab/tools/registry.jsonl),
  [`lab/tools/drafts/head-v1.draft.json`](../lab/tools/drafts/head-v1.draft.json) —
  проверяемые артефакты, а не «красивые документы».
