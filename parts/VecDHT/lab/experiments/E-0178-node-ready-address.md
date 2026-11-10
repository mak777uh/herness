---
id: E-0178
hypothesis: H-0178
status: completed
base_commit: "177460a"
started: "2026-11-10T12:20:00+03:00"
finished: "2026-11-10T14:20:00+03:00"
environment: "машина boxes.dev `vecdht` (Ubuntu, 4 vCPU / 8 GB), rustc 1.99.1, cargo 1.99.1; хост контура — Windows 11, x86_64-pc-windows-gnu"
command: "bash lab/e0178-run.sh (два прогона на неизменном дереве; таблица lab/expectations/e0178.tsv)"
threshold: "все факты lab/expectations/e0178.tsv совпадают, WORST_RC=0, второй прогон STABLE=1; опровержение — любой факт разошёлся; неопределённость — прогон не запустился"
result: "два прогона на неизменном дереве 155647c: PRE_FIX_WILDCARD_LOOPBACK=1, POST_FIX_WILDCARD_LOOPBACK=0, POST_FIX_LOOPBACK_KEPT=1, POST_FIX_LOOPBACK_IS_LOOPBACK=1, LISTEN_TEST_RC=0, LISTEN_TEST_CASES=3, SELFCHECK_OK=1, REMOTE_OK=1, TRANSPORT_RC=0, WIRE_TOUCHED=0, SPEC_TOUCHED=0, PRODUCT_TOUCHED=1, EXPECT_FREEZE_EXIT=0 — 13 из 14; TEXT_EXIT=1 — UNKNOWN, страж не запускался без python (H-0179)"
verdict: supports
---

## Pre-registration (до прогона)

**Вопрос.** Объявляет ли `node run` в `NODE_READY listen=…` адрес, по которому узел реально
принимает входящие, когда `--listen` содержит wildcard, и сохраняет ли loopback, когда `--listen`
loopback.

**Oracle.** Носитель `lab/e0178-run.sh` печатает факты `LISTEN_*`; они сверяются с замороженной
таблицей `lab/expectations/e0178.tsv`.

**Порог зафиксирован здесь, до приёмочного прогона.** Таблица `lab/expectations/e0178.tsv` входит
пре-регистрационным коммитом; страж заморозки `lab/check-expect-freeze.py` обязан давать 0.

**Что считается успехом.** Все факты совпали, `WORST_RC=0`, второй прогон `STABLE=1`.
**Что считается провалом.** Любой факт разошёлся.
**Что считается неопределённостью.** Прогон не запустился (нет тулчейна, нет машины) — `UNKNOWN`.

**Отрицательный контроль встроен в порог.** Факт `POST_FIX_LOOPBACK_KEPT` требует, чтобы при
`--listen 127.0.0.1` loopback **остался**. Правка, которая вычищает loopback всегда, этот факт
провалит — то есть порог ловит не только недоделку, но и переделку.

**Честная оговорка.** Дефект измерен до объявления порога (2026-11-10, машина `vecdht`:
`ss` показывает `0.0.0.0:7771`, `NODE_READY` печатает `127.0.0.1`). Это разведка, а не приёмка:
приёмочным будет прогон **после** правки на неизменном дереве, и он же записывается в эту карточку.

## Прогон

Ожидается: `bash lab/e0178-run.sh` дважды на неизменном дереве.

## Результат

13 из 14 фактов совпали в двух прогонах на неизменном дереве `155647c`.

```
PRE_FIX_WILDCARD_LOOPBACK=1    на пине объявлялся 127.0.0.1
POST_FIX_WILDCARD_LOOPBACK=0   после правки — 10.255.255.254
POST_FIX_LOOPBACK_KEPT=1       отрицательный контроль: при --listen 127.0.0.1 loopback остался
LISTEN_TEST_RC=0               тест 3 из 3
SELFCHECK_OK=1 REMOTE_OK=1 TRANSPORT_RC=0
WIRE_TOUCHED=0 SPEC_TOUCHED=0 PRODUCT_TOUCHED=1 EXPECT_FREEZE_EXIT=0
```

Четырнадцатый факт `TEXT_EXIT` — `UNKNOWN`, а не провал: страж `check-text-clean.sh` в этом
окружении не запускался (нет `python`). Это отдельная находка `H-0179`/`E-0179`, и она закрыта.

## Вердикт

`supports`. Дефект был (на пине — loopback), после правки его нет, отрицательный контроль
сработал, `selfcheck` и `transport` не сломаны.

## Что это не доказывает

- достижимость узла снаружи: фильтр убирает ложное объявление, но не открывает NAT;
- прохождение двухмашинного сценария: он заблокирован платформой (boxes.dev не даёт UDP между
  машинами), и это отдельная находка, а не свойство правки;
- что `0.0.0.0` не нужен в `listen_addrs` для relay (`E-0145`): фильтр применяется к тому, что
  печатает CLI, а внутренний список не меняется.


