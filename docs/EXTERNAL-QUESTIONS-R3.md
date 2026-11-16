# Внешний специалист: круг R3 — синхронизация представлений и архитектура изоляции

**Дата:** 16.11.2026. **Кому:** ИИ-модели с доступом к поиску.
**Правила ответа:** по каждому id — ≤ 120 слов, `источник: <URL>`, тип `факт`/`суждение`/`выбор`.
Числа без источника не считаются. Код не нужен — нужны решения, прецеденты и цена альтернатив.
Если вопрос поставлен неверно — переформулируйте.

---

## Контекст проекта (без него ответы будут мимо)

**herness** — харнесс для агентов на трёх уровнях: политика, посредник, замыкание.
Репозиторий: <https://github.com/mak777uh/herness> (MIT, публичный). 32 гейта с 34 пробами,
305 утверждений, 8 Lean-модулей, CI из 5 job'ов.

**Комната:** собственное ядро Linux 6.18 (Landlock ABI7, стены закрыты), QEMU с Rust PID1 без shell,
шесть инструментов (`read`, `list`, `search`, `write`, `seal`, `netprobe`), журнал HSJ2
(CRC кадра + kind внутри CRC + карантин оборванного хвоста).

**Доказательства:** Lean 4.36.0-rc2, 8 модулей, 11 теорем. Три стандартные аксиомы
(`propext`, `Classical.choice`, `Quot.sound`). Негативные контроли — сейчас «обязаны не собраться».

**Проблема, которую нашли два независимых ответа на R2:**
Lean-модель (`Policy.lean` — точное сравнение строк), Rust-реализация (`resource_matches` с
wildcard `/**` и `**`) и карточка (`head.json` — замыкание) — три представления, которые
расходятся в семантике wildcard. DRT невозможен без синхронизации.

---

## R3-1. Синхронизация Lean-модели с Rust wildcard `/**` и `**`

**Что нашлось:** `Policy.lean` сравнивает строки точно (`stringEq`), тогда как Rust
`resource_matches` реализует glob-семантику: `/**` — любое количество сегментов пути, `**` —
любые символы внутри сегмента. DRT (дифференциальное тестирование) на текущих представлениях
даст ложные расхождения или пропустит реальные.

**Вопросы:** Переписать Lean-модель под Rust-семантику (в Lean нет `**`, нужна индуктивная
функция по сегментам пути) или перейти на конечный автомат? Есть ли прецедент формализации
glob-семантики в Lean 4? Какая цена (число LOC, число новых лемм)?

**Что решает:** DRT станет возможным — модель и код начнут совпадать на одинаковых входах.

**Ссылки:**
- [`proofs/Proofs/Policy.lean`](https://github.com/mak777uh/herness/blob/main/proofs/Proofs/Policy.lean)
- [`core-rs/src/loopmod.rs`](https://github.com/mak777uh/herness/blob/main/core-rs/src/loopmod.rs) — `resource_matches`
- [`bin/policy_diff.py`](https://github.com/mak777uh/herness/blob/main/bin/policy_diff.py)

---

## R3-2. HSJ2: hash-chain или подписанный checkpoint?

**Что нашлось:** HSJ2 покрывает CRC кадра + kind, но **не связывает записи между собой**.
Подмена с пересчётом CRC не ловится. Обнаруживается порча одного кадра, но не доказывается
неизменяемость цепочки или авторство.

**Вопросы:** Добавить `event_hash → prev_hash` цепочку (как в событиях JSONL, но в бинарном
журнале)? Или достаточно подписанного checkpoint каждые N записей? Какой компромисс цены
(дополнительные байты на кадр) и гарантии (неизменяемость vs детекция порчи)? Какова практика
(блокчейн-журналы, append-only логи, tamper-evident storage)?

**Что решает:** уровень доверия к журналу — «порчу вижу» против «неизменяемость доказываю».

**Ссылки:**
- [`core-rs/src/journal.rs`](https://github.com/mak777uh/herness/blob/main/core-rs/src/journal.rs)
- [`bin/verify_journal.py`](https://github.com/mak777uh/herness/blob/main/bin/verify_journal.py)

---

## R3-3. Разделение инструментов на процессы: как PID1 раздаёт capability?

**Что нашлось:** оба ответа R2 согласны — capability-хэндлы требуют отдельных процессов.
Инструменты в одном PID1 = индивидуальные права на уровне ОС не изолированы.

**Вопросы:** Как PID1 раздаёт FD и Landlock каждому инструменту-процессу? Какой IPC — Unix
socket, pipe, shared memory? Какова цена (сериализация, латентность) и какова выгода (изоляция,
per-tool capability)? Есть ли прецедент «супервизор раздаёт файловые дескрипторы» в embedded /
container / micro-VM? Как применить Landlock per-process (не per-thread) в Rust?

**Что решает:** архитектура инструментов — в одном процессе или в отдельных.

**Ссылки:**
- [`core-rs/src/loopmod.rs`](https://github.com/mak777uh/herness/blob/main/core-rs/src/loopmod.rs) — 144 КБ, все инструменты в одном процессе
- [`core-rs/src/sandbox.rs`](https://github.com/mak777uh/herness/blob/main/core-rs/src/sandbox.rs)
- [Landlock man page](https://man7.org/linux/man-pages/man7/landlock.7.html)

---

## R3-4. NC как компилирующаяся теорема: написать и проверить

**Что нашлось:** оба ответа R2 согласны — NC должен быть **зелёной теоремой о ложности мутанта**
(`decide` на конкретном входе), а не красной сборкой. `native_decide` запрещён в 4.36.

**Вопросы:** Написать `BridgeNegative.lean` в новом формате: witness-лемма
`(forward cfg₀ req₀).host ≠ req₀.wantedHost := by decide` на конкретных строковых значениях.
Проверить: `lake build Proofs.BridgeNegative` даёт **успех** (а не падение)?
Как это переносится на PartBridgeNegative и Negative (для Policy)?

**Что решает:** все негативные контроли станут компилирующимися доказательствами ложности —
это устраняет неоднозначность вердикта.

**Ссылки:**
- [`proofs/Proofs/BridgeNegative.lean`](https://github.com/mak777uh/herness/blob/main/proofs/Proofs/BridgeNegative.lean)
- [`proofs/Proofs/Negative.lean`](https://github.com/mak777uh/herness/blob/main/proofs/Proofs/Negative.lean)
- [`bin/lean_wsl.py`](https://github.com/mak777uh/herness/blob/main/bin/lean_wsl.py)

---

## R3-5. `BridgeNegative.lean` не достижим из агрегата

**Что нашлось:** `proofs/Proofs.lean` импортирует Policy, Bridge, PartBridge. Негативные контроли
(Negative, BridgeNegative, PartBridgeNegative) и Probe в агрегат не входят.
`check_lean_imports.py` уже ловит это (объявленные корни). Но `BridgeNegative` собирается только
`bridge_lean.py` — если его забыть, файл не компилируется и никто не заметит.

**Вопросы:** Добавить все негативные контроли в ROOTS `check_lean_imports.py`? Или добавить
`BridgeNegative` в агрегат `Proofs.lean` (но тогда он соберётся, а должен упасть)? Как
маркнуть «этот модуль обязан упасть» в агрегате?

**Что решает:** полнота Lean-модулей — ни один файл не остаётся без проверки.

**Ссылки:**
- [`bin/check_lean_imports.py`](https://github.com/mak777uh/herness/blob/main/bin/check_lean_imports.py)
- [`proofs/Proofs.lean`](https://github.com/mak777uh/herness/blob/main/proofs/Proofs.lean)

---

## R3-6. Карточка: разрешить сеть, если она объявлена в ceiling

**Что нашлось:** `bin/tool_card.py` запрещает ВСЮ сеть (`closure.net: сеть не объявляется`),
но в комнате уже есть net-мост `10.0.2.2:8790`, и `netprobe` — сетевой инструмент.

**Вопросы:** Разрешить сеть в карточке, если она объявлена в ceiling (`lab/tools/ceiling.json`)?
Какая форма — `protocol:host:port` или URI? Как связать с SSRF-фильтром (`bin/net_policy.py`)?
Объявленные назначения = allowlist, всё остальное — deny?

**Что решает:** карточки сетевых инструментов станут возможными без обхода валидатора.

**Ссылки:**
- [`bin/tool_card.py`](https://github.com/mak777uh/herness/blob/main/bin/tool_card.py)
- [`bin/net_policy.py`](https://github.com/mak777uh/herness/blob/main/bin/net_policy.py)

---

## R3-7. Прецедент Cedar DRT: какой процент входов покрыл все правила?

**Что нашлось:** Cedar гоняет cargo-fuzz с генераторами согласованных (policy, entities, request)
на ~100 млн входов за ночные часы. DRT+PBT нашли 21 баг.

**Вопросы:** Как генерировать согласованные тройки (policy, entities, request) для нашего
посредника (19 правил, 6 инструментов)? Какой процент покрытия правил достаточен? Каков критерий
«DRT зелёный» — ноль расхождений за N входов? Как встраивать в CI (nightly vs каждый push)?

**Что решает:** наш DRT будет калиброван прецедентом, а не догадкой.

**Ссылки:**
- [Cedar DRT](https://www.amazon.science/blog/how-we-built-cedar-with-automated-reasoning-and-differential-testing)
- [`bin/policy_diff.py`](https://github.com/mak777uh/herness/blob/main/bin/policy_diff.py)

---

## R3-8. Comprehension-тест: написать конкретные вопросы для карточки `head`

**Что нашлось:** обе модели R2 согласны — прозрачность меряется экспериментом. 5–7 вопросов
«почему / что будет если», испытуемый — свежая модель без контекста генерации.

**Вопросы:** Написать конкретные вопросы для карточки `head` (id, purpose, замыкание /mnt/**,
отказы S6_CLOSURE_BREACH и S1_SCHEMA). Например: «Что вернёт инструмент на /etc/passwd?», «Почему
n=0 даёт отказ?», «Какие файлы может читать?». Кто оценивает — человек или свежая модель?
Какой критерий — доля верных ответов?

**Что решает:** метрика прозрачности станет измеримой и воспроизводимой.

**Ссылки:**
- [`lab/tools/cards/head.json`](https://github.com/mak777uh/herness/blob/main/lab/tools/cards/head.json)
- [`bin/tool_card.py --render`](https://github.com/mak777uh/herness/blob/main/bin/tool_card.py)

---

## Что решает каждый вопрос

| id | решает | блокирует |
|---|---|---|
| R3-1 | DRT для посредника | синхронизация модели и кода |
| R3-2 | уровень доверия к журналу | hash-chain или checkpoint |
| R3-3 | архитектура инструментов | per-tool capability |
| R3-4 | все негативные контроли | неоднозначность вердикта |
| R3-5 | полнота Lean-модулей | невидимые файлы |
| R3-6 | карточки сетевых инструментов | валидатор строже системы |
| R3-7 | калибровка DRT | число входов |
| R3-8 | метрика прозрачности | конкретные вопросы |
