# HANDOFF СЛЕДУЮЩЕМУ АГЕНТУ — 26.11.2026

> Режим остановки: владелец попросил остановить техническую работу и оставить в репозитории
> полную передачу смены. Этот файл — документарный handoff, **не** closure экспериментов и
> **не** разрешение продолжать реализацию без нового поручения. Сопровождающий commit/push
> сохраняет текущий candidate state и evidence; он не превращает открытые проверки в PASS.

## 1. С чего начать

Репозиторий: `C:\Users\Admin\Documents\Qoder\2026-11-23\59e41fc7\herness`.

Origin: `https://github.com/mak777uh/herness`.

Утверждённый план: `C:\Users\Admin\.qoder\plans\final-river-bison.md` (внешний локальный файл;
в commit не входит). Актуальная статусная карта в нём обновлена 26.11.2026 и ссылается сюда.

Обязательный порядок чтения — `AGENTS.md`:

1. `README.md`;
2. `docs/WHERE-I-STOPPED.md` — верхняя rolling-карта ведёт сюда;
3. `docs/DECISION-0001-base-os-language.md`;
4. `CLAIMS.md`;
5. `NOT-CLAIMED.md`;
6. `docs/eliminations.md`;
7. затем код и prereg.

Перед любыми выводами о состоянии выполнить:

```bash
git rev-parse HEAD
git status --short
git log -1 --oneline
```

Stop-point baseline: `3630801f31e2e0d0174de07c75faf72255e7fb59` —
`fix W12: сделать list детерминированным и ограничить 100`.

На момент остановки этот commit был локальным, `origin/main` = `a90712655267b50286c79d728e3323f1a52f837d`.
Сопровождающий handoff commit отправляет и `3630801`, и последующие E-0090/E-0091 изменения,
и этот документ. Поэтому актуальный HEAD после push нужно прочитать из git, а не подставлять
stop-point hash как текущий.

## 2. Что сделано и что не закрыто

| эксперимент | состояние на остановке | что подтверждено | что осталось |
|---|---|---|---|
| **E-0089 / LIST-DETERMINISM-LIMIT-REMAINDER-R1** | runtime candidate, **open** | Rust focused 8/8 Windows и POSIX; полный WSL suite 210/0 до изменения embedded registry state; полный Windows 165 passed / 3 старых platform failures; contract v2 и history обновлены | полный regression после E-0090 state change; clean clone; review; conclusion/claim/closure |
| **E-0090 / REGISTRY-DESCRIPTION-APPENDONLY-R1** | append-only correction candidate, **open** | registry state 40/40 и list contract 8/8 на Windows/POSIX; genesis snapshot и prefix seq=0..9 byte-exact; `active=[]`; list v4 только как description, authority не выдана | полный regression после нового `registry.state.json`; gates; clean clone; review; closure |
| **E-0091 / W03-REVIEW3-SUCCESSOR-BASELINE-R1** | sealed successor correction, **open** | W03 Review3 9/9 Windows/POSIX; исторические sealed W03 файлы не переписаны; successor разрешён только для `core-rs/src/loopmod.rs` из sealed E-0090 | включение в общий closure; review; claims/conclusion |
| **C-0364 / W12 list closure** | **не закрыт** | focused candidate evidence есть | conclusion artifact, `check_artifacts`, `verify_claims`, coverage, lab statuses, claims, closure commit |

Нельзя писать «W12 закрыт», «clean-clone PASS», «полный CI-PASS» или «production ready».
`N/A`, `unsupported`, `unknown` и непроведённая проверка не являются PASS.

## 3. Точное состояние E-0089

Runtime candidate `3630801`:

- `core-rs/src/loopmod.rs` использует `LIST_LIMIT = 100`;
- каталоги и файлы сортируются по имени отдельно;
- subset выбирается **после** сортировки, каталоги идут первыми;
- хранятся два bounded `BinaryHeap<ListEntry>` не более 100 кандидатов каждый;
- всё дерево одного уровня полностью считается для exact `total`;
- marker появляется только при `total > shown`;
- marker сообщает `total - shown`;
- границы 0/99/100/101/200/201 и permutation control покрыты восемью Rust-тестами.

Checkout и Git blob — разные evidence surfaces:

```text
core-rs/src/loopmod.rs checkout:
198631 байт, 3821 CRLF
sha256 9b1dc65e39c0b85eecba1d3ff61967d3b135327e500a843bcbb063a0ee9caf38

Git blob:
194810 байт, 0 CRLF
sha256 bd73f29954140ff6cc6092c8dac297d259d7726be537e5be80115fc747508979
```

Contract v2 в `lab/tools/contracts.json` и embedded `bin/contract.py` синхронизированы:
dirs-first, exact remainder, single level как negated duty, `escapes: []`.

Замороженный `lab/tools/registry.jsonl` **не изменён**. Его genesis digest:

```text
sha256 0afc75ec3bf277ba4d48336c75368d2f7382d0963aa0b42c929472715de9b008
```

List description v4 вынесен в append-only E-0090, а не записан поверх genesis.

## 4. Точное состояние E-0090

Prereg:

```text
lab/prereg/REGISTRY-DESCRIPTION-APPENDONLY-R1.json
sha256 d5b6a8cd13f307a462760ebed1681985cdae4c4fcc8cad20a54aee62c35f2a22

sidecar:
sha256 2a2dc8f04603b030e32dcf60a67f25e54b12ce3b35e90033354481b4e3cf235b
```

Baseline commit:

```text
3630801f31e2e0d0174de07c75faf72255e7fb59
```

Refs search был честно `NOT PROVIDED`, rc=2: справочника нет, пустой результат не считается успешным поиском.

`bin/registry_state.py` теперь fail-closed проверяет description overlay:

- description не может содержать authority-поля (`status`, `active`, `admission`, `owner_signed` и др.);
- required/unknown keys, id, version/previous, closure, examples, `at` и типы валидируются;
- overlay применяется только после успешного `computed_state()`;
- malformed state заставляет preflight вернуть `unreviewed`, а не частичный overlay.

В `lab/tools/registry.events.jsonl` добавлено ровно одно событие `seq=10`, type `quarantined`,
tool `list`. Это намеренно **не admission**. Hash строки:

```text
sha256:313bd83335dd765bf050d348a8858e486b0204d946c86efb229240a2a01a7533
```

Hash файла events:

```text
cd8bb988ca2f07404d23e43e43805fb987f7dc9b65f4a9484cb09abfd1c2b740
```

Prefix seq=0..9 сохранён:

```text
70a85691fbe8290f642c96d56c0efa043056750492b765202a1321ad5bfacb7f
```

Derived `lab/tools/registry.state.json` пересобран:

```text
sha256 d486f4267d0443b572c47986551138223b77fbc1872889ee7b19a4349b097114
active=[]
list=quarantined, description version=4, seq=10
head=candidate, seq=9
```

`tests/test_list_contract.py` читает effective description из `computed_state()`, не из
замороженного snapshot. Оракул не ослаблен.

## 5. Точное состояние E-0091

Prereg:

```text
lab/prereg/W03-REVIEW3-SUCCESSOR-BASELINE-R1.json
sha256 6ca3ba0ea44b1e091fe9b54b462f981828634a5ae59a9b3bc173e8b71515d8a7

sidecar:
sha256 20e7be19f80e59cc01d1d6c5e918e11d079c54d0ffee637b4cda8c78ec4e5128
```

Refs search: `NOT PROVIDED`, rc=2.

Историческая ошибка в sealed W03 baseline (65-символьный hash) **не исправлялась задним числом**.
E-0091 разрешает единственный successor hash `9b1dc65e…` для `core-rs/src/loopmod.rs`, взятый
из sealed E-0090. Остальные protected hashes остаются исходными. R09 по-прежнему содержит ровно
9 controls; lifecycle fixtures и три acceptance-bypass metakontrol не менялись.

## 6. Последние реально выполненные проверки

Зелёные focused результаты:

```text
E-0089 Rust list: 8/8 Windows, 8/8 POSIX
E-0090 registry state: 40/40 Windows, 40/40 POSIX
E-0090 list contract: 8/8 Windows, 8/8 POSIX
E-0091 W03 Review3: 9/9 Windows, 9/9 POSIX
W18 development-scope: 14/14, mode=development-scope
lab validate: 91 эксперимент, 7 следующих гипотез
```

Полный Rust regression **до** изменения embedded `registry.state.json`:

```text
WSL: 201 lib + 9 integration = 210 passed, 0 failed
Windows: 165 passed, 3 failed
```

Три Windows failures были прежними platform failures, не новыми list regressions:

```text
loopmod::tests::перезапись_существующего_файла_отклонена
loopmod::tests::повторная_запись_после_создания_отклонена
sandbox::reach_tests::мёртвый_адрес_недоступен
```

После E-0090 embedded state изменился, поэтому эти полные regression результаты **не повторены**
на финальном candidate state. Их нельзя выдавать за проверку текущего HEAD.

W18 14/14 в development-scope подтверждает только согласованность текущего рабочего дерева
с HEAD-bound constants. Это **не clean-clone PASS**. Для clean-clone нужен пустой worktree и
`W18_REQUIRE_CLEAN=1`.

## 7. Последняя ошибка и почему gates не зелёный

Последняя команда:

```bash
python -B bin/lab.py validate && set -o pipefail; \
python -B bin/hs.py gates --profile auto 2>&1 | tee runs/exp-ci-residuals/e0089-e0091-gates.txt; \
rc=${PIPESTATUS[0]}; sha256sum runs/exp-ci-residuals/e0089-e0091-gates.txt; exit "$rc"
```

`lab validate` прошёл. Gates прошёл первые пять проверок и упал при очистке disposable copy:

```text
PermissionError: [WinError 32]
C:\Users\Admin\AppData\Local\Temp\hs-gates-copy-6v_o8vpg
```

Traceback: `bin/hs.py:1517 gate_claims_run` → `bin/hs.py:161 remove_disposable` →
`shutil.rmtree` → `make_writable`. Артефакт содержит traceback, rc=1:

```text
runs/exp-ci-residuals/e0089-e0091-gates.txt
sha256 aac926a1a137f845e5b6c17e6db7bdbabed3847221edc2b170dd14941de40255
```

Не удалять этот каталог вслепую и не завершать неизвестный процесс. Сначала безопасно выяснить,
какой handle/process его удерживает. Ошибка очистки — не RED тестов и не GREEN gates.

## 8. Какие файлы входят в candidate state

Код/данные/тесты:

```text
.gitattributes
bin/preflight.py
bin/registry_state.py
lab/registry.json
lab/tools/registry.events.jsonl
lab/tools/registry.state.json
tests/test_list_contract.py
tests/test_registry_state.py
tests/test_w03_lifecycle_review3.py
tests/test_w18_clean_clone.py
lab/prereg/REGISTRY-DESCRIPTION-APPENDONLY-R1.json
lab/prereg/REGISTRY-DESCRIPTION-APPENDONLY-R1.json.sha256
lab/prereg/W03-REVIEW3-SUCCESSOR-BASELINE-R1.json
lab/prereg/W03-REVIEW3-SUCCESSOR-BASELINE-R1.json.sha256
```

Evidence в `runs/exp-ci-residuals/` игнорируется `.gitignore`; в accompanying commit добавлены
точные пути принудительно. LF-пины в `.gitattributes` сохранены для всех E-0089/E-0090/E-0091
evidence, чтобы checkout не менял digest.

Исторические/вспомогательные файлы, которые не являются closure evidence:

- `e0089-list-red-rust.txt` — неудачная Windows linker environment (`GetHostNameW`), не test RED;
- `e0089-list-green-contract.txt` — получен при временно изменённом snapshot; **не использовать**;
- `e0089-list-gates-auto.txt` — исторический RED из-за genesis mismatch, не текущий GREEN;
- `e0089-list-candidate-contract-registry-red.txt` — baseline contract/registry RED до E-0090;
- `e0089-list-green-rust-windows-r2.txt` — повтор focused Windows, вспомогательное свидетельство.

## 9. Как продолжить после нового разрешения владельца

### Шаг 1 — reconcile и базовые integrity checks

```bash
git rev-parse HEAD
git status --short
python -B bin/seal.py verify-all
python -B bin/lab.py validate
```

Ожидается на момент handoff: seals должны пройти на candidate state; lab — 91/7. Если hash или
status изменился, сначала выяснить причину, а не перегенерировать sealed файлы.

### Шаг 2 — безопасно закрыть blocker gates cleanup

Выяснить владельца `C:\Users\Admin\AppData\Local\Temp\hs-gates-copy-6v_o8vpg` доступными
средствами диагностики процессов/handles. Не убивать неизвестный процесс и не удалять каталог
без подтверждения, что это disposable copy именно этого gates run.

Затем сохранить новый, отдельный артефакт (не перезаписывать старый RED):

```bash
set -o pipefail
python -B bin/hs.py gates --profile auto 2>&1 | tee runs/exp-ci-residuals/e0089-e0091-gates-r2.txt
rc=${PIPESTATUS[0]}
sha256sum runs/exp-ci-residuals/e0089-e0091-gates-r2.txt
exit "$rc"
```

Если снова `WinError 32`, это отдельный instrument defect; не объявлять tests RED и не обходить
очистку молча.

### Шаг 3 — повторить полный Rust regression на финальном state

Native Windows: перед cargo поставить в начало `PATH` WinLibs POSIX UCRT MinGW, иначе системный
conda GCC 5.3 даёт `GetHostNameW`:

```bash
export PATH="/c/Users/Admin/.cargo/bin:/c/Users/Admin/AppData/Local/Microsoft/WinGet/Packages/BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe/mingw64/bin:$PATH"
cd core-rs
cargo test --release --lib --tests
```

Ожидание: новых regressions относительно трёх известных Windows failures быть не должно.
Любой новый failure сохраняется и разбирается; старые failures не маскируются.

WSL Ubuntu, offline, release, с принудительным удалением core artifacts из-за DrvFs stale build:

```bash
wsl -d Ubuntu -- bash -lc 'cd /mnt/c/Users/Admin/Documents/Qoder/2026-11-23/59e41fc7/herness/core-rs && rm -f target/release/libhs_core.rlib target/release/deps/hs_core-* target/release/deps/libhs_core-* && CARGO_NET_OFFLINE=true cargo test --release --lib --tests'
```

Linker failure не считается RED тестов.

### Шаг 4 — clean Windows disposable selftest и W18 clean-clone

В disposable клоне зафиксированного candidate commit:

```bash
W18_REQUIRE_CLEAN=1 python tests/test_w18_clean_clone.py
python -B bin/hs.py selftest
```

Ожидание после исправления blocker: W18 14/14 `mode=clean-clone`; manifest 88 Python suites,
85 performed + 3 Linux N/A, 0 failed. N/A остаётся N/A. Development-scope W18 этого не заменяет.

### Шаг 5 — независимый review и closure C-0364

Review должен проверить runtime list invariants, append-only registry overlay, sealed successor
W03, exact EOL/hashes и отсутствие authority expansion. Только после PASS review и зелёных
regression/clean-clone проверок:

1. создать conclusion artifact для C-0364;
2. выполнить `python bin/check_artifacts.py C-0364`;
3. выполнить `python bin/verify_claims.py --fast`;
4. пересобрать/проверить `python bin/coverage.py CLAIMS.md`;
5. обновить `lab/registry.json`, `CLAIMS.md` и closure metadata по принятой практике;
6. обновить `docs/WHERE-I-STOPPED.md` и план;
7. создать отдельный closure commit, отправить и проверить CI.

Исторические FAIL/NEEDS_CHANGES не переписываются в PASS. Focused correction PASS не закрывает
весь план.

## 10. Стойкие ограничения

- Не трогать установленный DeepSeek Harness, `app.asar` и `~/.dsh`; работать только в своём `DSH_HOME`.
- Секреты не попадают в контекст, evidence и git; настоящие owner keys не создавать.
- Не активировать инструменты, не проводить реальную ceremony, не выполнять production activation.
- Не начинать production Linux namespace correction с `-r`: E-0085 и sealed stopping rule запрещают.
- Не ослаблять gates, frozen criteria, thresholds, corpora и acceptance requirements после RED.
- Не переписывать sealed или append-only history; исправления — новыми событиями/экспериментами.
- Перед новым механизмом выполнять `python bin/hs.py refs search "<боль>"`; `NOT PROVIDED` и пустой
  результат записывать как есть.
- `host_received ≠ host_durable ≠ host_observed ≠ integrity_verified ≠ acceptance_verified_executable ≠ externally_verified`.
- Receipt с `seq`/`sha256` не доказывает истину или acceptance.
- Native Windows Rust и WSL Rust — разные evidence surfaces.
- Local PASS, clean-clone PASS и CI-PASS — разные статусы.
- Полный CI-PASS не заявлять при известном Linux namespace positive B residual.
- Трёхкомнатная архитектура R1/R2/R3 остаётся гипотезой, не реализованной гарантией изоляции.

## 11. Ресурсы

После остановки RAM/диск/WSL **не перемерялись**. Старые числа из предыдущей смены нельзя
выдавать за актуальные. Не удалять DSH, защищённые каталоги, pagefile, WSL virtual disks,
Rust offline caches, Qoder history и пользовательские работы без безопасной причины.
После возобновления сначала измерить текущее состояние, затем очищать только подтверждённые
временные артефакты.

## 12. Evidence digest index

### E-0089

```text
prereg LIST-DETERMINISM-LIMIT-REMAINDER-R1.json
4f244a0a6467c702e306dcd0aa6f81099d5a4f97e54a3ddc0589fd6cc12c2757

red-python
96dc13e4172728c6b84716e78e834841a8775a45b6ee98bf50b31601700a896e

red-rust-windows
df7f047bbae7dfe6cfafd05227a0e4cbb7a86456da573541b29138fac06c258c

red-rust-posix
042850265c52475d1375df9b041d2c05762b0dc8a4f72f8980d0ca37bf808e5f

green-rust-windows
6c6aa8e369c7a072605f87b15c404d8d6d5d832ef65d8a0955aa8284b0b97f2f

green-rust-posix
5a5cbf1e5592590f0669f60e395d7ce538eab74f3e61c259bf50d6af47a5e0c3

regression-rust-windows (165 passed / 3 known failed)
de98cf67498bdee49eebc27d24a4ba5447fe648483edbfd19aca7881ef8fe190

regression-rust-posix (210 passed / 0 failed)
0cae62f89a768b67e8fb34a7be4780064b6a3d71c1b667736a0909cc00924698

baseline-regression-rust-windows
b6216bdda485caf27b58f8be041403549b4f58bd7873e20fb73a8cae8eaa2dda
```

### E-0090

```text
red-registry-windows
8effd7f5438803b35a5f27ed4c2f9dee0ed4335361030ffd27c0c0f923a390b4

red-registry-posix
e706ef16f71ed7a366982ad343f3d84afc37df48965d926d774f92dc7fa4ef3b

red-list-contract-windows
d24bad298ad0b8f566d945a340ba071b5df7f00f29307c99fd9c0159dbd79b8b

red-list-contract-posix
b7d898c21fe0495c1f1d23741d279fcecdbfdd48b23cc940fc4a70f469e37326

green-registry-windows
960e3a281e7e9b96136e01cec0e20ff98612f83936d26f0bf773888f1d8ddd54

green-registry-posix
16d318a33bbd905dca40a83b7be00720616a56a631577b79c4ff09e5336862fb

green-list-contract-windows
ad2cb0b67bc17810aa688c92cc42c88f21f7dcf65619948362466e4f2bf5facd

green-list-contract-posix
6dbf7b910ae67a06be2ff85716344c860748e4e30d8ca7a3da3e61e3c785b36f

w18-development-green
842fb34316e8cb4ca41100181005ae11807716c0570055437000f281a341634e
```

### E-0091

```text
red-windows
5cd0908df19793caefab03ae0eb4a287fd73a0bc956c25e0472f40d180b1b0ed

red-posix
93e8df74a6a99dc56c7d0c9446baa019195e47ef192e5560d5b3b5ba42894455

green-windows
c0e1d3f655dff1db21f914adbcee5556367a4296cda81cfb8f828e2e35187185

green-posix
e4179b12d2a3ff2c44ddfb8a693db4cf6dcf8301bed5265ec14a378dcab39c7d
```
