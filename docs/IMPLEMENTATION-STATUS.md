# IMPLEMENTATION-STATUS — какая реализация каноническая

**Дата:** 11.11.2026; **сверено:** 12.11.2026 — бюджет/приёмка/сеть закрыты этапами 1.5/1.6/1.1
(ссылки на закрывающие артефакты в таблице ниже), Lean-пути переатрибутированы с `F-0080` на `N4`.
**Зачем:** в репозитории два слоя — Python на хосте (`core/`, `bin/`) и Rust
в комнате (`core-rs/`). Пока не сказано, какой из них канонический, проверка может относиться к
одному, а исполняться другой. Это класс `F-0073` (два образа), только на уровне кода.

**Правило.** «Канонический» = **тот, что исполняется в прогоне**. Всё остальное — вторично и
обязано либо совпадать с каноном, либо быть названо расхождением.

---

## Таблица

| фича | канон (исполняется) | вторичная | паритет | доказательство | проверка | известные границы |
|---|---|---|---|---|---|---|
| **политика доступа** | `core-rs/src/loopmod.rs::policy_allows` | `bin/policy_diff.py::policy_allows` (эталон для сверки), `proofs/Proofs/Policy.lean` (модель) | **15 из 18** — три расхождения названы ограничением модели (`**`) | Lean: 6 теорем, но полная сборка `Proofs` красная (`F-0080`) | `python bin/policy_diff.py` | Lean сравнивает **точным** равенством, Rust — префиксом `/**`; это и есть источник трёх расхождений |
| **инструменты** | `core-rs/src/loopmod.rs::tool_*` | `core/tools.py` (оболочка, чтение, поиск — для хостовых сценариев) | **не сверялся** | нет | `cargo test -p hs-core` | у Python-слоя другой набор инструментов; это не «две реализации одного», а два разных набора |
| **журнал** | `core-rs/src/journal.rs` (HSJ2) | `bin/accept.py` (разбор кадра), `core/journal.py` (цепочка событий) | **кадр HSJ2 сверен** Rust↔Python (CRC+kind) | `tests/vectors/journal_frame.json`; Rust `hsj2_frame_cross_vector_matches_python` (--lib) + Python `tests/test_frame_vector.py` | `python bin/rust_tests.py` + `python tests/test_frame_vector.py` | CRC кадра — 32 бита (детектор порчи, не криптостойкость); подделку с пересчётом CRC ловит хеш-цепочка событий, не кадр; HSJ1 отвергается fail-closed; Node-плагин кадр не проверяет (ADR-0056) |
| **цикл** | `core-rs/src/loopmod.rs` | `core/loop.py` (v0, mock-провайдер) | **нет** — разные протоколы | нет | `python bin/hs.py selftest` | Python-цикл — v0 без сети; Rust — рабочий |
| **бюджет** | `core-rs/src/loopmod.rs::Budget` | `core/budget.py` | **не сверялся** | `tests/test_budget.py` | `pytest tests` | `None` больше не читается как ноль → `unknown-cost` (этап 1.5, `1eef3a6`; тест `провайдер_без_расхода_даёт_unknown_cost_а_не_done`, `python bin/rust_tests.py`). **Закрыт без prereg** — порог задним числом не выдуман (`AUDIT-PLAN.md`). Паритет Rust↔Python не сверялся |
| **приёмка** | `bin/accept.py` (хост) + `core-rs/accept-run.ps1` | — | — | 5 критериев на прогон | `pwsh accept-run.ps1` | журнал извлекается **с копии**, оригинал не чинится (этап 1.6, `445718c`, `F-0085`/`C-0296`/`E-0017`, `READONLY-ACCEPT-R1`; `bin/extract_journal.py`, `bin/check_readonly_accept.py`, `research/outputs/readonly-accept.txt`, ADR-0049). Граница: только чистый одноразовый образ |
| **сеть** | `bin/net.py` (хост, через мост) | — | — | 28 записей в `runs/net/net.jsonl` | `python bin/net.py search` | SSRF-фильтр исходящих URL есть (этап 1.1, `9fb67e6`, `bin/net_policy.py`, `tests/test_net_policy.py` — 25 тестов, `F-0081`/`E-0015`, `SSRF-R1`; redirect проверяется). **N6 открыт**: literal `198.18/15` + rebinding (`SSRF-HARDEN-R1`) |
| **мост** | `bin/bridge.py` (хост) | `proofs/Proofs/Bridge.lean` (модель) | **не сверялся** | 6 теорем | `python bin/bridge_verify.py` | `bridge_verify` — поиск по тексту, не поведение |
| **Lean-доказательства** | `proofs/` (в репозитории с 11.11.2026) | — | — | 6 + 6 + 3 теоремы | `lake build Proofs` | **полная сборка красная** (`F-0080`) |

---

## Что это меняет в работе

1. **Правка политики** идёт в `loopmod.rs`; Lean-модель и `policy_diff.py` — сверка, а не источник.
2. **Правка журнала** идёт в `journal.rs`; Python-журнал — отдельная реализация, не эталон.
3. **`core/loop.py` — не канон.** Это v0 с mock-провайдером. Утверждения о цикле проверяются на Rust.
4. **Скрипты, которые ищут `C:/111/env/lean/proofs`, смотрят не туда** — доказательства теперь в
   `proofs/` этого репозитория. Это **N4** (`AUDIT-PLAN.md`), не `F-0080`: 5 скриптов хардкодят путь
   (`bin/lean_check.py:15`, `policy_diff.py:23`, `bridge_lean.py:23`, `bridge_parts.py:23`, `session_types.py:23`).
   `F-0080` — отдельный дефект (namespace `Effect` в корне `Policy.lean`/`PartBridge.lean`), нужен ADR.

---

## Открытые расхождения (не закрыты)

| расхождение | класс | где записано |
|---|---|---|
| Lean: точное равенство; Rust: префикс `/**` | `policy_diff` 15 из 18 | `bin/policy_diff.py`, `README` |
| `net` нет в реестре и README | учёт | план этап 2.4 |
| полная сборка `Proofs` красная | формальная проверка | `lab/failures/F-0080.md` |
