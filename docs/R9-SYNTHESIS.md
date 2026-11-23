# R9 — синтез ответов A/B/C и план реализации

**Дата:** 23.11.2026. **Снимок кода:** `ce7c64d930720da4e6fdc74ce88ccf950d301c55`.
**Статус:** синтез внешних рекомендаций — не approval и не решение; конституционные пункты утверждает владелец (помечены).

**Участники** (все ответы сохранены байт-в-байт с SHA-256 в [`docs/research/external/`](https://github.com/mak777uh/herness/tree/main/docs/research/external); метки — порядок вложений владельца):

| метка | раунды | файл | SHA-256 (первые 8) | особенность |
|---|---|---|---|---|
| A | R9 + R9.1 + R9.2 | [2026-11-23-R9-answer-A.md](https://github.com/mak777uh/herness/blob/main/docs/research/external/2026-11-23-R9-answer-A.md), […R9.1-answer-A.md](https://github.com/mak777uh/herness/blob/main/docs/research/external/2026-11-23-R9.1-answer-A.md), […R9.2-answer-A.md](https://github.com/mak777uh/herness/blob/main/docs/research/external/2026-11-23-R9.2-answer-A.md) | `cf36482b`, `cc9af061`, `59a37ece` | 31 вопрос + дожим + V1–V6; сквозная линия «один IR → одно ядро» |
| B | R9.2 | [2026-11-23-R9.2-answer-B.md](https://github.com/mak777uh/herness/blob/main/docs/research/external/2026-11-23-R9.2-answer-B.md) | `022cbf52` | статическое чтение снимка через GitHub; «наиболее опасны разрешительные результаты без проверки условия» |
| C | R9.2 | [2026-11-23-R9.2-answer-C.md](https://github.com/mak777uh/herness/blob/main/docs/research/external/2026-11-23-R9.2-answer-C.md) | `e53b0280` | **исполнил локальный failing-репро** чекера; две фактические поправки к брифу |

## 0. Факты, подтверждённые кодом (сверка владельцем-агентом, снимок `ce7c64d`)

| # | факт | заявлен | вердикт |
|---|---|---|---|
| F1 | `chain.py:102` — `if adjacent_methods and methods:` отключает проверку методов при пустом/отсутствующем `allowed_methods` | A, B, C (C — **исполнением репро**) | **подтверждено** |
| F2 | `chain.py:79` — `proven` самодекларируемый boolean | A, B, C (репро) | **подтверждено** |
| F3 | `Composition.lean:128` — `Bridge.proven : Bool`, `allProven`; методы в Lean-модели отсутствуют вовсе | B | **подтверждено** |
| F4 | `cards/head.json` = `head_legacy`, `status:"superseded", superseded_by:"head"`; живая карточка — `drafts/head-v1.draft.json` (`schema_version: tool-card-v1`); её читает `check_policy_parity.py` (`DRAFT`); `tool-card-v1.schema.json` и `tests/test_head_cards.py` существуют | B, C | **подтверждено** — позиция A по V4 была направленно неверна |
| F5 | `model.rs` — `EXTERNAL_TRUST = "external_untrusted"` как строковая константа; taint в Reply/Step не сохраняется (NC-019/C-0325) | B | подтверждено (константа; следствие — NC) |
| F6 | `bridge.py` — `BaseHTTPRequestHandler`, `MAX_BODY = 8 MiB`, пути через префикс `/v1/` (не-тотальная грамматика stdlib) | B, C | подтверждено |
| F7 | admission: 6 digest-полей, owner-ключа нет, `active` пуст | B, C, A | подтверждено (NC-019) |

**Новая находка C (CLAIM, не проверена мной):** `urllib.request` следует редиректам и не снимает `Authorization` при cross-host redirect — потенциальная утечка ключа провайдера (upstream фиксирован при старте, риск ограничен; смежно с N6/SSRF). Требует пре-регистрируемой проверки.

## 1. Консенсус и расхождения по V1–V6

| V | A | B | C | вердикт синтеза |
|---|---|---|---|---|
| V1 семантика пустых методов | (а) deny-all, поле обязательное, «любой» = перечисление | (а) deny-all, дискриминированный объект `mode: only/any` | (а) deny-all, absent → `K9_SCHEMA`, «любой» в v1 не выражается | **консенсус 3/3**: deny-all; поле обязательное; absent → `K9_SCHEMA`; wildcard нет; семантика — *покрытие* (отказ, когда adjacent непуст и downstream не покрывает; `[]` у adjacent = ничего не пересылает → проверка проходит). Воплощение — минимальное по A, схема — по C/B |
| V2 K12 | принять, поправка | принять, поправка; две решётки, `ControlProvenance`, endorsement-конверт ed25519 | принять, поправка; **модель = taint-laundering oracle**: session-coarse отвергнут, enforce = channel-separation + целостность артефактов + pre-committed plans | **консенсус 3/3 — нужна ваша санкция** (поправка конституции). Формулировка закона — C; endorsement-конверт — B; IR-taint — с ядром |
| V3 K11 | uniform для не-native, конверты | uniform; операционное определение native/generated (образ, не путь); делегированная политика для restricted-класса | uniform по *происхождению ревью*; scoped class-admission для sandboxed read-only workers (выход = untrusted) | **консенсус 3/3 — нужна ваша санкция** (поправка конституции). uniform + два уровня: подписанная политика класса для sandboxed workers, персональный допуск для privilege/trust-role |
| V4 карточки head | каноническая = cards, закат drafts | (в) отложить до IR; долг `HEAD-CARD-IR-DEBT`; авто-конверсия запрещена (не-тотальна) | каноническая = **v1 draft**; промоушен draft→cards сейчас, legacy в архив, валидатор на jsonschema, гейт единственности | **код на стороне C** (F4). Принимаем C: закрыть сейчас (0,5–1 день), взяв у B запись долга, запрет авто-конверсии и тесты «superseded не активируется» |
| V5 транспорт | кадры первыми (~30 LOC), vsock при зелёной пробе | **HTTP-subset сейчас**, vsock только после пре-регистрируемой пробы | **HTTP-subset сейчас**; stdlib-грамматика не-тотальна (живые smuggling-поверхности); vsock на Windows предсказуемо RED (vhost-vsock — Linux) | **2/3 за HTTP-subset**: strict-validator + ~22 мутанта сейчас; проба `VSOCK-WIN-R1` пре-регистрируется (порог объявить до прогона); кадры — post-IR. Находку C про redirect/Authorization проверить отдельно |
| V6 proven | объект `{kind, artifact, sha256, toolchain, theorem}` | (в+) proof-package с **запуском pinned Lean** + `k9_certificate_digest` как 7-е поле admission; `BridgeSpec/VerifiedBridge`; «сертификат ≠ K9_proven» | объект + `subject_sha256` (JCS цепочки без proven) + регенерационный гейт + миграция через `ChainInstances.lean` | **слои совместимы**: сейчас — объект с subject-привязкой по C (закрывает F2 немедленно, чекер — единственная точка проверки); при оживлении admission — proof-package с запуском Lean по B (его «подмножество A» замечание принято: хеш файла ≠ истина) |

## 2. План реализации

### Этап 0 — делать сейчас (≈4–6 рабочих дней; без поправок конституции; гейты 33/33 не ослабляются, только усиливаются)

Порядок с зависимостями: **V1 → V6** (Lean-инстанс V6 строится на том же `chainOk` с методами); V4 и V5-валидатор независимы. Каждый шаг — отдельный коммит, порог пре-регистрируется до прогона, failing-репро воспроизводится у себя до фикса (для V1 репро C — дословный).

1. **V1** (0,5–1 день): убран охрана `and methods`; `allowed_methods` обязательное, absent → `K9_SCHEMA`; закрытый enum методов; фикстуры `methods-empty/absent/ok/narrowing`; Lean: `Bridge.methods` + `forwardsMethods` + теорема покрытия + падающий негатив; `tests/test_chain.py` helper всегда эмитит поле.
2. **V6** (1–2 дня): `proven` → `{kind, artifact, sha256, subject_sha256}`; коды `K9_PROVEN_BAD_FORMAT/MISSING_ARTIFACT/HASH_MISMATCH/SUBJECT_MISMATCH` под зонтиком `K9_CHAIN_UNPROVEN`; `ChainInstances.lean` (`decide`) + машинный отчёт; миграция `allowed.json`/`taint.json`; гейт-антиоткат (boolean → отказ схемы; мутант «вернуть строку 79» обязан падать).
3. **V4** (0,5–1 день): `drafts/head-v1.draft.json` → `cards/head.json`; legacy → `lab/tools/archive/`; `check_policy_parity.py` читает новое место; `bin/tool_card.py` на jsonschema против `tool-card-v1.schema.json`; гейт единственности схемы + «superseded не активируется»; закат legacy-валидатора 2026-12-07.
4. **V5-валидатор** (1–2 дня): strict pre-handler перед `do_POST` (фиксированные маршруты `/v1/{chat,net,journal}`, allowlist заголовков, канонический `Content-Length`, запрет TE/Expect, anti-smuggling, один запрос на соединение) + корпус ~22 мутантов + коды `BRIDGE_HTTP_*`; Rust-клиент эмитит канонические запросы. Отдельно: пре-регистрация пробы `VSOCK-WIN-R1` (порог: устройство стартует, p99 < 5 мс, 0/10000 потерь, изоляция CID) — ожидание RED; проверка redirect/Authorization по находке C.

### Этап 1 — после вашего «да» (конституционные поправки + ключ)

5. **ADR K12** (формулировка C одной фразой; endorsement-конверт `herness-control-endorsement-v1` по B — ed25519, owner-signed, одно-use, не создаются моделью; channel-separation guard сейчас, IR-taint с ядром; NC: «модель-опосредованная инъекция K12 не останавливается — ограничивается K1–K10 + pre-committed plans»). Код `K12_CONTROL_TAINT` в словарь v2.
6. **ADR K11** (origin-of-review; scoped class-admission для sandboxed read-only workers с `output=untrusted`; `k9_certificate_digest` — седьмое поле admission-манифеста; генератор не меняет собственную политику делегирования).
7. **Церемония owner-ключа** ([`docs/OWNER-RUNBOOK-2026-11-17.md`](https://github.com/mak777uh/herness/blob/main/docs/OWNER-RUNBOOK-2026-11-17.md)) — без неё endorsement, конверты и admission не операциональны.

### Этап 2 — стратегия (все три модели сошлись)

8. **IR-ядро**: один интерпретатор обязательств (каталог 7 законов / 8 инстансов из S1/S2 ответа A), семантика в Lean, conformance-гейт «Lean ≍ настоящий Rust» на корпусе с мутантами; калибровка — [`research/outputs/TCB-LOC-R1-2026-11-23.txt`](https://github.com/mak777uh/herness/blob/main/research/outputs/TCB-LOC-R1-2026-11-23.txt) (4552 строки в трёх рукописных представлениях). `policy_eval` исполняет настоящий Rust — транскрипция удаляется (FACT-2 раунда R9.1).

## 3. Честные границы (NC-пул для новых работ)

- `K9_proven` не выдаётся ни на одном шаге (B: «сертификат доказывает проверяемость формального утверждения, не соответствие кода») — потолок `K9_model_checked`.
- K12 не останавливает модель-опосредованную инъекцию (модель отмывает taint) — ограничивается K1–K10 + pre-committed plans; записать в NC при ADR.
- Привязка `proven` по хешу доказывает *привязку*, не *истинность* доказательства (истинность — от регенерационного гейта и Lean-ядра).
- vsock на Windows — ожидание RED; решает проба, не мнение.
- Доля ложных отказов K12 не выдумывается — измеряется на пре-регистрируемом корпусе задач.

## 4. Что дальше — ответ на вопрос владельца

**Ещё бриф не нужен — пора делать.** Обоснование: 3/3 консенсус на V1–V3; V4 решён кодом (C прав, проверено); V5 решается пре-егистрируемой пробой, а не четвёртым мнением; V6 — слои совместимы. Четвёртый независимый ответ дал бы мало нового.

От владельца остались ровно два решения и одно действие: **«да» на ADR K12**, **«да» на ADR K11**, позже — **церемония ключа**. Всё остальное (Этап 0) — работа агента без дополнительных решений.

Проверка реализаций: по B — «воспроизвести каждый негативный контроль на следующем коммите»; peer-review реализаций диффом — единственный будущий бриф, если понадобится.

## 5. Сверка

- FACT — проверено чтением/исполнением (указано, кем); FACT-CODE — следствие чтения кода; CLAIM — не проверено; UNVERIFIED — не открыто.
- Совпадение трёх ответов — не согласие, а сужение развилки; окончательное решение — владельца.
- Не проверено мной: `registry.state.json`, содержимое `tool-card-v1.schema.json`, dispatch-секция `loopmod.rs`, redirect/Authorization (CLAIM C).
