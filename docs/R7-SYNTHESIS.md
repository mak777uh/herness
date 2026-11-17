# R7 — синтез пяти ответов и развилки

**Дата:** 17.11.2026. **Снимок кода:** базовая линия `9c8af80`, проверяемый снимок
`3d988f8` (дельта — только docs, код тот же). **Вход:** пять сырых ответов R7,
сохранённых байт-в-байт в [`docs/research/external/`](research/external/README.md):
[A](research/external/2026-11-17-R7-answer-A.txt),
[B](research/external/2026-11-17-R7-answer-B.txt),
[C](research/external/2026-11-17-R7-answer-C.txt),
[D](research/external/2026-11-17-R7-answer-D.md),
[E](research/external/2026-11-17-R7-answer-E.txt).

**Статус.** Это рекомендации внешних моделей, а не решения владельца и не approval.
Решения Q11–Q18 принимает владелец; код, `policy.json`, `registry.jsonl`, схема,
словарь отказов и пре-регистрация в этом круге **не менялись**. Совпадение нескольких
ответов тоже не является согласованием: это только сужение развилки.

---

## 0. Что проверено, а что нет

Прочитаны все пять ответов целиком. Независимо проверены по снимку:

- `core-rs/src/loopmod.rs`: `KNOWN_TOOLS`, `MAX_FILES`/`MAX_FILE`/`MAX_READ`, `POLICY`
  (14 правил), `policy_allows`, `resource_matches`, `resource_of`, `resolve_in`,
  `tool_read_in`, `tool_search_in`, `tool_list_in`, `tool_write_in`, `write_beneath`,
  `tool_seal`, `tool_netprobe`, `tool_net`, `run_tool_g`, ветка non-Linux;
- `lab/tools/policy.json` (19 правил), `lab/tools/registry.jsonl` (шесть записей,
  все `version: 3`, все `status: "active"`), `lab/tools/cards/head.json`,
  `lab/tools/drafts/head-v1.draft.json`, `lab/tools/tool-card-v1.schema.json`,
  `lab/prereg/HEAD-SLICE-R1.json`, `bin/card_atoms.py`, словарь v2;
- фикстура [`lab/fixtures/model_visible/head-slice.txt`](../lab/fixtures/model_visible/head-slice.txt):
  471 Б, 10 строк, SHA-256 `b5157f948c0833f80ac96ad64916c93d747e07df253801dfcd5674e59ce76850`,
  длины строк с LF: 41, 46, 57, 53, 46, 60, 58, 40, 46, 24; первые три строки — 144 Б,
  вторая заканчивается на байте 87;
- `python bin/card_atoms.py --check lab/tools/cards/head.json` → `rc=3`,
  `[uncovered] a1 /mnt/**`; без пути (`--check head`) → `rc=2` «нет файла»;
- первичные источники: `openat2(2)` (`RESOLVE_NO_SYMLINKS` implies
  `RESOLVE_NO_MAGICLINKS`; `RESOLVE_NO_XDEV` запрещает переход точки монтирования) и
  `landlock(7)` (флаги audit logging — ABI v7 / Linux 6.15; ядро 6.6 их не имеет).

Не проверены и не выдаются за факт: прогоны QEMU/KVM, ptrace и Landlock-профилей,
которые описывают ответы; их точные номера строк; JCS-векторы; воспроизводимость их
сборок. Там, где ответ ссылается на собственный прогон, это помечено как «по ответу».

---

## 1. В чём пять ответов согласны

1. **Канон семантики карточки — Rust, Python не выдаёт допуск.** Все пять выбирают
   Rust-реализацию (в разной упаковке: библиотека, CLI, бинарь в промоторе) и оставляют
   Python (`card_atoms.py`/`tool_card.py`) ненормативным: генератор векторов, линт,
   вторая реализация, dev-only. F-вариант «Python + receipt» отвергнут всеми пятью.
   Степень runtime-перепроверки расходится (§2.1).
2. **`file_read_stream` читает сырые байты из FD с жёстким потолком.** Все пять:
   `max_bytes_read` — потолок безопасности, `line_count` — лимит API; `BufReader::take`
   и `read_to_string` не годятся; за бюджетом не читается ни один байт; частичная
   строка не выдаётся; `truncated` и `stop_reason` обязательны и не врут; невалидный
   UTF-8 — отказ, а не «частичный вывод». В R7 все пять также **запрещают
   EOF-зонд сверх бюджета** (C в R6 предлагал `probe_one_byte` с отдельным счётчиком;
   в R7 C это отменил).
3. **Комната — WSL2 + KVM, `microvm`, без сети и host mounts.** Все пять выбирают
   WSL2+KVM как security-путь v0 (C — при условии прохождения измерений; только C
   допускает WHPX как запасной путь с отдельной учётной записью). TCG — только
   `simulation`, не security. Все требуют: один `-accel kvm` без fallback, `-nic none`,
   `-nodefaults`/`-no-user-config`, отсутствие 9p/virtiofs/host mounts, доказательство
   ускорителя (QMP `query-kvm`, `/dev/kvm` в fd QEMU, гостевая сигнатура), digest
   QEMU/ядра/initramfs.
4. **Наблюдение — измерение, а не доказательство.** Никто не выдаёт
   `observed_code_effects ⊆ card_effects` за доказательство для произвольного кода.
   «Нет событий» — не зелёный: слепой монитор обязан дать провал (`S7_GATE_BLIND` или
   `observation_invalid`). Расхождение «стена отказала, трасса молчит» и наоборот —
   провал в любую сторону. Self-report инструмента никогда не считается независимым.
5. **Один путь допуска.** Owner-ключ подписывает admission; recovery не подписывает
   admission и не должен становиться вторым путём. Потеря ключа — fail-closed;
   восстановление — backup того же ключа или физическая замена trust anchor с полной
   повторной процедурой.
6. **`active` — производный предикат.** Хранимое `"status": "active"` не признаётся;
   источник истины — append-only журнал событий/манифестов; указатель — кэш, который
   перепроверяется; генератор пишет только в candidate inbox; registry пишет только
   promoter. `search` не должен оставаться активным (Q8).
7. **Admission привязан к точным байтам.** JCS (RFC 8785), domain separation,
   подпись владельца над каноническими байтами, SHA-256 по card/source/binary/template/
   deps/toolchain/policy/room, проверка на хосте до запуска, путь и «красивый JSON» не
   являются идентичностью.
8. **Генератор запускается только после зелёного ручного `head`.** Нужны канонический
   валидатор, admission, комната, наблюдение, замороженные до прогона пороги и held-out,
   запись всех попыток, подпись владельца. Авто-approval нет.
9. **`K9_proven` в v0 запрещён; `K11_admitted` ≠ «безопасен».** Все пять различают
   доказательство/свидетельство и полномочие; допуск не отключает стены.
10. **Порядок отказов: вычислить все нарушения, выдать один primary.** K11 — первым;
    для пути вне корня класс данных не запрашивается; сырой путь вне корня не пишется
    в журнал; метрики считают все коды в `violations[]`, а не только выданный.

---

## 2. Где расходятся: развилки Q11–Q18 и не только

### 2.1. Q11/F01 — канонический валидатор и его runtime-роль

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| канон | Rust | Rust в том же крейте | Rust-крейт `card-check` | Rust-бинарь `semantic_check` | Rust-библиотека `herness-card-validator` |
| Python | интерфейс/тесты | генератор векторов и оракул миграции | вторая реализация на векторах, затем выводится | dev-only convenience | ненормативный линт/векторы |
| runtime | повторная проверка **admission** перед запуском | не фиксировано | **повторная семантическая проверка** при загрузке карточки | runtime **доверяет** подписанному манифесту, семантику не повторяет | только перепроверка привязки digest'ов, не полная семантика |
| привязка к бинарю | promoter сверяет digest собранного артефакта | promoter сам собирает и хеширует | promoter собирает из source, `card.effects ⊆ template.max_effects` | `validate_binding(card, template_binary)` | admission-манифест + runtime-сверка digest |

Сверх JSON Schema все пять требуют: непустой scope по kind, запрет wildcard/`..`/NUL,
`process_spawn=false`, `max_bytes_read` не выше потолка, data classes только
`public`/`model_visible`, коды отказов только из словаря, `examples` с ok и refusal.
C формулирует это как таблицу V01–V13 и требует по положительному и отрицательному
вектору на каждое правило; D — 12 правил и мутантов; E — 12 правил и корпус
`lab/conformance/*.json`; A/B — списки без полного корпуса.

**Цена выбора.** Если runtime повторяет полную семантику (C), обход promoter'а записью
в каталог не даёт `active`; цена — тот же валидатор в runtime и его версия в TCB.
Если runtime доверяет манифесту (D), нужна жёсткая защита каталога и указателя; иначе
подмена файла карточки после допуска не ловится. Позиция E (только digest-привязка)
ближе к D, но сохраняет обнаружение дрейфа байтов.

**Проверенный факт против всех:** `bin/card_atoms.py` работает со старым форматом
`closure.fs.*`, а `tool-card-v1` описывает `effects.*`/`limits.*`. Прямой вызов
`card_atoms` на новой карточке — не проверка новой семантики (A, E; подтверждено
чтением скрипта и карточек).

### 2.2. Q12/S02 — одна таблица `file_read_stream`

Согласовано: сырой `read`, потолок, отсутствие зонда сверх бюджета, отсутствие
частичной строки, явные `truncated`/`stop_reason`, отказ на невалидном UTF-8,
CRLF-нюанс фиксируется явно. Расходятся пять осей:

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| как подтверждается EOF | `read()==0` в пределах бюджета; иначе `truncated=true` | `fstat.size` при открытии: `recv==size` → EOF, без лишнего read | `read()==0` в пределах бюджета; иначе консервативно `truncated` | `read()==0`; иначе `truncated=true` | `read()==0`; зонд только в пределах бюджета, иначе `truncated=true` |
| счётчики | один `bytes_read` | **два**: `bytes_received` (read) и `bytes_consumed` (до последней выданной строки) | один `bytes_read` (включает read-ahead) | один `bytes_read`, но псевдокод вычитает хвост, а «поправка» говорит «не вычитать» — внутреннее противоречие | один `bytes_read` (включает read-ahead) |
| `truncated` | true при `line_limit`/`byte_limit`; false при EOF | `bytes_consumed < size_at_open`; false, если N-я строка ровно на EOF | `stop_reason != eof`; **true** даже если N-я строка с LF ровно на EOF | true при ByteCap/LineCount; false при Eof | `stop_reason != eof`; true на `cap == size`, если EOF не подтверждён |
| cap меньше первой строки | 0 строк, `ok`, `truncated=true` (по таблице) | 0 строк, `ok`, `truncated=true` | 0 строк, `ok`, `byte_cap` | 0 строк, `ok`, `ByteCap` | **отказ `K4_RESOURCE_LIMIT`**, 0 выданных байт |
| CRLF | CR снимается перед выдачей, входит в `bytes_read` | CR — обычный байт; снимается только завершающий CR | CR **остаётся** в содержимом строки (как POSIX `head`) | CRLF — разделитель, CR снимается | CRLF — разделитель, CR снимается при выдаче |
| невалидный UTF-8 | отдельный код `S2_ARTIFACT_ENCODING` (предложение) | `S?_ENCODING`, поправка словаря — решение владельца | detail `input_invalid_utf8` до поправки; код — в S05 | **`K6_DATA_CLASS_UNKNOWN`** | интерим `S1_SCHEMA` + detail `content_encoding`; предложение `S2_CONTENT_ENCODING` v3 |
| `output_bytes` | отдельный лимит, поведение при переполнении не определено | не фиксировано | четвёртая причина `output_cap`: останов на границе строки | не фиксировано; `output_bytes` и `max_bytes_read` — разные оси | кадр > `output_bytes` → `K4_RESOURCE_LIMIT`, без частичного JSON |
| CHUNK | не фиксирован (в примере 4096) | `min(CHUNK, cap−recv, size−recv)`; конкретное значение не зафиксировано | `CHUNK=4096` — часть digest семантики | 4096 | `CHUNK=4096` — константа шаблона |

**Что важно для пре-регистрации.** Числа для fixture сходятся у A/C/E на трёх
сценариях: `N=3, cap=4096` → 3 строки, `bytes_read=471`, `truncated=true`; `N=200,
cap=64` → 1 строка, `bytes_read=64`, `truncated=true`; `N=200, cap=4096` → 10 строк,
`bytes_read=471`, `truncated=false`, `eof`. B даёт те же `lines`, но `bytes_consumed`
вместо `bytes_read`; D даёт те же значения при исправленном счётчике. Расхождение
остаётся в **точном EOF-момере** и в `truncated` на границе — это и есть решение Q12.

**Ошибки внутри таблиц** (не позиции, а противоречия): D в псевдокоде вычитает хвост
из `bytes_read`, затем «поправка» требует не вычитать; строка 7 той же таблицы
исключает байты неполного символа из `bytes_read`, что противоречит поправке. A в R6
обещал `éé` при cap внутри multibyte; в R7 A это исправил (частичная строка не
выдаётся). B при `size_at_open` может объявить EOF раньше, если файл вырос; B сам
помечает это ограничением v0.

**Наше уточнение:** `max_bytes_read=65536` и `output_bytes=8192` — разные оси, но
неопределённость при переполнении вывода реальна. `output_cap` (C) и `K4` на кадр (E)
— два способа её закрыть; D/B оставляют пробел. Это решение владельца, а не деталь.

### 2.3. Q13/R01 — комната, загрузка и seccomp

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| путь | WSL2+KVM | WSL2+KVM | WSL2+KVM при измерениях, WHPX — fallback с отдельным пользователем | WSL2+KVM | WSL2+KVM, иначе срез не закрыт (WHPX не security-fallback) |
| seccomp | `CONFIG_NET=y`, фильтр ставит сам инструмент (`harden_self`) | `CONFIG_NET=y`, без NIC; seccomp обязан запретить сокеты | `CONFIG_NET=y`, без NIC/INET; `harden_self`; супервизор передаёт fd 3 | **seccomp нет**: NET-less ядро + Landlock + `harden_self` | `CONFIG_NET=y`; фильтр ставит launcher и **наследуется через execve**; PID1 проверяет `Seccomp==2` до выдачи fd |
| процессы | `pids.max=2` (supervisor + tool); дочерние запрещены | `pids.max=1` в cgroup инструмента; supervisor вне | `max_tool_processes=1`, `room_processes=2`, `RLIMIT_NPROC=1` + seccomp | `pids.max=2` (PID1 + tool) | `pids.max=1` в cgroup инструмента; инфраструктура вне TCB-счётчика |
| ввод fixture | initramfs (не сказано, как менять на прогон) | initramfs | **`-add-fd` + virtio-blk RO**, образ передан открытым fd | initramfs; способ подачи fixture на прогон не описан | initramfs; fixture внутри образа |
| доказательство KVM | QMP + `/proc/pid/fd` + guest dmesg | QMP + fd + CPUID-сигнатура | QMP + fd + CPUID + 20 прогонов + `chmod 000 /dev/kvm` | QMP + guest dmesg | QMP + fd `kvm-vm`/`kvm-vcpu` + debugfs счётчики + cmdline |

**Общая фактическая база:** seccomp-фильтр зависит от `NET`
(`research/outputs/seccomp-net-dependency.txt`), `pre_exec` даёт `ENOSYS`
(`research/outputs/pre-exec-seccomp.txt`). Отсюда четыре ответа выбирают NET=y и
установку фильтра процессом/launcher'ом; D выбирает NET-less и отказывается от
seccomp. Это не косметика: без seccomp сетевой запрет держится только на `-nic none`,
а fork-запрет — на cgroup/Landlock.

**Цена каждого пути.** NET=y добавляет сокет-поверхность в гостевом ядре; её нужно
закрыть seccomp-запретом `socket/connect` (A/B/E). NET-less убирает сокеты, но
лишает seccomp и оставляет Landlock, который не фильтрует `clone/execve` (D). C
покупает fd-передачу и `-add-fd` ценой virtio-blk в TCB. E покупает наследование
фильтра ценой launcher'а в TCB и проверки `Seccomp==2`.

**Проверенный факт:** host-side Landlock не является границей для других процессов
хоста; он ограничивает только процесс и его потомков. Поэтому «Landlock закрывает
TOCTOU между хешем и exec» (D) неверно для чужого писателя. Это ошибка D, не
развилка.

**Не решено и требует замера:** работает ли вложенный KVM в WSL2 (наличие
`/dev/kvm` — не доказательство `KVM_RUN`); загрузится ли `microvm` под KVM на этой
машине; какой именно QEMU/ядро/initramfs; кто монтирует fixture и как он попадает
в гостя; входит ли `microvm` в QEMU virtualization use case (C сомневается).

### 2.4. Q14/R02 — механизм наблюдения

| ответ | механизм | что считается независимым | главный риск |
|---|---|---|---|
| A | ptrace супервизора в госте + журнал | событие supervisor'а | ptrace меняет поведение, не видит скрытые каналы |
| B | **отказ ядра** (seccomp/Landlock/cgroup) + канарейки | `enforced_by_kernel`; `observed_independent` в v0 **не выдаётся** | наблюдение ограничено известными попытками; нет трассы |
| C | ptrace-супервизор + seccomp TRACE + калибровка | `observed_in_guest`, не глобальное `independent` | TCB трассировщика, слепые зоны таблицы |
| D | Landlock audit + QMP + init-счётчик | Landlock denial | **на ядре 6.6 Landlock audit flags недоступны** (ABI v7/6.15); QMP видит события VM, не syscall; init-счётчик не видит `execve` внутри процесса |
| E | ptrace/strace под PID1 + kernel-счётчики + канарейки | трасса на канале, недоступном инструменту | полнота таблицы классификации; ptrace-эквивалентность |

Согласовано: канарейка на каждый прогон, `dropped_events==0`, `unclassified==0`,
негативные контроли, расхождение стены и трассы — провал. Расходится **уровень
притязания**: B честно ограничивает v0 отказом ядра и не выдаёт
`observed_independent`; A/C/E выдают независимое свидетельство трассы; D — самый
слабый механизм и с несуществующим на 6.6 audit.

**Проверенный факт:** Landlock audit logging добавлен в ABI v7 (Linux 6.15); ядро
6.6.114.1 их не имеет. Поэтому D-R02 в текущей комнате не запускается как описано.

### 2.5. Q15/R03 — owner-ключ, recovery и trust anchor

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| топология | один signing root; backup того же ключа | operational + **recovery**, который подписывает **trust-anchor update** и отзыв, но не admission | один ключ, без recovery root; backup того же | signing + **recovery**, который может отозвать/ротировать, но не подписывать admission | один operational + backup; recovery-root, минтищий ключи, отсутствует |
| формат | «сырой» Ed25519 RFC 8032, доменный префикс | SSHSIG + KRL | SSHSIG (namespace) | SSHSIG | SSHSIG |
| trust anchor | pin в конфиге promoter'а; git — справочно | файл владельца/конфиг promoter'а; git read-only | вне агентского дерева; git read-only | **compiled-in digest** + keyring в репозитории | файл вне дерева (Windows ACL или WSL root-owned) + pinned digest |
| анти-откат | epoch + revocation state | epoch/seq в состоянии promoter'а; `expires_at` информативен | `seq`/epoch/pointer; срок вторичен | `monotonic_counter` + `prev_manifest_digest` | `min_epoch` + монотонное состояние, отзыв поднимает epoch |

Согласовано: admission подписывает только owner-ключ; потеря не даёт автодопуска;
отзыв и срок — разные вещи; старый манифест не оживает после откката.

**Опасное расхождение B:** recovery-ключ, который подписывает trust-anchor update,
транзитивно может установить новый operational-ключ и затем подписать им admission.
Если церемония нового ключа не требует физического присутствия владельца и не
фиксируется отдельным журналом, это второй путь допуска. B не описывает такую
церемонию явно. D разрешает recovery только revoke/rotate, но «rotate» тоже требует
церемонии; у D она описана как полная. A/C/E вообще не вводят отдельный recovery-ключ.
Это решение владельца, а не деталь реализации.

**SSHSIG vs «сырой» Ed25519.** SSHSIG выигрывает у четырёх (B/C/D/E): namespace,
готовый `ssh-keygen -Y verify`, меньше самодельной криптографии. A выбирает сырой
RFC 8032 + OpenSSL. Если владелец выбирает SSHSIG, «голый» verifier по `prefix‖JCS`
не проверит подпись: нужно проверять SSHSIG-фрейминг (namespace `herness-admission-v1`,
hash sha512) или использовать `ssh-keygen -Y verify`. Смешивать два формата нельзя.

### 2.6. Q18/T01 — производный `active`, legacy-шесть и указатель

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| состояния | candidate/validated/admitted/active/needs_revalidation/quarantined/rejected/revoked/expired/superseded | candidate/admitted/revoked/quarantined/rejected/expired/needs_revalidation; `active` — функция | unadmitted/quarantined/admitted_inactive/active/revoked/expired/stale/rejected | FSM register→admitted→rejected/revoked/expired | proposed→quarantined→checked→admitted_confined→needs_revalidation→revoked |
| legacy-шесть | все `quarantined`, `search` `rejected` | все `needs_revalidation` событием, `search` `rejected` | `import_legacy` без admit; рабочий цикл в отдельном `legacy-loop`, K11 не заявляется | пять `needs_revalidation`, `search` `rejected` | заморозить старый registry, genesis-событие, шесть → `quarantined`; **K11 к native не применяется**, они остаются native inventory |
| указатель | вне writable workspace агента | HEAD подписан, вне области записи | вне репозитория, пересчёт цепочки | **`lab/tools/registry-pointer`** — внутри дерева агента | promoter-owned каталог, пересчёт от genesis |
| кто пишет | только promoter | только promoter, проверка EACCES | только promoter, отдельная учётная запись | только promoter, файл readonly для агента | только promoter, ACL/uid + негативный тест |

**Конституционное уточнение.** В конституции прямо сказано: «Для native-инструмента
K11 не применяется (они уже в системе), но K1–K10 применяются» (строки 94–95; там же
§211). E опирается на это; C сохраняет рабочий цикл через `legacy-loop`, не заявляя
K11. A/B/D переводят legacy в карантин/revalidation, что может быть разумной мерой
риска, но не должно молча превращаться в требование admission для native-инструментов:
это была бы поправка к конституции. Решение — за владельцем.

**Проверенный факт:** в `registry.jsonl` все шесть записей `active` версии 3, включая
`search`. Это противоречит Q8 и принципу производного `active` независимо от того,
какой формат выберет владелец.

**Ошибка D:** указатель `lab/tools/registry-pointer` лежит в агентском дереве. При
компрометации агента его можно заменить вместе с цепочкой; это противоречит K10 и
позициям остальных. Указатель должен быть вне области записи агента.

**Ошибка D (вероятная):** `admission_event.manifest.monotonic_counter == env.latest_counter`
глобально выключает старые валидные инструменты при каждом новом допуске. Нужен
счётчик на инструмент или `≤` с окном replay, иначе один новый `head` деактивирует
`read`/`list`.

### 2.7. Q16/T02 — минимальный пилот генератора

| ответ | что генерируется | шаблоны | spec / held-out | мутанты/контроли | порог |
|---|---|---|---:|---|---|
| A | код в 2 семействах | `file_read_stream` + второе | 6 spec, 3 варианта, 2 held-out | 12 мутаций, 8 критических | 6/6 compile+semantic, 8/8, held-out 2/2 |
| B | **только карточка и параметры**, код фиксирован | 1 kind `file_read_stream` | 8 spec, 4 held-out | 10 мутантов | held-out 4/4, мутанты 10/10, любой escape = kill |
| C | код в 3 шаблонах | `file_read_stream`, `digest`, `directory_read` | 12 spec, 6 held-out | 18 критических + 24 прочих | M1 ≥5/6, M2 ≥4/6, M3=0, M0=100% |
| D | код в 3 шаблонах | `file_read_stream`, `directory_list_bounded`, `digest_sha256` | 3 задачи/шаблон + 3 held-out/шаблон | 4 атаки/задачу, 8/9 held-out | 108 прогонов, held-out ≥8/9, 100% контролей |
| E | код в 2 шаблонах | `file_read_stream` + `digest_sha256` | 20 spec (10/шаблон, 5 held-out/шаблон) | 24 gate-мутанта, 8 контролей/шаблон | ≥19/20, 100% контролей, детерминизм 3/3 |

Согласовано: 1 шаблон недостаточен; свободный Rust не генерируется; held-out
хешируется до прогона и не виден генератору; все попытки логируются; человек
подписывает и расширяет авторитет; kill при любом пропущенном критическом контроле.
Расходится главный вопрос: **генерируется ли код или только карточка/параметры**.
B предлагает карточный пилот (доказывает параметризацию, не синтез кода); A/C/D/E —
кодовый, от 2 до 3 шаблонов. Это решение владельца, потому что оно меняет смысл
заявления «харнесс генерирует инструменты».

**Наше замечание:** числа 20/24/108 — инженерные гейты, не статистика. При 0
допущенных нарушениях верхняя 95%-граница ≈ 3/n (C это отмечает): при n=12 это ~25%,
при n=36 ~8%. Писать это в отчёте обязательно.

### 2.8. Q17/S05 — порядок отказов и словарь

| ответ | приоритет после K11 |
|---|---|
| A | `K6_EGRESS` → `S6` → `K6_UNKNOWN` → `K4` → `S7` → `S1` |
| B | scope → `K6_EGRESS` → `K6_UNKNOWN` → `K4` → `S6` → `S1` |
| C | `S6` → `K6_EGRESS` → `K6_UNKNOWN` → `K4` → `S1` |
| D | scope (`K1`) → `K6_EGRESS` → `K6_UNKNOWN` → `K4` → `S6` → `S1` |
| E | `K6_EGRESS` → `K6_UNKNOWN` → `S6` → `K4` → `S2` → `S1` |

Согласовано: K11 первым; для пути вне корня класс не запрашивается и наружу не
выдаётся; модель видит один primary, журнал — все `violations[]`; сырой внешний путь
не пишется. Расходится место `S6` относительно K6: A/C ставят `S6` выше, B/D/E —
ниже. Расходится `K4` vs `S6`: A/C — `S6` выше, B/D — `K4` выше, E — `S6` выше.
Победителя по голосам нет; нужен выбор владельца и фиксация в пре-регистрации.

Словарь v2: точных кодов для невалидного UTF-8 и отсутствующего файла нет. A
предлагает `S2_ARTIFACT_ENCODING`/`TYPE`/`CHANGED`; B — `S?_ENCODING`/`TYPE`/`SIZE_CHANGED`
и поправку словаря; C — detail-поле до поправки, затем v3; D — переиспользовать
`K6_DATA_CLASS_UNKNOWN` для UTF-8 и `S1_SCHEMA` для отсутствия; E — интерим
`S2_ARTIFACT_MISSING` (для отсутствия), `S1_SCHEMA` + detail для UTF-8, предложение
`S2_CONTENT_ENCODING`. Четыре из пяти против переиспользования K6: это маскирует
класс дефекта. D — единственный, кто смешивает UTF-8 с K6.

### 2.9. F04 — лестница статусов

| ответ | форма |
|---|---|
| A | 6 ступеней: declared → schema_validated → semantic_validated → policy_checked → K11_admitted → runtime_observed |
| B | 5 ступеней: card_valid → policy_checked → room_run_passed → observed_within_card → K11_admitted; `K9_proven` запрещён |
| C | **две оси**: evidence `none`/`schema_valid`/`policy_checked`/`room_observed` + authority `admitted: bool`; `K9_proven` запрещён |
| D | 4 ступени: schema_valid → policy_checked → slice_passed → admitted; `K9_proven` запрещён |
| E | 6 ступеней: declared → schema_checked → policy_checked → contract_checked → runtime_checked → K11_admitted; `K9_model_checked` зарезервирован, `K9_proven` запрещён |

Согласовано: статус вычисляется из артефактов, не рисуется; любое изменение digest
сбрасывает соответствующие ступени; `runtime_checked`/`room_observed` — только для
конкретного корпуса/прогона; `K11_admitted` не означает «безопасен». Расходится
порядок runtime и допуска: A/D/E ставят runtime до или независимо от допуска, A —
после; C вообще разводит доказательство и полномочие. Это решение владельца.

### 2.10. A01 — манифест, JCS и TOCTOU

| ось | A | B | C | D | E |
|---|---|---|---|---|---|
| домен | `HERNESS-ADMISSION-MANIFEST-V1\0` + JCS, сырой Ed25519 | `herness.admission.v1` | SSHSIG namespace; сырой префикс как эквивалент | `herness:admission` + SSHSIG | SSHSIG namespace `herness-admission-v1` |
| `stored == JCS` | да | да (для воспроизводимости, не как защита) | да | да | да |
| TOCTOU Linux | FD + `execveat`/`fexecve` | `memfd` + `F_SEAL_*` + `execveat` | `-add-fd` + guest RO + `memfd`/`execveat` | digest перед exec + Landlock (**неверно**), memfd — v1 | `memfd`/`execveat`; host image `-add-fd` |
| Windows | отдельное решение, не описано | WSL-вариант проверить | **не исполнять байты на Windows** | digest+Landlock, остаточное окно | handle + hash + ACL, остаток документировать |
| replay/срок | epoch, expires, revocation state | epoch/seq, `expires_at` информативен | `anchor_epoch`, `admission_seq`, revoked digests | `monotonic_counter`, `prev_manifest_digest` | `min_epoch`, монотонное состояние |

Согласовано: подпись над точными байтами; строгий парсинг (дубли ключей, неизвестные
поля, BOM, невалидный UTF-8); проверка до запуска; digest бинаря, а не путь; срок и
отзыв; replay-защита. Расходится **механизм привязки к исполняемым байтам** и
Windows-путь. D-вариант «Landlock закрывает TOCTOU» неверен: Landlock ограничивает
только процесс и потомков, но не другого писателя на хосте.

---

## 3. Проверенные факты репозитория

Это не мнения ответов, а чтение снимка и запуск существующих чекеров.

| утверждение | где | вердикт |
|---|---|---|
| `tool_write_in` **не** вызывает `resolve_in` | `loopmod.rs`, `tool_write_in` ~877: `resource_of` + `policy_allows("write","write")` + `write_beneath` | **подтверждено E по коду**; B-R6 ошибался. A подтвердил сам `write_beneath` и его флаги, но не отсутствие `resolve_in` |
| Rust `POLICY` = 14 правил, `policy.json` = 19 | `loopmod.rs` ~491–514; `lab/tools/policy.json` | **подтверждено**: отсутствуют пять `implied` deny: `read-deny-outside`, `write-deny-outside`, `seal-deny-outside`, `netprobe-deny-other`, `netprobe-deny-fs` |
| `resource_matches` не поддерживает `!` | `loopmod.rs` | **подтверждено**: `file:!/mnt/**` не матчит ничего; при codegen из JSON эти deny станут мёртвыми молча → класс `S5_POLICY_DRIFT` |
| `write_beneath` ставит только `BENEATH \| NO_SYMLINKS` | `loopmod.rs` ~904 | **подтверждено**; `NO_MAGICLINKS` влечётся `NO_SYMLINKS`, реальный пробел — `NO_XDEV` |
| `write` использует `O_TRUNC` | `write_beneath` | **подтверждено**; противоречит Q1 `file_write` = create-new/no-overwrite — миграционный пробел |
| write-политика на ненормализованном пути | `/mnt/work/../../etc/x` → `policy_allows("write")=True` | **подтверждено**; `openat2 BENEATH` ловит, то есть policy не стена для write |
| `resource_of` вне корня подставляет `/mnt` | `resource_of` ~547 | **подтверждено как поведение функции**; `resolve_in` `starts_with(root)` защищает read/list/search; для write защищает `openat2`, не policy |
| `resolve_in` всегда проверяет `("read","read")` | `resolve_in` ~607 | **подтверждено**; list/search/seal затем проверяют свой action, но первая проверка идёт от `read` |
| `read` делает `resolve_in` → `metadata` → `read_to_string` | `tool_read_in` ~821 | **подтверждено**: TOCTOU-окно и чтение файла целиком до обрезки |
| карточка `read` обещает `output_bytes: 8192`, код даёт `MAX_READ=24*1024` | `registry.jsonl`, `loopmod.rs` | **подтверждено**: контракт/код расходятся (`S5_IMPL_DIVERGES`) |
| `tool_search_in` молча пропускает нечитаемые/`>MAX_FILE` файлы, но считает их в `scanned` | `tool_search_in` ~625 | **подтверждено**: «найдено 0 в N файлах» при N, включающем непрочитанные — напряжение с K5 |
| у `head` две карточки | `lab/tools/cards/head.json` (legacy closure), `lab/tools/drafts/head-v1.draft.json` (`tool-card-v1`) | **подтверждено**; `card_atoms` потребляет только старую |
| `head` не имеет разрешающего правила; `card_atoms` rc=3 | `policy.json`; полный путь `lab/tools/cards/head.json` | **подтверждено**; без пути `--check head` → rc=2 «нет файла» |
| registry: шесть записей, все `active`, `version: 3`, включая `search` | `registry.jsonl` | **подтверждено**; противоречит Q8 и производному `active` |
| admission в коде не проверяется | `run_tool_g` ~1085 — только granted-list; `K11_ADMISSION_REQUIRED` только в словаре | **подтверждено** |
| `seal`/`netprobe` запускают себя через `current_exe()` | `tool_seal` ~285, `tool_netprobe` ~364 | **подтверждено**; противоречит `process_spawn: false` и `max_processes: const 1` |
| `max_processes` не проверяется runtime | `core-rs/src` — только схема/карточка | **подтверждено** |
| draft `head` проходит схему с нулевыми provenance digest | `tool-card-v1.schema.json`, `head-v1.draft.json` | **подтверждено** чтением схемы: `provenance` не требует ненулевых значений; E исполнял валидатор — 9 мутантов проходят схему (по ответу E) |
| `file_read_stream` в Rust отсутствует | `core-rs/src` | **подтверждено**; `HEAD-SLICE-R1` `closed:false` |
| non-Linux fallback слабее | `loopmod.rs` комментарий «на не-Linux атомарности нет» | **подтверждено по смыслу**; номер строки не сверялся |
| `.gitattributes` покрывает R6 и R7 | `.gitattributes` | **подтверждено**; F-R6 утверждал обратное — устарело |

---

## 4. Ошибки и неподтверждённые утверждения R7

### 4.1. Исправления к R6, сделанные по итогам R7

- **`NO_MAGICLINKS` — не отдельный дефект `write_beneath`.** `openat2(2)`:
  `RESOLVE_NO_SYMLINKS` implies `RESOLVE_NO_MAGICLINKS`. Реальный пробел — `NO_XDEV`.
  `docs/R6-SYNTHESIS.md` исправлен.
- **`card_atoms --check` требует точный путь.** `python bin/card_atoms.py --check head`
  даёт `rc=2` «нет файла», `--check lab/tools/cards/head.json` — `rc=3`. В R6 это
  смешивалось; в синтезе R6 уточнено.
- **B-R6 «write вызывает `resolve_in`» — ложно.** `tool_write_in` не вызывает; это
  подтвердили A и E по коду.

### 4.2. Ошибки в ответах R7

| ответ | утверждение | что не так |
|---|---|---|
| D | Landlock audit — независимое наблюдение на ядре 6.6 | Флаги audit logging — ABI v7 / Linux 6.15; на 6.6 их нет. Механизм D-R02 в текущей комнате не работает как описан |
| D | Landlock закрывает TOCTOU между хешем и exec | Landlock ограничивает только процесс и потомков, не других писателей хоста; окно не закрывается |
| D | указатель registry в `lab/tools/registry-pointer` | Это агентское дерево; противоречит K10 и позициям остальных. Указатель должен быть вне области записи агента |
| D | `monotonic_counter == latest_counter` глобально | Деактивирует старые валидные инструменты при каждом новом допуске; нужен счётчик на инструмент или окно |
| D | `bytes_read` в S02 | Псевдокод вычитает хвост, «поправка» требует не вычитать; строка 7 противоречит поправке |
| D | команда QEMU | Опечатка `qemu-system-x86_66`; способ подачи fixture на прогон не описан |
| C | V05 «путь абсолютный», `read_scope:["/fixture/..."]` | Реальный `pathScope` — `{root_ref, segments}`, сегменты относительны; C сам пишет, что схемы не видел. Правило нужно переформулировать под `tool-card-v1` |
| C | `max_tool_processes` как поле карточки | В текущей схеме `max_processes: const 1`; новое поле — изменение схемы, а не деталь |
| C | `output_cap` как четвёртая причина остановки | Это дизайн-выбор (E: `K4` при переполнении кадра); требует фиксации в контракте, а не только в ответе |
| B | `truncated := bytes_consumed < size_at_open` | При росте файла можно объявить EOF раньше; B сам помечает это ограничением v0, но формула остаётся хрупкой |
| B | recovery подписывает trust-anchor update | Транзитивно может установить новый operational-ключ; без отдельной церемонии это второй путь допуска |
| E | каталог/FIFO без метки → `K6_DATA_CLASS_UNKNOWN` до open | Расходится с B/C/D (S6/S1/type); класс до open — это выбор, а не факт; нужно решение |
| E | `cap < первой строки` → `K4` | A/B/C/D возвращают ok+truncated; E сохраняет негативный контроль пре-регистрации, но это развилка |
| A | приоритет `S6` выше `K6_UNKNOWN` | Меньшинство (C); B/D/E ставят K6 выше; не ошибка, но требует выбора |
| A | legacy-шесть все `quarantined` | Может конфликтовать с конституционным «K11 к native не применяется»; нужно решение, а не молчаливая миграция |
| A | `output_bytes` при переполнении | Поведение не определено; C/E его закрывают, A/B/D оставляют пробел |

### 4.3. Что в ответах не доказано (и не выдаётся за доказанное)

- Ни один ответ не доказал изоляцию QEMU/KVM/WSL2; все пять это признают.
- Ни один не доказал полноту наблюдения; скрытые каналы, ptrace-эквивалентность,
  Landlock-полнота — открыты.
- Ни один не доказал, что карточка описывает поведение кода; валидатор проверяет
  декларацию и digest'ы, а не реализацию.
- Числа пилотов (6/12/20/108) — инженерные гейты, не статистика.
- Ссылки/утверждения о коде у B/C не проверялись ими; D проверял частично; A и E
  проверяли снимок, но их прогоны мы не воспроизводили.

---

## 5. Что можно делать без решения владельца

Только то, что не меняет authority и не закрепляет одну из развилок:

1. Держать сырые ответы и этот синтез как историю; ничего не «сглаживать».
2. Исправить документацию, где утверждения уже опровергнуты (R6-синтез исправлен:
   `NO_MAGICLINKS`, точный путь `card_atoms`).
3. Подготовить **измерительный** план комнаты: список команд и evidence-полей, без
   запуска security-run и без записи в WSL-дистрибутив другого проекта.
4. Подготовить конformance-векторы как черновик, но **не** объявлять их каноном и не
   подключать к гейту до решения Q11.
5. Проверить на текущем коде уже известные дефекты (policy drift, `O_TRUNC`,
   `MAX_READ`, `search` skip) — это чтение/тесты, не изменение policy.

Нельзя до решений: писать Rust `file_read_stream`, менять `policy.json`/registry/схему,
вводить admission, создавать owner-ключ или promoter, запускать генератор, менять
`lab/prereg/HEAD-SLICE-R1.json`.

---

## 6. Решения, которые нужны от владельца

Ниже — не наши выборы, а точные вопросы, на которые ответ снимает развилку. Формулировки
нейтральны; рекомендации агента помечены отдельно в R8, а не здесь.

| № | решение | что выбрать | почему нельзя отложить |
|---|---|---|---|
| Q11 | канон и runtime | Rust-канон (все пять); степень runtime-проверки: полная семантика (C), только admission (A), только digest (E), доверие манифесту (D) | от этого зависит, что проверяет promoter и что считается `active` |
| Q12 | таблица S02 | EOF-момер (size_at_open / read==0 / зонд в бюджете); один счётчик или два; `truncated` на точной границе; `cap<строки` → ok или K4; CRLF снимать или сохранять; `output_cap` vs K4; коды UTF-8 | без одной таблицы нельзя писать Rust-срез и пре-регистрацию |
| Q13 | комната | WSL2+KVM (все); seccomp: NET=y + фильтр (A/B/C/E) или NET-less + Landlock (D); процессы: cgroup=1 vs pids.max=2; подача fixture: initramfs vs `-add-fd`; WHPX fallback: разрешён (C) или нет | security-run не существует, пока это не зафиксировано и не измерено |
| Q14 | наблюдение | ptrace-трасса (A/C/E), отказ ядра + канарейки (B), Landlock audit (D — не работает на 6.6); притязание `observed_independent` или `observed_in_guest` | от этого зависит, что считается свидетельством и что — провалом |
| Q15 | ключ | один ключ + backup (A/C/E) или отдельный recovery с ограниченными правами (B/D); SSHSIG (B/C/D/E) или сырой Ed25519 (A); trust anchor: compiled-in / файл владельца / root-owned WSL | ошибка здесь создаёт второй путь допуска или потерю управления |
| Q18 | registry и legacy | `active` как предикат (все); legacy: карантин (A/C/E), needs_revalidation (B/D); K11 к native: не применяется (конституция, E/C) или применяется после поправки; указатель вне агентского дерева (все, кроме D) | без этого `search` остаётся активным, а цикл либо ломается, либо обходит конституцию |
| Q16 | пилот | генерировать карточку/параметры (B) или код; 2 шаблона (A/E) или 3 (C/D); 6/12/20 spec; held-out 2/4/6/10; пороги и kill | преждевременный пилот закрепит неверную семантику и создаст «зелёный» без доказательства |
| Q17 | отказы | приоритет после K11: `S6` выше K6 (A/C) или K6 выше `S6` (B/D/E); `K4` vs `S6`; новые коды UTF-8/type/missing или detail-поля | порядок влияет на метрики и на то, что видит модель; менять после прогонов нельзя |
| F04 | статусы | 4 ступени (D), 5 (B), 6 (A/E) или две оси (C); где runtime относительно допуска | статус — это язык отчётов и гейтов; смешение превращает допуск в «безопасность» |
| A01 | манифест | поля, домен, SSHSIG/raw, JCS-хранение, Linux TOCTOU, Windows-путь | подпись не тех байтов или проверка пути вместо FD обесценивает admission |

Отдельно, как дефекты, а не развилки:

- **Policy drift:** Rust `POLICY` 14 vs JSON 19; пять implied deny не реализованы,
  `!` не матчится. Сейчас поведение спасает default-deny, но codegen из JSON сделает
  deny мёртвыми. Это надо чинить до генератора; решение о том, какой источник
  канонический (JSON или Rust), — за владельцем.
- **`read` 24 KiB vs 8192:** либо привести код к карточке, либо карточку к коду;
  молчаливое расхождение недопустимо.
- **`write` `O_TRUNC`:** Q1 обещает create-new/no-overwrite; код перезаписывает.
- **`search` skip:** молчаливый пропуск нечитаемых файлов при подсчёте `scanned`
  нарушает K5 в отчёте; нужно либо отдельное поле `skipped`, либо отказ.
- **Две карточки `head`:** legacy и draft смешиваются в ответах; до миграции нужно
  явно указывать, какая карточка имеется в виду.

---

## 7. Что изменилось по сравнению с R6

- Канон: R6 был 5:1 за Rust; R7 — 5:0. Python-вариант F больше не поддерживается.
- S02: R6 имел шесть несовместимых таблиц; R7 сузился до одного консенсуса по
  принципам и нескольких точных осей (EOF-момер, счётчики, граница, CRLF, output).
- Комната: R6 расходился WHPX/KVM; R7 — 5:0 за WSL2+KVM (C — с fallback).
- Наблюдение: R6 включал seccomp-unotify и Landlock; R7 — unotify отвергнут всеми,
  Landlock-audit остался только у D и не работает на 6.6.
- Ключ: R6 включал recovery-root; R7 — 5:0 против recovery, подписывающего admission;
  осталось различие «отдельный recovery с revoke/rotate» (B/D) vs «тот же ключ» (A/C/E).
- `active`: R6 — идея; R7 — формула и конкретные legacy-решения (но развилка
  «карантин vs native» осталась).

---

## 8. Следующий шаг

Нужен бриф R8, который закроет оставшиеся развилки **точными вопросами**, а не
пересказом. Он должен включать:

1. Q11: канон + runtime-роль, с примерами «что происходит при подмене карточки после
   допуска» для каждого варианта.
2. Q12: одна таблица S02 с точными полями и ожидаемыми значениями для fixture
   471 Б/10 строк; отдельно — `output_cap`/`K4` и коды UTF-8.
3. Q13: точная команда QEMU, способ подачи fixture, seccomp-механизм, модель процессов,
   список измерений и evidence; вопрос о WHPX-fallback.
4. Q14: механизм наблюдения и уровень притязания; что считается `observed_independent`;
   как проверяется слепой монитор.
5. Q15: топология ключа, SSHSIG/raw, trust anchor, анти-откат; цена каждого варианта.
6. Q18: legacy-шесть и K11-native; указатель; состояния; `search`.
7. Q16: что генерируется, сколько шаблонов/spec/held-out, пороги, kill.
8. Q17: приоритет отказов и словарь.
9. F04/A01: лестница и манифест; JCS/домен; Windows/Linux TOCTOU.
10. Отдельный блок «дефекты, которые чинятся независимо»: policy drift, `O_TRUNC`,
    `MAX_READ`, `search` skip, две карточки `head`.

Сам бриф — `docs/EXTERNAL-QUESTIONS-R8.md` (следующий коммит); он
самодостаточен, ссылки прибиты к коммитам, наши вердикты в него не входят.
