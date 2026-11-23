# Внешние ответы — сырые тексты

Здесь лежат ответы внешних моделей ровно в том виде, в каком их передал владелец.
Это **не решения**, не approval и не поправка к конституции. Решения принимает владелец;
агент может только предложить, проверить и зафиксировать.

## R5 — 16.11.2026

| файл | размер | SHA-256 | что внутри |
|---|---:|---|---|
| [`2026-11-16-R5-answer-A.md`](2026-11-16-R5-answer-A.md) | 18 550 Б | `0d7eaa10edbfac0426b22d682e72b35e551854674b6ef4181d88b33cf49e0b60` | «фундаментальная четвёрка»: D02, S02, S01, D01 и матрица производных; остальные 20 вопросов не раскрыты |
| [`2026-11-16-R5-answer-B.md`](2026-11-16-R5-answer-B.md) | 97 483 Б | `2be360cb5f729e98ba728b09a55b7a4f0d41e0e5fcdd0f82ded0a2c70edf0a8e` | все 24 вопроса R5: D, S, C, T, R, E; схемы, алгоритмы, тест-матрица, источники |

Модели, сгенерировавшие ответы, владельцем не названы. Не приписывать авторство
и не выдавать эти тексты за консенсус: A и B расходятся, сводка и расхождения —
[`docs/R5-SYNTHESIS.md`](../../R5-SYNTHESIS.md).

## R6 — 17.11.2026

Шесть ответов на [`EXTERNAL-QUESTIONS-R6.md`](../../EXTERNAL-QUESTIONS-R6.md).
Пять пришли как `.txt`, один — как `.md`; все сохранены байт-в-байт, без нормализации
переводов строк (правило в `.gitattributes`).

| файл | размер | SHA-256 | что внутри |
|---|---:|---|---|
| [`2026-11-17-R6-answer-A.txt`](2026-11-17-R6-answer-A.txt) | 45 918 Б | `7ca56925168d7e711ccc37a40b79cbf5efd8760cc2e63a2e3ac0d13ff875a496` | независимый разбор: F01–F03, S01–S02, R01–R03, T01–T02, P1 F04/R04/R05/I01; Lean-ядро, Rust-валидатор, WSL2+KVM предпочтительно |
| [`2026-11-17-R6-answer-B.txt`](2026-11-17-R6-answer-B.txt) | 68 106 Б | `fc95d894e8114b0ad8d4c2928839c96b76da1abdf9be573f9546c20a3d208918` | проверял код и JCS-векторы; F01–F04, S01–S02, R01–R03, T01–T02, S05/R05; Lean+Kani, Rust-валидатор, WSL2+KVM; нашёл конфликт `max_processes` и `resource_of` |
| [`2026-11-17-R6-answer-C.txt`](2026-11-17-R6-answer-C.txt) | 49 539 Б | `b723536d9901467c2422cbebd717b399bf1ecfb8b9d591f5c6832eb32b8fe3af` | ссылки не открывал; F01–F04, S01–S02, R01–R03, T01–T02, S05/R04/R05; Lean + Rust-дифференциал, Rust-валидатор, WHPX как основной путь |
| [`2026-11-17-R6-answer-D.txt`](2026-11-17-R6-answer-D.txt) | 52 252 Б | `394c6fbdaebc8f1216cb66f60f2f7e505f37b61a4055546099415bcd294e9dda` | только P0: F01–F03, S01–S02, R01–R03, T01–T02; малая Lean-модель, WHPX/KVM, честные границы наблюдения |
| [`2026-11-17-R6-answer-E.txt`](2026-11-17-R6-answer-E.txt) | 123 014 Б | `52d2fee2de57057742113580cb6eff03fd1ba5c89da2b795ba68a68a651c6e5e` | все F/S/R/T, включая S03/S04/S06, R04/R05; Lean+proptest, 4 шаблона, seccomp-unotify + фазовый барьер; в S02 читает 1 байт сверх бюджета и выдаёт частичную строку |
| [`2026-11-17-R6-answer-F.md`](2026-11-17-R6-answer-F.md) | 81 488 Б | `0a7cc3797e72c6049dd6a04091e5f1b6dc537b231768a4cdf48bb925442477d5` | все 10 P0 + F04/S05/R05/I03; проверял код; Lean-инфраструктура, Python как канонический валидатор, WSL2+KVM; зафиксировал `NO_MAGICLINKS`/`NO_XDEV`, stored `active` и `card_atoms` rc=3 |

Это **не консенсус и не approval**. Шесть ответов расходятся по валидатору, семантике
`file_read_stream`, ускорителю, модели процессов, наблюдению, ключам, объёму генератора
и приоритету отказов. Сводка, проверка утверждений и развилки —
[`docs/R6-SYNTHESIS.md`](../../R6-SYNTHESIS.md).

## R7 — 17.11.2026

Пять ответов на [`EXTERNAL-QUESTIONS-R7.md`](../../EXTERNAL-QUESTIONS-R7.md) — все 11 вопросов
(F01, S02, R01–R03, T01–T02, S05, F04, A01, AUDIT) в каждом. Четыре пришли как `.txt`, один —
как `.md`; сохранены байт-в-байт, без нормализации переводов строк (правило в `.gitattributes`).

| файл | размер | SHA-256 | что внутри |
|---|---:|---|---|
| [`2026-11-17-R7-answer-A.txt`](2026-11-17-R7-answer-A.txt) | 68 505 Б | `c06c76c67a8051c3fc3fa16a6aee20fa563881b7b1cd63976fb50e3666baac92` | открывал снимок на GitHub, проверял код; Rust-валидатор, WSL2+KVM, ptrace-наблюдение; «сырой» Ed25519/OpenSSL, один ключ + backup, без recovery-root; поправки к `resource_of` и `write_beneath` (NO_SYMLINKS влечёт NO_MAGICLINKS) |
| [`2026-11-17-R7-answer-B.txt`](2026-11-17-R7-answer-B.txt) | 47 167 Б | `0ba05db696a9ce34138f40c0f3cfaa459141f9ec4a35c62709ba68d1a066e1b2` | код не открывал; Rust-валидатор, WSL2+KVM, наблюдение через отказы ядра + канарейки (без `observed_independent` в v0); отдельные `bytes_received`/`bytes_consumed`; recovery-ключ может обновлять/отзывать trust anchor, но не допускать; генератор — только карточка одного kind |
| [`2026-11-17-R7-answer-C.txt`](2026-11-17-R7-answer-C.txt) | 85 057 Б | `19e7d865ed00e6c364e7ef57d6946710c05ce5a1f489523ca6454127a860b523` | код не открывал; таблица правил V01–V13 + исполняемые векторы, Rust-канон; runtime-revalidation; ptrace+seccomp TRACE; один ключ без recovery-root; 3 шаблона × 4 spec + 6 held-out; `output_cap`, `RLIMIT_NPROC`; EOF-зонд запрещён (в R6 C предлагал обратное) |
| [`2026-11-17-R7-answer-D.md`](2026-11-17-R7-answer-D.md) | 80 488 Б | `06e1c01c5523ce6d0496348d419594911a033ec2f23dcacf42de56f02cd32980` | Arena.ai Agent Mode, снимок проверял по файлам; Rust-валидатор, WSL2+KVM; Landlock audit logging как наблюдение (на ядре 6.6 недоступно — ABI v7/6.15); recovery-ключ только revoke/rotate; лестница `slice_passed`; 3 шаблона/108 прогонов; внутренние противоречия в S02 и глобальный `monotonic_counter`; указатель реестра в агентском дереве |
| [`2026-11-17-R7-answer-E.txt`](2026-11-17-R7-answer-E.txt) | 71 976 Б | `3f210e665f3d25fa7fb81f7e18903b4442b578834fea67ab318fd6400d4a4e93` | открывал снимок через `raw.githubusercontent.com`, исполнял эталон S02; Rust-валидатор, WSL2+KVM, seccomp+ptrace; один операционный ключ + backup; 2 шаблона/20 spec; проверил, что `tool_write_in` не вызывает `resolve_in`, и расхождение Rust `POLICY` 14 против `policy.json` 19 |

Это **не консенсус и не approval**. Ответы сходятся по Rust-канону, производному `active`,
безопасности точных байтов и комнате без сети, но расходятся по семантике S02, механизму
наблюдения, модели процессов, топологии ключа, объёму генератора и формату статусов.
Проверка утверждений и развилки — [`docs/R7-SYNTHESIS.md`](../../R7-SYNTHESIS.md);
следующий бриф — [`docs/EXTERNAL-QUESTIONS-R8.md`](../../EXTERNAL-QUESTIONS-R8.md).

## R8 — 17.11.2026

Пять ответов на [`EXTERNAL-QUESTIONS-R8.md`](../../EXTERNAL-QUESTIONS-R8.md) — все 11 вопросов
(F01, S02, R01–R03, T01–T02, S05, F04, A01, AUDIT) в каждом. Четыре пришли как `.txt`, один —
как `.md`; сохранены байт-в-байт, без нормализации переводов строк (правило в `.gitattributes`).
Метки A–E — порядок вложений владельца, а не самоидентификация моделей.

| файл | размер | SHA-256 | что внутри |
|---|---:|---|---|
| [`2026-11-17-R8-answer-A.txt`](2026-11-17-R8-answer-A.txt) | 65 172 Б | `284862a9b1d9012cfee3e8c9cffe7036e1d21223aee2ce1e0115615d9057dce8` | открывал снимок `c63f3b8`, читал код; полный Rust-валидатор на promoter + тонкий runtime V02/V04/V05/V06/V12; WSL2+KVM `microvm`; seccomp TRACE + ptrace; SSHSIG; пять native `needs_revalidation`; карточный пилот 20/20/20; `policy.json` → codegen |
| [`2026-11-17-R8-answer-B.txt`](2026-11-17-R8-answer-B.txt) | 62 585 Б | `e9dfbca2c388ddad8083a452a884f28225aa676c6eb4bed6ea6787cb5a7760d4` | репозиторий не открывал; один Rust-валидатор дважды (приём и каждая загрузка), C01–C12; WSL2+KVM `q35`; ptrace; SSHSIG; `read`/`list` — `needs_revalidation`, `write`/`seal`/`netprobe` — `quarantined`; карточный пилот 12/16; S1 вторым |
| [`2026-11-17-R8-answer-C.txt`](2026-11-17-R8-answer-C.txt) | 54 519 Б | `874f64a8a80ee616473a02360181a53b5819c7107a994e0da52e34c63cea5e77` | ссылки не открывал; один Rust-крейт на приёме и при каждой загрузке, CV-01–CV-13; WSL2+KVM `q35`, `microvm` — отдельный профиль; отказы ядра + канарейки; raw Ed25519 + `K_rev`; все шесть native `quarantined`; карточный пилот 12/24; строка 9 S02 невалидна как записана |
| [`2026-11-17-R8-answer-D.md`](2026-11-17-R8-answer-D.md) | 70 034 Б | `5b7369fa7e1c9a4a95f60bbe4bcf5020e24e064f52459919ac432c2c24e07401` | снимок `c63f3b8`; полная семантика один раз на promoter + digest-only runtime; **Windows QEMU `-accel whpx -M microvm`** (главный выброс); seccomp+cgroup+канарейки; SSHSIG; все шесть native `quarantined`; кодовый пилот на двух шаблонах; строка 6 S02 — `ok`, что противоречит пре-регистрации; CR снимается; есть иностранные токены и самоисправления |
| [`2026-11-17-R8-answer-E.txt`](2026-11-17-R8-answer-E.txt) | 72 409 Б | `87ef64a52376ce358dbdac744f073f32219518ae751b924ffa23b842b0e60d5d` | открывал снимок `c63f3b8`, читал код; полный host-валидатор + тонкий runtime; WSL2+KVM `microvm`; seccomp TRACE + ptrace; raw Ed25519 + узкий recovery; все шесть native `quarantined`; кодовый пилот 20/24; вывод `NOT READY` |

Это **не консенсус и не approval**. Ответы сходятся по Rust-канону, производному `active`,
точным байтам admission и комнате без сети, но расходятся по runtime-валидатору, таблице S02,
ускорителю и машине, наблюдению, ключу/recovery, legacy-шести, пилоту, порядку отказов,
статусам и манифесту. Сводка, проверка утверждений и развилки —
[`docs/R8-SYNTHESIS.md`](../../R8-SYNTHESIS.md).

## R9 — 23.11.2026

Вопросы: [`docs/EXTERNAL-QUESTIONS-R9-BRIDGES.md`](../../EXTERNAL-QUESTIONS-R9-BRIDGES.md) (31 вопрос, 8 блоков, снимок `ce7c64d`).
Дополнение после первого ответа: [`docs/EXTERNAL-QUESTIONS-R9-ADDENDUM.md`](../../EXTERNAL-QUESTIONS-R9-ADDENDUM.md).
Решения как технические вопросы: [`docs/EXTERNAL-QUESTIONS-R9.2.md`](../../EXTERNAL-QUESTIONS-R9.2.md) (V1–V6; указание владельца: это технические вопросы, не решения).

| файл | размер | SHA-256 | что внутри |
|---|---:|---|---|
| [`2026-11-23-R9-answer-A.md`](2026-11-23-R9-answer-A.md) | 89 628 Б | `cf36482b7b66748d95d002b0060f3b245856b19f266272125a962439f137f275` | все 31 вопрос R9; реестр открытых ссылок (BRIDGE/COMP/CHAIN/PDIFF/PROP/CONST/NC/ROOT); сквозная линия «один IR → одно ядро → три формы законов → конформность-гейт»; 3 repro-кандидата (пустой allowed_methods, транскрипция в policy_diff, шестой код K9_SCHEMA) |
| [`2026-11-23-R9.1-answer-A.md`](2026-11-23-R9.1-answer-A.md) | 55 935 Б | `cc9af0617f5b560b751208314781ba76987036bfac91c829e9322d60e887ee8f` | ответ A на R9.1: X1–X10 + S1–S10 артефактами (IR v1 JSON+Lean, каталог 7 законов/8 инстансов, скелет policy_eval, фикстура FACT-1); самокоррекции: parity-гейт закрыл 19/14, VM обязательна для /v1/net, три формы не покрывают гиперсвойства |
| [`2026-11-23-R9.2-answer-A.md`](2026-11-23-R9.2-answer-A.md) | 27 096 Б | ``59a37ece2e66ec4bd6351b23d426e5a04369a28d57e190ad1f32f904437ff4a3`` | ответ A на R9.2 (V1–V6): пустой allowed_methods = deny-all + замкнутый словарь методов; K12 принять; K11 uniform для не-native с конвертным допуском; head мигрировать к cards; V5/V6 — в файле |


Хеши проверяются командами:

```bash
sha256sum docs/research/external/2026-11-16-R5-answer-*.md
sha256sum docs/research/external/2026-11-17-R6-answer-*
sha256sum docs/research/external/2026-11-17-R7-answer-*
sha256sum docs/research/external/2026-11-17-R8-answer-*
sha256sum docs/research/external/2026-11-23-R9-answer-*
```
