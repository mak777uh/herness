# План: перенести все наши репозитории в herness

**Дата:** 07.11.2026. **Задача:** владелец хочет безопасно удалить локальные копии наших репозиториев.
Всё наше должно жить в `herness`. **Морфогенез не трогать.**

## Что найдено

### Наши репозитории (переносим)

| локальный путь | удалённый | состояние |
|---|---|---|
| `C:\111\spec` | `mak777uh/flowguard-spec` | чисто, запушено |
| `C:\111\lexspec-review` | `mak777uh/lexspec` | чисто |
| `C:\111\VecDHT` | `mak777uh/VecDHT` | **1 неотслеживаемый файл** |
| `C:\111\_vec` | `mak777uh/VecDHT` (ветка interop) | **1 неотслеживаемый файл** |
| `C:\111\lean-agent-verify` | `mak777uh/lean-agent-verify` | чисто |
| `C:\111\modelproof` | `mak777uh/modelproof` | чисто |
| `C:\111\proofs-registry` | **нет .git** | 0,5 МБ, локальное |
| `C:\111\pharos-agent-arena` | `mak777uh/pharos-agent-arena` | чисто |
| `C:\111\cases` | `mak777uh/cases` | **9 незапушенных коммитов** |
| `C:\111\work\nomos` | **нет .git** | 0,3 МБ, локальное |
| `C:\111\work\flowguard` | `mak777uh/flowguard-spec` | **6 неотслеживаемых файлов** |
| `C:\111\work\harness` | `mak777uh/harness` | чисто |
| `C:\111\work\rocketpool-invariants` | `mak777uh/rocketpool-invariants` | **4 незапушенных коммита** |
| `C:\111\work\verified-cells-cairo` | `mak777uh/verified-cells-cairo` | **3 незапушенных коммита** |
| `C:\111\work\sealed-invoice` | `mak777uh/sealed-invoice` | чисто |

### НЕ трогаем

| путь | почему |
|---|---|
| `C:\111\system\repos\morph` | **морфогенез**, владелец объяснит позже |

### Чужие репозитории (не переносим)

`C:\111\projects\*` — 40+ клонов чужих контрактов (Uniswap, Aave, Chainlink и т.д.).
Это рабочий материал для аудитов, не наши репозитории. **Не переносить.**

## План

### Шаг 1. Сохранить то, что не запушено

| репозиторий | что сделать |
|---|---|
| `cases` | **запушить 9 коммитов** |
| `rocketpool-invariants` | **запушить 4 коммита** |
| `verified-cells-cairo` | **запушить 3 коммита** |
| `VecDHT` | закоммитить и запушить `interop/2026-10-29-herness-to-vecdht.md` |
| `_vec` | закоммитить и запушить `2026-10-27-flowguard-to-vecdht-5.md` |
| `work\flowguard` | проверить 6 файлов: это дубликаты `docs/` или новые? |
| `proofs-registry` | **создать репозиторий и запушить** (сейчас только локально) |
| `work\nomos` | **создать репозиторий и запушить** (сейчас только локально) |

### Шаг 2. Перенести в herness

**Вариант A — как подкаталоги с сохранением истории (git subtree).**

```
herness/
  parts/
    flowguard-spec/
    lexspec/
    VecDHT/
    nomos/
    proofs-registry/
    lean-agent-verify/
    modelproof/
    cases/
    rocketpool-invariants/
    ...
```

**Плюс:** всё в одном месте, история сохранена.
**Минус:** herness раздувается, и это уже не «один репозиторий», а склад.

**Вариант B — как ссылки и копии артефактов.**

```
herness/
  parts/
    MANIFEST.json      # что откуда, какой коммит, какой хеш
    flowguard-spec/    # только ключевые документы
    lexspec/
    ...
```

**Плюс:** herness остаётся про харнесс, а не про всё.
**Минус:** история не сохранена, только снимок.

**Вариант C — как субмодули.**

```
herness/
  .gitmodules
  parts/flowguard-spec   # submodule
  parts/lexspec          # submodule
```

**Плюс:** история и обновления, herness не раздувается.
**Минус:** субмодули требуют сети для клонирования; при удалении локальных копий всё равно
нужен доступ к GitHub.

## Что я рекомендую

**Вариант A для маленьких, C для больших.**

| репозиторий | размер | вариант |
|---|---|---|
| `flowguard-spec` | 82 КБ документов | **A** (subtree) |
| `lexspec` | 68 КБ документов | **A** |
| `nomos` | 0,3 МБ | **A** |
| `proofs-registry` | 0,5 МБ | **A** |
| `lean-agent-verify` | 0,1 МБ | **A** |
| `modelproof` | 0,1 МБ | **A** |
| `cases` | 0,1 МБ | **A** |
| `VecDHT` | 24 МБ | **C** (submodule) |
| `rocketpool-invariants` | ~1 МБ | **A** |
| `verified-cells-cairo` | ~1 МБ | **A** |
| `sealed-invoice` | ~1 МБ | **A** |
| `pharos-agent-arena` | 2,6 МБ | **A** |

**Почему так:** маленькие репозитории целиком помещаются в herness без раздувания. VecDHT на 24 МБ
лучше как субмодуль.

## Что нужно решить владельцу

1. **Подтвердить план** — или выбрать другой вариант.
2. **Разрешить запушить** 16 коммитов в `cases`, `rocketpool-invariants`, `verified-cells-cairo`.
3. **Разрешить создать** репозитории `proofs-registry` и `nomos` на GitHub (сейчас их там нет).
4. **Сказать**, что делать с `projects/*` — чужими клонами на 1,9 ГБ.

## Чего я НЕ буду делать без разрешения

- удалять что-либо;
- пушить в репозитории, где есть незапушенные коммиты;
- создавать новые репозитории на GitHub;
- трогать `system\repos\morph`.
