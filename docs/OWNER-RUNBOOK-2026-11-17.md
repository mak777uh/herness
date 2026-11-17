# OWNER-RUNBOOK — допуск инструмента `head` (17.11.2026)

> Это **не approval** и не инструкция «активировать сейчас». Документ фиксирует, что уже
> проверено на эфемерном test-only ключе, и какой чек-лист остаётся владельцу для настоящей
> церемонии. Агент не создаёт настоящий owner-ключ, не читает его и не делает production
> `active` без отдельного решения владельца.

## 1. Текущее состояние

- `head` — `candidate`; `active` пуст; `search` — `rejected`; шесть legacy-инструментов —
  `quarantined`.
- Настоящий owner-ключ не создавался; owner-подпись не выдавалась.
- `K9_proven` не выдан.
- Production-файлы `lab/tools/registry.jsonl`, `registry.events.jsonl`,
  `registry.state.json` не переписывались test-only репетицией и сухой owner-церемонией.
- Известный разрыв: `run_tool_g` не имеет ветки `head`. Даже после активации conversational
  loop не запустит `head`; запуск идёт через promoter. Это отдельная работа, не часть
  церемонии ключа.

## 2. Что можно запустить сейчас (test-only)

На Windows — verify/store и песочный реестр, без launch:

```text
python bin/activation_rehearsal.py --no-launch
```

В WSL — полная цепочка, включая `memfd + F_SEAL_* + execveat`:

```text
wsl.exe -e sh -lc 'cd /mnt/c/Users/Admin/Documents/Qoder/2026-11-16/7e4ba6fe/herness && python3 bin/activation_rehearsal.py --build --evidence research/outputs/ACTIVATION-REHEARSAL-R1-2026-11-17.txt'
```

Ожидание: `PASS activation rehearsal: 33/33` в WSL; на Windows без launch — `22/22`.
Normal — 3 строки/144 B/`line_cap`; outside-root — `S6_CLOSURE_BREACH`. В CI та же
цепочка идёт без `--build` (бинарь собирается отдельным шагом); это не другой порог,
а отсутствие проверок сборки. Рабочий каталог и ключ создаются вне репозитория и
удаляются, если не указан `--keep`; в evidence попадает только fingerprint, не seed.

Репетиция доказывает: подпись и шесть exact-byte digest проверяются; test-only без
`--allow-test-only` отвергается; promoter verify/store работает; test-only `admitted`
остаётся `admitted_inactive`; launch идёт без path fallback. Она **не** доказывает, что
владелец согласен, что ключ настоящий или что комната изолирует произвольный код.

Положительная ветка отдельно проверена песочным прибором (этап 12):

```text
python bin/owner_ceremony_dry_run.py --no-launch
wsl.exe -e sh -lc 'cd /mnt/c/Users/Admin/Documents/Qoder/2026-11-16/7e4ba6fe/herness && python3 bin/owner_ceremony_dry_run.py --build --evidence research/outputs/OWNER-CEREMONY-DRY-RUN-R1-2026-11-17.txt'
```

Ожидание: `45/45` на Windows без launch, `56/56` в WSL с launch. Прибор создаёт
**эфемерный** ключ с anchor `test_only:false` вне репозитория, проверяет манифест без
`--allow-test-only`, выполняет promoter verify/store и даёт песочный `head=active`,
`active=[head]`; production `head` остаётся `candidate`, production `active` пуст.
Добавлены негативные контроли: CLI `keygen` без `--test-only` и внутри репозитория;
изменённые манифест, подпись, anchor и fingerprint; срок; `seq=0`; отсутствующий
`test_only`; повтор ключа; integer вне JCS; повтор `seq` и разрыв `prev`; три test-only
варианта реестра. Это проверка положительной ветки, **не** approval и не настоящая
церемония: эфемерный ключ не является owner-ключом, а CLI `keygen` намеренно не умеет
создавать `test_only:false`.

Проверить готовый пакет можно read-only прибором (ничего не пишет, private key не читает):

```text
python bin/verify_owner_package.py --manifest <manifest.json> --sig <manifest.sig> \
  --anchor <anchor.json> --card <card.json> --source <source> --binary <binary> \
  --fixture <fixture-manifest.json> --policy <policy.json> --room <room.json> \
  --evidence <evidence.txt>
```

Без `--allow-test-only` пакет с `test_only:true` по умолчанию считается провалом.
`--allow-test-only` только осматривает песочный пакет и не делает его approval.
Self-test прибора: `python bin/verify_owner_package.py --self-test` → 5 сценариев
(годный пакет, test-only без разрешения, изменённая карточка, изменённое содержимое
фикстуры, изменённая подпись). Это единственная проверка, которая сверяет **sha256
содержимого** фикстуры; runtime `head` сверяет только размер — известный разрыв.

## 3. Что уже закрыто в реестре

`active` теперь требует **явного** `test_only:false` в теле события `admitted`.
`test_only:true`, отсутствие поля и не-bool значение дают `admitted_inactive` и не попадают
в `active`. Это защита от ложной активации тестового события, а не проверка подписи:
подпись проверяет promoter; реестр проверяет объявленные поля и остаётся fail-closed.

## 4. Чек-лист настоящей церемонии (выполняет владелец)

1. **Прочитать evidence и решить.** Минимум:
   `research/outputs/ACTIVATION-REHEARSAL-R1-2026-11-17.txt`,
   `research/outputs/HEAD-SLICE-R1-2026-11-17.txt`,
   `research/outputs/PILOT-GENERATOR-R1-2026-11-17.txt`,
   [`docs/DECISIONS-R8-2026-11-17.md`](DECISIONS-R8-2026-11-17.md).
2. **Выбрать формат ключа.** Текущий verifier принимает raw Ed25519 RFC 8032 с доменным
   префиксом `herness-admission-v1`. Если владелец хочет SSHSIG/FIDO2, это сначала
   отдельное решение и изменение verifier, а не тихая подмена формата.
3. **Создать ключ офлайн.** На машине без агента и без доступа агента к seed; ключ и backup —
   вне репозитория. Команда настоящего `keygen` **намеренно не реализована**:
   `python bin/admission.py keygen` умеет только `--test-only` и отказывается писать ключ в
   репозиторий. Использовать test-only ключ как owner-ключ нельзя.
4. **Зафиксировать anchor.** Публичный ключ, fingerprint, `min_epoch`, `revoked_epochs`,
   `expected_prev`. Fingerprint передать владельцу по отдельному каналу и сверить глазами;
   anchor хранить как защищаемый файл, не в git, если владелец не решил иначе.
5. **Собрать манифест из точных байтов.** Существующая команда умеет это:
   `python bin/admission.py manifest --tool head --card ... --source ... --binary ... --fixture ... --policy ... --room ... --anchor ... --out ...`.
   Для настоящего допуска **не** передавать `--test-only`. Проверить, что digest'ы относятся
   к той же репрезентации файлов, которая будет у promoter (CRLF/LF — объявленная граница).
6. **Подписать detached.** Подпись — над `DOMAIN + "\n" + canonical(manifest)`, без
   pretty-переформатирования. Если используется внешний подписывающий инструмент, он должен
   дать те же байты и hex-подпись; иначе verifier откажет.
7. **Проверить до активации.**
   `python bin/admission.py verify --manifest ... --sig ... --anchor ...` — без
   `--allow-test-only`; затем `python bin/promoter.py verify ... --store ...`. Ожидание:
   подпись и шесть digest сходятся, `test_only` отсутствует или false, store не содержит seed.
   Дополнительно — независимый read-only отчёт
   `python bin/verify_owner_package.py ...` (см. §2): он сверяет те же шесть digest,
   карточку, содержимое fixture-манифеста и evidence, ничего не записывая.
8. **Записать evidence.** Команда, rc, digest'ы, fingerprint, дата, кто и на каком хосте
   подписывал. Evidence — не seed и не приватный ключ.
9. **Добавить событие `admitted`.** Append-only событие в `registry.events.jsonl`:
   `schema=herness-registry-event-v1`, `seq`, `prev`, `type=admitted`, `tool_id=head`,
   `body.owner_signed=true`, `body.test_only=false`, `body.admission_digest`,
   `body.evidence_digest`. Перед append владелец **вне канала** сверяет `key_fingerprint`
   и anchor: реестр не проверяет подпись и не содержит allowlist owner-anchor, поэтому
   событие само по себе не доказывает, что ключ — owner-ключ. Отдельного CLI append сейчас
   нет: это отдельный проверяемый шаг, а не рекомендация править журнал вручную без
   проверки `seq`/`prev`.
10. **Вывести и проверить состояние.**
    `python bin/registry_state.py --write`, затем `--check`, `--show`, `--authorize head`.
    Только после этого `head` может стать `active`; `registry.state.json` в Rust
    пересобирается и проверяется тестами.
11. **Прогнать CI.** `python bin/hs.py gates --profile auto`,
    `python bin/verify_claims.py --fast`, Rust-тесты в WSL; push и дождаться success.
12. **Откат.** `python bin/admission.py revoke --anchor ... --epoch N --i-am-owner` повышает
    `min_epoch` и добавляет epoch в `revoked_epochs`; старые манифесты обязаны отвергаться.
    Это изменение anchor, а не подписанное событие: хранить anchor и backup нужно так,
    чтобы агент не мог их подменить. При сомнении — остановиться и не активировать.

## 5. Стоп-условия

Остановиться, если: требуется передать seed агенту или в контекст; тестовая подпись или
песочная owner-церемония выдаётся за owner-подпись/approval; событие `admitted` имеет
`test_only:true` или не имеет поля; кто-то предлагает ослабить гейт/порог; launch
подменяется путём или TCG; в evidence попадает приватный ключ; production-файлы реестра
меняются без события и проверки.

Границы: этот runbook не является approval, не создаёт ключ и не доказывает изоляцию
комнаты. `K9_proven` остаётся невыданным.
