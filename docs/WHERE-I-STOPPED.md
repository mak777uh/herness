# ГДЕ ОСТАНОВИЛСЯ — 25.11.2026 (rolling-карта смены)

> **Обновление 25.11.2026, CI-RUST-OFFLINE-R2.** E-0078 сохранён открытым историческим RED: его sealed критерий требовал на пустом WSL cache именно `ed25519-dalek`, а новая изолированная проба первой дала missing `hex`; post-fetch observation был 14/14 и 7/7, но критерий не подменён. Отдельный E-0079/C-0354 запечатан и закрыт: ровно один `cargo fetch --locked` в core-rs перед Selftest; focused и manifest selection 5/5 на Windows/POSIX; повторный пустой WSL cache дал baseline 13/14 и 5/7 с `hex`, после fetch — 14/14 и 7/7; исторический CI 45499098427 отдельно подтвердил `ed25519-dalek`; Cargo.lock и production Rust неизменны. Lab 79/7, seals 56/56, prereg 68/68; после C-0354 verify_claims --fast 315/0, coverage 347/347 anchored и strict 196/344 = 0.57, ANCHORED_WEAK. Граница: полный CI-PASS и independent review не заявлены; bridge unshare, Windows-only N/A, C-0340, 21 absolute link, directory durability, strict coverage и Lean↔Rust equivalence остаются открытыми; N/A не PASS; activation и публикация не выполнялись. Следующий срез — фактический CI-run после commit, затем остальные residuals и W12/W20/W25.

> **Обновление 25.11.2026, SELFTEST-DIAGNOSTICS-R1.** E-0077/C-0353 закрыт: failed suite теперь печатает summary, note и последние не более 30 строк уже сохранённого output; successful suite не печатает payload. Исторический RED 6/6 failures сохранён; focused 6/6 на Windows/POSIX. Implementation commit `685df94` прошёл независимые Windows и POSIX clean clone: W18 14/14, diagnostics 6/6, seals 54/54, lab 77/7, prereg 66/66; полный Windows selftest rc=0 при пустом status; после регистрации C-0353 verify_claims --fast 314/0, coverage 346/346 anchored и strict 195/343 (0.569), `ANCHORED_WEAK`. Прибор уже точно назвал development-scope W18 FAIL до commit и не затронул thresholds, N/A, corpus или rc. Граница: сами CI residuals не исправлены; полный POSIX selftest и полный CI-PASS не заявлены; independent review, Windows directory durability, strict claims coverage и Lean↔Rust equivalence остаются открытыми; N/A не PASS; activation и внешняя публикация не выполнялись. Следующий срез — фактический CI-run `685df94`, затем приоритетные residuals и W12/W20/W25.
> **Обновление 25.11.2026, W18-CLEAN-CLONE-R1.** Snapshot gate E-0073/E-0074 закрыт: baseline `f292734` воспроизводимо дал Review3 8/9 и stale pilot rc=1; implementation `7e5a618` прошёл отдельные Windows и POSIX clean clone с W18 controls 14/14, Review3 9/9, V1/V6 и V4 без провалов, pilot/registry rc=0, seals 51/51, `lab validate` 74/7 и пустым worktree. Checkout `loopmod.rs` закреплён как 191435 байт/3647 CRLF/`74c77403…`, Git blob отдельно 187788/0/`b2ffec5d…`; V6 `ChainInstances.lean` закреплён exact LF `2478/0/8cfe7c4d…` после исторического Windows RED `b32843d`. Stale pilot baseline принят только sealed correction `9727c890…` с fail-closed мутантами; registry seq=9 указывает candidate `head` на canonical card, seq=8 сохранён, `active=[]`. Закрыты E-0073/E-0074/C-0351, evidence — `research/outputs/W18-CLEAN-CLONE-R1-CLOSURE.txt`; coverage 344/344 anchored, strict 193/341, `ANCHORED_WEAK`. Граница: независимый review W18 не проводился; полный CI-PASS, absolute Windows links, C-0340 platform behavior, POSIX selftest residuals, Windows directory durability и Lean↔Rust equivalence не закрыты; N/A не PASS; activation и внешняя публикация не выполнялись. Следующий срез — разбор CI residuals и W12/W20/W25, без ослабления gates.

> **Обновление 25.11.2026, PREREG-CORRECTION-OVERLAY-R2.** После snapshot closure общий gate обнаружил C-0082: sealed E-0074 не содержал шесть обязательных методических полей. E-0075 R1 сохранён открытым историческим RED 5/8 и prereg 63/64; scope не расширялся задним числом. Отдельный E-0076/C-0352 реализует hash-verified source-bound inheritance всех отсутствующих обязательных полей с приоритетом явных полей overlay. Focused 8/8 на Windows/POSIX, prereg check 65/65 sensitivity, `check_artifacts C-0352` rc=0, `verify_claims --fast` 313/0, seals 53/53, `lab validate` 76/7; coverage 345/345 anchored, strict 194/342, `ANCHORED_WEAK`. Исходные E-0074/E-0075/source/sidecars не переписаны; missing/wrong-digest/traversal/incomplete-source/unrelated-incomplete остаются fail-closed. Evidence — `research/outputs/PREREG-CORRECTION-OVERLAY-R2-CLOSURE.txt`. Независимый review, полный CI-PASS и activation не заявлены; N/A не PASS.

> **Обновление 25.11.2026, W18 FINAL CLOSURE.** Closure commit `081b3a9` отправлен в `origin/main` вместе с `b32843d` и `7e5a618`. На чистом Windows worktree полный Python manifest — 76 suites/966 checks/0; W18 clean-clone 14/14. Финальные Windows/POSIX clean clone `081b3a9` дали W18 14/14, Review3 9/9, pilot/registry rc=0, seals 53/53, lab validate 76/7, prereg 65/65 и E-0076 focused 8/8 при пустом status; временные клоны удалены. CI run `45494108369` завершился failure: Rust/admission/plugin прошли, но POSIX selftest residuals, C-0147 transport error, C-0340 platform behavior, 21 absolute Windows link и два verify_claims FAIL остаются. Полный CI-PASS не заявлен; следующий срез — эти residuals, без ослабления gates.

> **Обновление 24.11.2026, W03-LIFECYCLE-R1-REVIEW3.** Финальная correction-попытка E-0070 закрыта локально: общий Python↔Rust corpus, строгая terminal-token boundary, structured per-run refusal, unknown-cost/final-overspend fail-closed, полный call→result→step lifecycle, on-disk fresh proof и разделение fresh/resume подтверждены. Review3 9/9 и regression 32/16/11 на Windows/POSIX без W03 N/A; native Windows и WSL Rust 1/1 + 4/4; полный Windows manifest 78 suites/1341 checks/0 провалов; выбранный POSIX W03/Rust aggregate 10/522/0. Независимый review PASS, substantive findings нет; gates 31/33 с двумя прежними N/A, fast probes 17/17, seals 49/49, verify_claims --fast 311/0, coverage ANCHORED_WEAK (strict 192/340 = 0.56). Закрыты E-0070/C-0350 и instrument corrections E-0067/E-0071/E-0072; исторические E-0066/E-0068/E-0069 остаются open как FAIL/NEEDS_CHANGES. Evidence — `research/outputs/W03-LIFECYCLE-R1-REVIEW3-CLOSURE.txt` и `research/outputs/W03-LIFECYCLE-R1-REVIEW3-INDEPENDENT-VERDICT.txt`. Граница: QEMU/provider, resume idempotency/retry, clean-clone/CI, Windows directory durability, production activation и Lean↔Rust equivalence не закрыты; N/A не PASS; внешняя публикация не выполнялась. Следующий технический срез — W18 clean-clone/HEAD-bound после разрешённого commit/push и фактического CI-run.

> **Обновление 23.11.2026, BRIDGE-REDIRECT-AUTH-R1.** Подтверждённая граница секрета закрыта: `urllib` следовал upstream `301/302/303` и переносил `Authorization` провайдера на redirect target (same- и cross-origin, синтетическая канарейка; RED — 32 провала). `Bridge.forward` теперь использует opener с `_NoRedirectHandler`; любой upstream `3xx` даёт фиксированный `502 {"error":"upstream redirect refused"}` без чтения тела и `Location`. GREEN: 10/10 target requests=0 и target Authorization=0, source Authorization=1, обычный upstream 200 сохранён; канарейка/Location/target отсутствуют в ответах, `bridge.log` и stdout/stderr. Регрессия: bridge 8/8, key isolation 7/7, win isolation 28/28, net namespace 16/16, общий selftest rc=0. Закрыты E-0043/C-0335, evidence — `research/outputs/BRIDGE-REDIRECT-AUTH-R1-2026-11-23.txt`. Граница: urllib/loopback, не V5 strict HTTP; TLS/proxy/DNS/конкретный провайдер не покрыты; не approval/activation/K9. Изменение `bin/bridge.py` разрешено владельцем; commit/push не запрошены и не выполнялись.

> **Обновление 23.11.2026, HEAD-CARD-CANONICAL-R1 (V4).** Единственная рабочая карточка `head` — canonical `lab/tools/cards/head.json` (`tool-card-v1`), перемещённая без read-resave: SHA-256 `361ad2ecd421fae57f7ec3ae4c5e7e5bc8befd4d6d21b68573c23a70e699fe97`, 5832 байта, 313 CRLF. Legacy `head_legacy` сохранён байт-в-байт в `lab/tools/archive/` со `status=superseded`; drafts пуст. RED до перемещения — 11 провалов; независимый GREEN — focused 17/27/33/18 без провалов, parity rc=0. Итоговая интеграция: selftest rc=0, `verify_claims --fast` 297/0, `lab validate` 44 эксперимента, gates 31/33 с двумя честными N/A (нет `runs/` и индекса журналов). `tool_card.validate` требует jsonschema Draft202012Validator и смысловые проверки для v1; `validate_activation` отвергает superseded/legacy; `card_atoms` явно запрещает v1→v0. Readers переключены на canonical, required-only fallback удалён и в `new_tool`, jsonschema 4.26.0 закреплён в CI, V4-тесты включены в selftest. Закрыты E-0044/C-0336, evidence — `research/outputs/HEAD-CARD-CANONICAL-R1-2026-11-23.txt`. Граница: карточка не доказывает соответствие Rust-исполнению; IR-перевод остаётся долгом; append-only registry history не переписывалась; не owner approval, production activation или K9_proven. Commit/push не запрошены и не выполнялись. Следующий отдельный срез — V5; K12/K11 и IR не начинать без решений владельца.

> **Обновление 23.11.2026, R9 — опросник «мосты из первых принципов».** Собран `docs/EXTERNAL-QUESTIONS-R9-BRIDGES.md` — вопросы для внешних ИИ-моделей от владельца (ИИ — новая технология, все подходы меняются, смотреть из первых принципов). Код не менялся; ссылки снимка — `ce7c64d`. Ответы сохраняются байт-в-байт в `docs/research/external/`, синтез — R9-SYNTHESIS.

> **Обновление 23.11.2026, R9.1 — первый внешний ответ и дополнение.** Ответ A на R9 сохранён байт-в-байт (`docs/research/external/2026-11-23-R9-answer-A.md`, SHA-256 `cf36482b7b66748d95d002b0060f3b245856b19f266272125a962439f137f275`), его позиции сжаты в развилки; собран `docs/EXTERNAL-QUESTIONS-R9-ADDENDUM.md` (X1–X10 — независимым моделям, S1–S10 — дожим A, V1–V5 — решения владельца). Проверено по коду: (1) `chain.py:101–104` — пустой `allowed_methods` у downstream отключает проверку методов, нужен вердикт владельца V1; (2) `policy_diff.py` сверяет Lean с Python-переносом Rust-функций; дрейф 19/14 закрыт `check_policy_parity.py`, но зазор «транскрипция vs настоящий Rust» остаётся; (3) в `chain.py` шесть кодов K9 (включая `K9_SCHEMA`), в дано R9 было пять. Ждут решений владельца: V1 семантика пустого списка методов, V2 K12 `no_untrusted_control`, V3 юрисдикция K11 внутри комнаты, V4 две карточки head, V5 протокол границы комната↔мост. Код не менялся.
> **Обновление 23.11.2026, R9.1-дожим и замер TCB.** Ответ A на дополнение сохранён байт-в-байт (`docs/research/external/2026-11-23-R9.1-answer-A.md`, SHA-256 `cc9af0617f5b560b751208314781ba76987036bfac91c829e9322d60e887ee8f`): самокоррекции (parity-гейт закрыл 19/14; VM для /v1/net обязательна уже сейчас; три формы законов — только trace-safety, гиперсвойства K7 вне fold), артефакты S1–S10 (IR v1, скелет policy_eval, фикстура V1, семантический конверт, K12, ветка r=0.28). Гейт «ссылки» больше не сканирует docs/research/external/* — сырые ответы байт-в-байт (decision-log, `3e6097f`). Новый FACT-CODE: `chain.py:79` — `proven` самодекларируемый boolean без привязки к proof-артефакту; кандидат V6. Замер рукописной поверхности — `research/outputs/TCB-LOC-R1-2026-11-23.txt`: Lean 444 + Python 974 + Rust 3134 = 4552 строк в трёх представлениях одной семантики (гипотеза «на порядок» не опровергнута). Ждут решений владельца V1–V6. Собран `docs/EXTERNAL-QUESTIONS-R9.2.md` — V1–V6 переформулированы как технические вопросы для моделей (указание владельца).
> **Обновление 23.11.2026, R9-SYNTHESIS.** Ответы независимых моделей B и C на R9.2 сохранены байт-в-байт (SHA-256 `022cbf52…4830`, `e53b0280…87bd`); синтез и план — `docs/R9-SYNTHESIS.md`. Консенсус 3/3: V1 deny-all + обязательное поле (семантика покрытия); V2 K12 — поправка конституции; V3 K11 uniform + scoped-worker — поправка конституции; V6 proven → объект с subject-хешем (сейчас) и proof-package с запуском pinned Lean (при оживлении admission); V4 — код на стороне C: живая карточка — tool-card-v1 в drafts/, cards — legacy tombstone (промоушен сейчас); V5 — B/C: канонический HTTP-subset сейчас, проба VSOCK-WIN-R1 пре-регистрируется (ожидаемо RED). Этап 0 (V1→V6→V4→V5, ~4–6 дней) — без поправок конституции; Этап 1 — по «да» владельца (ADR K12, ADR K11, церемония ключа); Этап 2 — IR-ядро. Решение владельца: реализация, новых брифов не нужно.

> **Обновление 23.11.2026, R9 V6 — proof-binding вместо boolean.** V1 из baseline `31a7b561` уже закрыт; продолжение реализовало V6. `bin/chain.py` больше не принимает `proven:true`: downstream требует закрытый объект `{kind, artifact, sha256, subject_sha256}`, kind — `lean-instance`; subject — канонический JSON всей цепочки без bridge-level `proven`, artifact — безопасный repo-relative путь и exact-byte SHA-256. Отказы разнесены по `K9_PROVEN_BAD_FORMAT`, `K9_PROVEN_MISSING_ARTIFACT`, `K9_PROVEN_HASH_MISMATCH`, `K9_PROVEN_SUBJECT_MISMATCH`; strict CLI отвергает duplicate keys, float/NaN и unsafe integer. 43/43 теста, пять V1-фикстур сохранили вердикты, machine report `research/proofs/k9-chain-instances.json` детерминирован (`--check` rc=0). Lean `Proofs` и новые `ChainInstances` собраны под rc2, аксиомы стандартные, все три negative-control модуля отвергнуты; мутант boolean guard дал 23 провала и восстановлен байт-в-байт. `verify_claims --fast` — 295 исполняемых утверждений, 0 провалов; полный live-прогон не зелёный (17 старых environment-dependent отказов, C-0334 проходит). Selftest rc=0; финальные gates 31/33, два N/A названы (журналы, run-index; Rust уже оценён после сборки бинарника полным прогоном). Закрыты E-0042 и C-0334, evidence — `research/outputs/V6-PROOF-BINDING-R1-2026-11-23.txt`. Граница: привязка не доказывает истинность доказательства, pinned Lean checker'ом не запускается, соответствие downstream-кода модели не проверено; `K9_model_checked`, не `K9_proven`. На момент закрытия V6 изменения были локальными; публикация в main — отдельное действие по явному поручению владельца. Следующий шаг этапа 0 — V4: промоушен `drafts/head-v1.draft.json` в `cards/head.json` с legacy tombstone и обновлением parity reader.

> **Обновление 21.11.2026, K9 — модель композиции (`K9_model_checked`).**
> По прямому выбору владельца («K9: модель композиции») собрана модель
> `proofs/Proofs/Composition.lean`: T1 — замыкания складываются и остаются
> внутри границы; T2 — пошаговой проверки недостаточно (`secretStep` и
> `netStep` по отдельности не утекают, их композиция утекает); T3/T4 —
> утечка даёт отказ, безопасная композиция исполняется; T5/T6 — downstream
> без доказательства делает цепочку недопустимой. Аксиомы только стандартные;
> `CompositionNegative` отвергнут (три ложных утверждения, `decide` их
> опроверг). Checker `bin/chain.py` — policy-only: допустимая цепочка
> `ok=true, rc=0`; отказы `K9_ADJACENT_REQUIRED`, `K9_CHAIN_UNPROVEN`,
> `K9_DOWNSTREAM_MISSING_DEST`, `K9_DOWNSTREAM_MISSING_METHOD`,
> `K9_TAINT_ESCAPE` — `rc=3`; 16/16 проверок, `python tests/test_chain.py`
> `провалов: 0` (C-0332, E-0040,
> `research/outputs/K9-COMPOSITION-R1-2026-11-21.txt`).
> Граница: проверяются объявленные замыкания и адреса мостов, не код
> downstream и его egress; taint только `secret:*` и сеть; скрытые каналы
> и соответствие Rust-кода модели не покрыты. Это `K9_model_checked`, не
> `K9_proven`; active пуст, настоящий owner-ключ не создавался. Коммит
> локальный, наружу ничего не публиковалось — нужен явный «да» владельца.
> Старая копия `C:\111\harness` разошлась с remote (6 локальных коммитов
> new10 WIP + 98 remote): WIP сохранён в ветке `wip/new10-flake-2026-11-15`
> и в stash, `main` приведён к `origin/main` (`774d187`).
> Перед коммитом подняты локальные артефакты старой копии (без ослабления
> проверок): `runs/accept/journal-default-threshold.bin` мигрирован
> HSJ1→HSJ2 (13 событий, seq/kind/payload сохранены, пересчитан только CRC
> по ADR-0056; тот же честный прогон теперь читается приёмкой), rust-артефакт
> пересобран (`141 passed, 0 failed`), `research/claims-coverage.json`
> пересчитан под C-0332 (325 утверждений, 325 закрытых, строгое покрытие 0.56).
> Итог: `python bin/hs.py selftest` зелёный, `python bin/hs.py gates` —
> 33 из 33, без N/A.

> **Обновление 18.11.2026, барьер записи внешнего помощника (Landlock + low-IL).**
> `bin/net.py` больше не может писать в комнату/репозиторий. Перед разбором
> запроса и до сети ставится Landlock (ABI ≥ 3, права записи), единственный
> разрешённый путь — `runs/net`; при ABI < 3 — отказ `fs-sandbox` до сети.
> На `/mnt/c` (9p/drvfs) Landlock не узнаёт существующие inode, поэтому журнал
> и `session.json` открываются до барьера и пишутся через fd; новых путей это
> не открывает. Красный репро: копия HEAD пишет `room/protected.txt`
> (`SANDBOX=absent, PROTECTED_WRITE=1`, текст `PWNED`). После: `PROTECTED_WRITE=0`
> (errno 13), `STATE_WRITE=1, JOURNAL=1, SESSION_RESULTS=1, RC=0`; ABI=0 —
> отказ до fetch, rc=3; плечи D/E на 9p — журнал и сессия через fd, защищённая
> запись отвергнута; Windows low-IL — `PROTECTED_WRITE=0, STATE_WRITE=1`, 28 ok
> (C-0331, E-0039, `research/outputs/NET-FS-WRITE-BARRIER-R1-2026-11-18.txt`).
> Регрессии: `test_bridge.py` 8/8, `test_bridge_key_isolation.py` PASS,
> `test_bridge_net_namespace.py` PASS, гейты локально — 31/33 (N/A 2),
> `verify_claims --fast` — 292/292, `lab validate` — реестр связен.
> Граница: барьер ставится после старта интерпретатора; чтение и сеть не
> ограничены; на 9p через fd пишутся только два файла состояния; прямой запуск
> `net.py` вне моста на Windows не покрыт; `runs/net` остаётся downstream-
> записью; симлинки, жёсткие ссылки и гонки не покрыты; это не K9; настоящий
> ключ не использовался, active пуст, K9_proven нет.
> Следующее — K9 (`composition_preserves`).
> **Проверенный handoff-коммит:** `7edd412`; CI `44350168720` — success, все 6 job'ов.
> docs-правки после него не меняют код и проходят тот же workflow.

> **Обновление 18.11.2026, Windows-изоляция `/v1/net` — low-IL (H-0010).**
> Windows-ветка больше не запускает `net.py` обычным ребёнком: `bin/win_lowil.py`
> создаёт restricted-токен, ставит `TokenIntegrityLevel = S-1-16-4096` (Low),
> запускает `CreateProcessAsUserW` с pipes, NUL на stdin и job object
> kill-on-close; `runs/net` опускается до метки Low, иначе low-процесс не запишет
> журнал (это downstream-данные, не первая комната). Плечо A (medium напрямую)
> видит канарейку в PEB моста — `FOUND=1, FOUND_ANY=1`; плечо B через мост —
> `200, NET_PROBE=1, IL_RID=4096, FOUND=0, FOUND_ANY=0, ERR=OpenProcess err=5`;
> C без лаунчера — 503 «не найден», D с нерабочим — 503 «не работает», `net.py`
> в C/D не исполняется; 24 ok, провалов 0 (C-0330, E-0038,
> `research/outputs/WINDOWS-NET-LOWIL-R1-2026-11-18.txt`).
> Регрессия: `test_bridge_key_isolation.py` PASS на Windows (allowlist; теперь
> через low IL), `test_bridge.py` 8/8, `test_bridge_net_namespace.py` PASS в WSL
> (Linux-ветка не менялась), реальный `net.py links` под low IL — rc=3 no-page,
> журнал пишется. Граница: Windows-only; token-файл, командная строка, файловая
> система, сеть, ptrace-аналог и K9 не покрыты; проба кэшируется; low-состояние
> `runs/net` доступно low-процессам; настоящий ключ не использовался, active пуст,
> K9_proven нет. Коммит кода: `b819546`; гейты локально — 31/33 (N/A 2),
> `verify_claims --fast` — 291/291, `check_autonomy --staged` — ok.
> Следующее — запрет записи внешнего в комнату 1 и K9.

> **Обновление 18.11.2026, гигиена EOL и названная причина 503.**
> Пять JSON переписывались с CRLF при неизменном содержимом: `verify_claims --fast`
> внутри гейтов запускал `score_h2`, `build_reviews_index`, `review_debt` и
> `make_vectors`, а `Path.write_text` без `newline` на Windows даёт CRLF. Добавлен
> `newline="\n"`: после повторного прогона `crlf=0, bytes_equal_head=True` для всех
> пяти, гейты 31/33 N/A 2, пробы 17/17
> (`research/outputs/LF-WRITERS-2026-11-18.txt`). Запинненные CRLF файлы не тронуты.
> Прибор R2 усилен: плечи C и D проверяют причину отказа («unshare не найден» /
> «не работает»), 16/16 вместо 14; amendment в пре-регистрации, критерий не менялся
> (`research/outputs/BRIDGE-NET-NAMESPACE-R2-2026-11-18.txt`, C-0329, E-0037).
> Граница: общего стража переводов строк нет; Windows, файловая система/сеть/token/
> ptrace не покрыты; это не K9 и не активация.
> **Проверенный handoff-коммит:** `08583f8`; docs-правки после него не меняют код
> и проходят тот же workflow.

> **Обновление 18.11.2026, `/v1/net` в PID-namespace: решение A принято и реализовано.**
> Владелец выбрал A («давай а»), поэтому `bin/bridge.py` изменён: на Linux `net.py`
> запускается через `unshare -U -p -f --mount-proc`; без `unshare` — `503` и никакого
> запуска (fail-closed). Красный репро: подставной помощник видел ключ (`FOUND_ANY=1`),
> PATH без unshare давал 200 и исполнял `net.py` (4 провала); после — `NET_PROBE=1,
> FOUND_ANY=0`, без unshare `503` и маркера исполнения нет (11/11), регрессия allowlist
> на Windows PASS (C-0328, E-0036,
> `research/outputs/BRIDGE-NET-NAMESPACE-R1-2026-11-18.txt`). CI этого среза упал:
> после включения namespace C-0324 на Linux-раннере перестал видеть исполнение
> `net.py`. Добавлена одноразовая проба `unshare` (C-0329, E-0037): найденный, но
> нерабочий `unshare` теперь даёт `503` и не запускает `net.py` (до пробы — 200 с
> error, 1 провал; после — 14 ok; затем усиление до 16 ok с проверкой названной
> причины «не найден»/«не работает»); env-тест C-0324 на Linux получил
> shim launcher'а, потому что его предмет — окружение, а не namespace.
> `research/outputs/BRIDGE-NET-NAMESPACE-R2-2026-11-18.txt`. Граница: Windows не
> покрыт (H-0010), файловая система, сеть, token-файл и ptrace не изолированы;
> WSL-прогон под root; проба кэшируется; это не K9.
> Следующее — Windows-механизм изоляции, запрет записи внешнего в комнату 1 и K9.
> **Проверенный handoff-коммит:** `551e179`, CI `44303600442` — success, все 6 job'ов.
> Перед ним: `f1e4106` (реализация A; CI `44301185581` — красный по C-0324 на Linux,
> разобран в C-0329), `551e179` (проба unshare и R2); docs-правки после него не меняют
> код и проходят тот же workflow.

> **Обновление 18.11.2026, метка внешнего в комнате и честная сводка Rust-тестов.**
> Разрыв K9 закрыт со стороны комнаты: `HttpBridge::net_request` теперь возвращает
> `[external_untrusted]` и на успешный `output`, и на отказ; красный репро (старый
> `model.rs` + новый интеграционный тест) дал 2 FAILED, после — 141/141 (C-0325,
> `research/outputs/ROOM-EXTERNAL-TAINT-R1-2026-11-18.txt`). При этом найден дефект
> прибора: `bin/rust_tests.py` печатал «провалов: 0» при красном интеграционном тесте,
> потому что брал первое вхождение; теперь суммирует по всем бинарникам, 4/4 (C-0326).
> Мост `bin/bridge.py` не менялся. Остаётся: метка — текст, а не политика исполнения;
> модель может её проигнорировать; ответ провайдера не помечается; запись внешнего в
> комнату и K9 не доказаны; token-путь в argv и same-uid `/proc` остаются на Windows.
> Изоляция внешнего помощника на Linux сделана в C-0328 (PID-namespace); следующий
> технический шаг — Windows-механизм и запрет записи внешнего в комнату 1, а не
> ослабление реестра.

> **Обновление 18.11.2026, граница комнаты 1 и внешних (после уточнения владельца).**
> Владелец уточнил порядок: харнес — инструмент моделей; владелец только передаёт важное
> (пароли, ключи, личное) в первую комнату; модель сама пишет инструменты, сохраняющие её
> безопасность; внешние мосты подключаются к инструментам, но после внешнего всё
> недоказано и в комнату 1 не возвращается. Поэтому ближайший технический шаг — не новая
> церемония ключа, а K6/K9 на границе: мост не получает ключ, внешний результат помечается
> и не пишется обратно. Один канал уже закрыт: `/v1/net` наследовал `HS_BRIDGE_KEY`;
> после allowlist-окружения канарейка не появляется ни в ответе, ни в журнале (C-0324,
> `research/outputs/BRIDGE-KEY-ISOLATION-R1-2026-11-18.txt`). Остаётся token-путь в argv и
> same-uid доступ через `/proc`; метка `external_untrusted` сделана на границе комнаты
> (C-0325); запрет записи внешнего в комнату 1 остаётся. Текущий реестр строже конституции: `active` требует подписи для
> всех; если модель должна сама активировать инструменты вне комнаты 1, это отдельное
> решение владельца, а не тихое послабление.

> **Обновление 18.11.2026, два разрыва допуска закрыты (без активации).** Promoter теперь
> связывает `--job` с проверенным admission: `root`, fixture-манифест, шесть digest-путей,
> manifest/sig/anchor, запрет per-case override; при расхождении — отказ до store/launch.
> Job передаётся хосту точными байтами через запечатанный memfd и `--job-fd`, а не путём.
> Runtime `head` сверяет и размер, и **sha256 содержимого** фикстуры; `MAX_HASH_BYTES = 8 MiB`
> даёт `K4` вместо неограниченного чтения, хешируются те же байты, которые выдаются.
> Проверки: Rust lib — **133 passed** (2 новых: same-size/different-bytes → `K11`,
> выше предела → `K4`); promoter self-test — **18/18 Windows, 21/21 WSL**; активационная
> репетиция — **34/34 WSL, 22/22 Windows**; owner-церемония — **57/57 WSL, 45/45 Windows**;
> HEAD-SLICE host+QEMU — **PASS**. Evidence:
> `research/outputs/PROMOTER-JOB-BINDING-R1-2026-11-18.txt`,
> `HEAD-EDGE-R1-2026-11-17.txt`, `ACTIVATION-REHEARSAL-R1-2026-11-17.txt`,
> `HEAD-SLICE-R1-2026-11-18.txt`; C-0322/C-0323. Файл `...-17.txt` не менялся: его
> digest заморожен в `PILOT-GENERATOR-R1`; повтор после sha256 — отдельный `...-18.txt`.
> **Известные разрывы (не закрашены):** promoter не реализует полную семантику карточки;
> реестр не проверяет подпись и не имеет allowlist owner-anchor; `run_tool_g` не имеет ветки
> `head`; предел 8 MiB означает отказ для большой фикстуры, а не потоковое чтение.
> Production `head` — `candidate`, `active` пуст; настоящий owner-ключ не создавался,
> admission не подписан, `K9_proven` не выдан, наружу ничего не публиковалось.
> **Следующее действие — владелец:** церемония ключа и подпись admission либо отказ; после
> подписи — событие `admitted`, production `active` и отдельный живой эксперимент `head`.
> **Проверенный handoff-коммит:** `3a055ca` (CI `44282496337` — success, все 6 job'ов).
> До него: `a999037` (реализация), `567254f` (C-0322 в CI без cryptography).
> Docs-правки после него: `5ceeff6`, CI `44282714085` — success, все 6 job'ов.

> **Более ранний снимок (R8/этап 12; 17.11.2026).** **Обновление 17.11.2026, R8 реализован.** Актуальный handoff —
> [`docs/SELF-TOOLING-2026-11-16.md`](SELF-TOOLING-2026-11-16.md), §1.11–1.12.
> **Последняя точка:** `fe143b6` (сухая owner-церемония в песочнице); CI
> `44163715508` — **success**, все 6 job'ов, включая новый шаг `admission`. Перед ним:
> `700d516` (байтовый откат проб и CRLF-пин карточки), `8c30f27` (CI-гейты),
> `c063ded` (test-only репетиция и evidence), `a95fe58` (guard `test_only:false`);
> ранее `edbf085` (CRLF-пиннинг) и `fe27d07` (handoff). Реализация R8 — этапы 0–12:
> `e82dc22` (решения и словарь v3), `d95c533` (репро и policy), `96470e9` (write),
> `318eb9e` (legacy), `729fee8` (KVM_RUN), `f790ef5` (admission/promoter), `8d1f542`
> (head slice), `a6e7292` (реестр), `92963cf` (пилот), `a95fe58` (guard test-only),
> `c063ded` (репетиция), `8c30f27` (CI), `700d516` (байтовый откат проб и CRLF-пин
> карточки), `fe143b6` (сухая owner-церемония).
> Этап 11 — test-only активационная репетиция: **33/33 PASS** в WSL,
> guard явного `test_only:false`, песочный `admitted_inactive`, promoter launch;
> CI job `admission` — **31/31** без `--build` (бинарь собирается отдельным шагом);
> evidence — `research/outputs/ACTIVATION-REHEARSAL-R1-2026-11-17.txt`, C-0317.
> Этап 12 — положительная ветка в песочнице: эфемерный ключ с anchor `test_only:false`,
> promoter без `--allow-test-only`, песочный `active=[head]`; **30/30 PASS** в WSL,
> **28/28** в CI без `--build`, **19/19** на Windows без launch; production `head` —
> `candidate`, `active` пуст; evidence —
> `research/outputs/OWNER-CEREMONY-DRY-RUN-R1-2026-11-17.txt`.
> Runbook — [`docs/OWNER-RUNBOOK-2026-11-17.md`](OWNER-RUNBOOK-2026-11-17.md).
> Первый CI `44155903515` был красным только по представлению: проба гейта откатывала
> `HEAD-SLICE-R1.json` текстом и нормализовала CRLF→LF, а карточка head не была
> запиннена и получала LF. `700d516` вернул байтовый откат и запиннил карточку CRLF,
> не ослабляя exact-byte сверку и не меняя запечатанные digest'ы.
> **Проверенный handoff-коммит:** `d0fb60d`, CI `44165290004` — success; docs-правки
> после него не меняют код и проходят тот же workflow.
> Решения Q11–Q18/F04/A01 — [`docs/DECISIONS-R8-2026-11-17.md`](DECISIONS-R8-2026-11-17.md);
> выбраны агентом по делегированию владельца «делай сам все поочерёдно», не approval и не
> изменение конституции. Q1–Q10 не переоткрывались:
> [`docs/DECISIONS-R5-2026-11-16.md`](DECISIONS-R5-2026-11-16.md).
>
> **Что закрыто измерением:** KVM_RUN в WSL2 (`-M microvm -accel kvm`, QMP
> `present/enabled=true`, tracepoint, отрицательный контроль без `/dev/kvm`);
> HEAD-SLICE-R1 — PASS (8/8 критических контролей, normal 3 строки/144 B/`truncated=true`,
> 3 повтора, host+QEMU); PILOT-GENERATOR-R1 — PASS (20/20 спецификаций, 16/16 + 8/8
> мутантов, 3/3 генерации и прогона). Полные evidence — §1.11 SELF-TOOLING и
> `research/outputs/`, `research/kvm/`.
>
> **Что НЕ сделано:** настоящий owner-ключ не создан и не читался; admission не подписан;
> `head` остаётся candidate и отвечает `S13_TOOL_INACTIVE`; `registry.state.json` —
> `active` пуст; ни один инструмент не активирован; `K9_proven` не выдан; наружу ничего
> не публиковалось. Положительная ветка этапа 12 проверена только эфемерным ключом:
> это не approval и не замена церемонии.
>
> **Следующее действие — владелец:** прочитать evidence и решения, провести церемонию
> ключа и подписать admission (или отказать). После подписи — registry event и отдельный
> эксперимент на живой `head`; это новый порог, не продолжение HEAD-SLICE-R1.
>
> Разделы ниже — предыдущий снимок `ec07951` и блок R8-до-реализации; они сохранены как
> история, а не текущее состояние.

**HEAD предыдущего снимка:** `ec07951` — на входе было `2d556ee` (15.11); за ту смену 6 коммитов.
Дерево было чистое, синхронно с origin, CI зелёный (13 прогонов подряд после 383 падений).

## Снимок состояния

| что | команда | результат |
|---|---|---|
| гейты (клон, CI) | `python bin/hs.py gates` | **exit 0** — профиль `auto`: 30 из 32, N/A 2 с причиной |
| гейты (full) | `python bin/hs.py gates --profile full` | exit 1 ровно по отсутствию `runs/` |
| покрытие | `python bin/coverage.py CLAIMS.md` | 305 утверждений, 305 закрытых, anchored 1.00, strict 0.56 |
| Rust-тесты | `python bin/rust_tests.py` (WSL) | 75 из 75 |
| Lean | `python bin/lean_wsl.py` | агрегат собирается, 11 теорем, оба NC отвергнуты |
| CI | `gh run list -L 1` | success — 13 подряд |
| реализации | v0.1.0, LICENSE MIT | релиз создан |

## Что сделано за смену (по коммитам)

```
ec07951 docs: F-0094 — собственный README не проходит собственную мерку
31f9a3c test: VERIFY-REPO-R3 — поверхность прибора на бенчмарках есть, порог не понижен
92f4498 fix: verify_repo не читает блоки кода и не считает параметр командой
8a7cf8b feat: herness verify — измерение проверяемости чужого README
193ee3d fix: 31 замена путей к чекауту + гейт переносимости (F-0093, C-0305)
8373d07 docs: бриф R2 — 12 вопросов о доказательствах, capability и генерации
01f710a feat: карточка инструмента (валидатор+рендер) и DESIGN-0002
3e0c16e feat: версия формата журнала сверяется с бинарником комнаты (C-0308)
647dd34 feat: проверка достижимости Lean-модулей (C-0310) + разбор marfagenez
4dd3329 feat: карточка сводится в атомы nomos и сверяется с политикой (C-0312)
93a1d55 docs: предложение — харнесс пишет мосты под задачи (PROPOSAL-0001)
a9bec06 docs: анкета владельцу + отдельный бриф для поиска
511d063 docs: RESEARCH NOTE — накопитель (раунды 1-3, два независимых ответа, R2)
0c4f326 docs: раунд 5 — R3 результаты (два независимых ответа, находки)
6c13710 docs: бриф R3 — 8 вопросов о синхронизации представлений
```

Полный список с описанием — `research/RESEARCH-NOTE.md` (единый накопитель).

## Статус фаз

| фаза | статус | где |
|---|---|---|
| **Фаза 0** — прибор честен, CI зелёный | **закрыта** | `lab/prereg/PHASE0-CI-GREEN.json`, 13 CI подряд |
| **VERIFY-REPO-R1** — 5 чужих README | **закрыта PASS** | `research/verify/INDEX.md` |
| **VERIFY-REPO-R2** — таблицы | **закрыта FAIL** (0 табличных чисел), расширение отменено | `lab/prereg/VERIFY-REPO-R2.json` |
| **VERIFY-REPO-R3** — бенчмарки | **закрыта FAIL** (2 из 5, порог 3), поверхность подтверждена | `research/verify-r3/INDEX.md` |
| **DESIGN-0002** — карточка, генератор | **срез сделан** (`bin/tool_card.py`, `C-0311`); генератор `new_tool.py` — следующий шаг | `docs/DESIGN-0002-tool-generation.md` |
| **PROPOSAL-0001** — мосты от задач | **предложение** — не решение, ждаёт пре-регистрации | `docs/PROPOSAL-0001-task-written-bridges.md` |
| **RESEARCH NOTE** — 5 раундов, 4 внешних ответа | **накапливается** | `research/RESEARCH-NOTE.md` |
| **R3 ответы** — синхронизация Lean/Rust, изоляция | **получены, не применены** | `docs/EXTERNAL-QUESTIONS-R3.md`, ответы в RESEARCH-NOTE раунд 5 |
| **Анкета владельцу** | **отправлена, не заполнена** | `docs/OWNER-QUESTIONS-2026-11-16.md` |

## Что проверено (команда → rc → артефакт)

- `python bin/hs.py gates --profile auto` → **0** → 30/32, N/A 2
- `python bin/hs.py gates --profile full` → **1** — ровно 2 причины «нет runs/»
- `python bin/hs.py selftest` → **0**
- `python bin/rust_tests.py` → **0** (75 тестов, WSL)
- `python bin/check_probe_coverage.py` → **0** (ПРИБОР ЧЕСТЕН)
- `python bin/readme_numbers.py` → **0**
- `python bin/seal.py verify-all` → **0** (17 печатей)
- `python bin/check_lean_imports.py` → **0** (8 модулей, 5 корней)
- `python bin/binary_version.py --check` → **0** (HSJ2 совпадает)
- `python tests/test_verify_repo.py` → **0** (14 проверок)
- `python tests/test_tool_card.py` → **0** (9 проверок)
- `python tests/test_card_atoms.py` → **0** (10 проверок)
- `python tests/test_binary_version.py` → **0** (4 проверки)
- `python tests/test_lean_imports.py` → **0** (5 проверок)
- `node plugin/test/journal.test.js` → **0** (9 проверок)

## Что НЕ проверено

- CI на ubuntu: `cargo test --lib` — **первое измерение было на пуше, зелёное** (но не повторялось
  многократно). Lean и QEMU-комната в CI не запускаются.
- `crash-resume` и живая приёмка комнаты — не перемерялись (образ `acc.img` gitignored).
- `H-0180` мост Lean → C → Rust — пре-регистрация есть, прогона нет.
- NC с witness — предложено (R3-4), не реализовано.
- Переписывание 6 инструментов под карточки — задача владельца ответила «все», но работа не начата.

## Открытые находки (живые)

| # | суть | следующий шаг |
|---|---|---|
| F-0027 | crash-resume к раннему крашу | требует QEMU + образ |
| F-0074 | флаки N04 | улики при FAIL есть, 3×N04 не прогонялись |
| F-0084 | QEMU guestfwd на Windows | отложено (альтернатива virtio-serial) |
| F-0093 | 35 из 48 `.lean` не компилировались — **закрыто**, но ~15 скриптов с чужими путями остались | `bin/check_abs_paths.py` ловит, но не все исправлены |
| F-0094 | собственный README не проходит собственную мерку (7 чисел, 0 команд) | записано, исправление требует переписывания README |
| N6 | SSRF: литерал 198.18/15 + rebinding | `SSRF-HARDEN-R1` — не пре-регистрировано |
| H-0180 | мост Lean→C→Rust | пре-регистрация есть, прогона нет |

## Что НЕ решено (владельцу)

| id | суть | следствие |
|---|---|---|
| O1 | цель на две недели: автогенерация / пользователи / ядро | порядок всех очередей |
| O4 | первый тип задачи для моста | вертикаль |
| O5 | `--freeform` в v1: да или нет | дизайн генератора |
| O6 | переписать 6 инструментов под карточки — да, но работа не начата | объём рефакторинга |
| O7 | конституция харнеса: пул правил-законов, исполняемый | новый артефакт |
| O9 | письма авторам — не надо | черновик остаётся как артефакт |
| O10 | публиковать разборы — да, если нет ключей | зона A расширена |
| O11 | части публиковать — да, дорабатывать и там, и там | синхронизация контекстов между машинами |

## Текущее следующее действие (17.11.2026, после R8)

1. `python bin/hs.py gates` — ожидается rc=0, профиль `auto`, N/A с причиной; `N/A` не «зелёный».
2. Q1–Q10 приняты владельцем; запись — [`docs/DECISIONS-R5-2026-11-16.md`](DECISIONS-R5-2026-11-16.md).
   Словарь отказов v2, черновик схемы, scorecard, фикстура и `HEAD-SLICE-R1` созданы.
3. R8: пять сырых ответов и синтез в репозитории. Владелец читает
   [`docs/R8-SYNTHESIS.md`](R8-SYNTHESIS.md) и решает Q11–Q18, F04 и A01; ответы R8 —
   рекомендации, не approval. Перед принятием утверждения проверяются по коду, расхождения —
   failing-репро.
4. До решений не реализовывать `head`, admission, комнату, promoter, миграцию и генератор;
   не менять policy/registry/схему/конституцию. Допустимы документы, failing-репро тесты и
   сохранение улик.
5. Сначала — дешёвые обратимые починки с репро и тестом: parity policy JSON↔Rust, write-scope
   нормализация, `NO_XDEV`, потолок `read`/`head`, молчаливые пропуски `search`/`list`, ложный
   `active` в реестре. Каждая отдельным коммитом, без ослабления гейта.
6. Затем — измеренная комната (один `-accel kvm`, без fallback, `KVM_RUN` как событие); после
   Q11/Q12/Q13 — Rust-срез `file_read_stream` и `HEAD-SLICE-R1` по запечатанному порогу; FAIL
   сохраняется. После Q15/A01 — promoter с проверкой допуска; после Q18 — производный `active`
   и `search` вне допуска; после Q16 — пилот генератора. `K9_proven` не выдавать ни на одной
   ступени.

Актуальный handoff с деталями — [`docs/SELF-TOOLING-2026-11-16.md`](SELF-TOOLING-2026-11-16.md).

## Точное следующее действие предыдущего снимка (ec07951)

1. `python bin/hs.py gates` — убедиться, что rc=0.
2. Ответы на R3 (уже в RESEARCH NOTE раунд 5) — применить:
   a. NC с witness (R3-4) — переписать все 3 негативных контроли.
   b. Синхронизация Lean wildcard (R3-1) — до DRT.
   c. BridgeNegative в агрегат (R3-5) — после witness.
3. Анкета владельцу — когда придёт ответ, перенести в `owner-preferences.json`.
4. Далее по RESEARCH NOTE раунду 5: DRT, provenance, comprehension-тест.

## Читать в порядке

1. `AGENTS.md` — правила.
2. `docs/SELF-TOOLING-2026-11-16.md` — актуальный handoff: что сделано, где остановились.
3. Этот файл — текущая шапка и история предыдущего снимка.
4. `docs/DECISIONS-R5-2026-11-16.md` — принятые Q1–Q10 и что они не доказывают.
5. `docs/EXTERNAL-QUESTIONS-R8.md` — открытые развилки Q11–Q18, F04, A01 и AUDIT.
6. `docs/R8-SYNTHESIS.md` — синтез пяти ответов R8, проверенные факты и рекомендуемый порядок.
7. `docs/R7-SYNTHESIS.md` — синтез пяти ответов R7; исторический слой.
8. `docs/R6-SYNTHESIS.md` — синтез шести ответов R6; исторический слой.
9. `docs/research/external/` — сырые ответы R5–R8 с печатями; не решения.
10. `docs/EXTERNAL-QUESTIONS-R7.md` — 11 вопросов предыдущего круга.
11. `docs/EXTERNAL-QUESTIONS-R6.md` — 22 вопроса круга до него.
12. `docs/EXTERNAL-QUESTIONS-R5.md` — 24 вопроса круга до него.
13. `docs/EXTERNAL-QUESTIONS-R4.md` — 45 вопросов круга до него.
14. `docs/CONSTITUTION-v0-2026-11-16.md` — K1–K11 и юрисдикция.
15. `research/RESEARCH-NOTE.md` — исследования R1–R3.
16. `docs/DESIGN-0002-tool-generation.md` и `docs/PROPOSAL-0001-task-written-bridges.md` — карточка,
    генератор и мосты.

## Стоячие правила

- пре-регистрация с порогом ДО прогона, потом код, потом вердикт
- гейт не ослабляется; смена порога — отдельный ADR
- отрицательный результат остаётся результатом
- число без команды — не результат
- в каждом отчёте — «что это не доказывает»
- секреты не в контекст и не в git
- ничего наружу без явного «да» владельца
- N/A — не «зелёный»: проверка не состоялась
