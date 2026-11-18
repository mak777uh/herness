# PROPOSAL-0002 — PID-namespace для `/v1/net` (решение владельца)

Дата: 2026-11-18. Статус: **принято владельцем (вариант A), реализовано в C-0328**.
Измерение: `PROC-ISOLATION-R1` / C-0327,
[`../research/outputs/PROC-ISOLATION-R1-2026-11-18.txt`](../research/outputs/PROC-ISOLATION-R1-2026-11-18.txt).
Реализация: [`../research/outputs/BRIDGE-NET-NAMESPACE-R1-2026-11-18.txt`](../research/outputs/BRIDGE-NET-NAMESPACE-R1-2026-11-18.txt),
тест `tests/test_bridge_net_namespace.py`.

## Зачем

`BRIDGE-KEY-ISOLATION-R1` (C-0324) закрыл наследование окружения: `/v1/net` больше не
передаёт `HS_BRIDGE_KEY` ребёнку. Но на Linux ребёнок того же uid всё равно читает
**стартовое** окружение моста через `/proc/<ppid>/environ`; это подтверждено: плечо A
дало `FOUND=1, FOUND_ANY=1`. PID-namespace скрывает родителя: плечо B дало
`FOUND=0, FOUND_ANY=0`. Прототип был не подключён к мосту; по решению владельца A
он подключён в C-0328, Windows закрыт отдельным срезом C-0330 (low-IL).

## Реализованное изменение (C-0328)

В `bin/bridge.py` добавлен `Bridge.net_command(argv)`:

```python
def net_command(self, argv: list[str]) -> tuple[list[str], str]:
    command = [sys.executable, str(ROOT / "bin" / "net.py"), *argv]
    if not sys.platform.startswith("linux"):
        return command, ""
    unshare = shutil.which("unshare")
    if not unshare:
        return [], "unshare не найден: /v1/net выключен (fail-closed)"
    return [unshare, "-U", "-p", "-f", "--mount-proc", *command], ""
```

В обработчике `/v1/net` команда берётся из `net_command`; пустая команда — `503`, без
запуска `net.py`. На Windows поведение прежнее: там нет `/proc`, но остаётся чтение
окружения процесса через PEB/отладчик — это отдельный срез, не притворяться, что
namespace его закрыл.

После CI-падения C-0324 добавлена проба `Bridge.unshare_works`: один раз на процесс
`unshare -U -p -f --mount-proc <python> -c pass` в allowlist-окружении. Если user
namespace запрещён (CI-раннер, Ubuntu 24.04), `net_command` возвращает отказ, и мост
отвечает `503`, а не `200` с ошибкой уже упавшего `unshare` (C-0329, R2). Env-тест
C-0324 на Linux использует shim launcher'а: он проверяет наследование окружения,
namespace проверяют R1/R2.

## Тест (red → green)

`tests/test_bridge_net_namespace.py` (Linux/WSL; на Windows делегирует в WSL):

1. Поднять мост на loopback с синтетическим `HS_BRIDGE_KEY` и подставным `net.py`.
2. Подставной `net.py` печатает `NET_PROBE=1` (положительный контроль) и ищет
   `HS_BRIDGE_KEY=<канарейка>` по всему `/proc/*/environ`; печатает `FOUND_ANY`.
3. До изменения: `NET_PROBE=1`, `FOUND_ANY=1` — тест красный (4 провала).
4. После изменения: `NET_PROBE=1`, `FOUND_ANY=0` — тест зелёный (11/11).
5. При отсутствии `unshare` мост отвечает `503` с причиной «не найден», а `net.py`
   не исполняется (отрицательный контроль fail-closed).
6. Если `unshare` найден, но не работает (подставной бинарник с exit 1), мост
   отвечает `503` с причиной «не работает» и `net.py` не исполняется; зелёный
   прогон — 16 ok, провалов 0.

Поддерживающее измерение — `python bin/proc_isolation.py`; оно уже показывает
A `FOUND=1` / B `FOUND=0` и не заменяет интеграционный тест.

## Что это НЕ закрывает

- **Не** защищает Windows: это отдельный механизм. Он сделан в C-0330
  ([`WINDOWS-NET-LOWIL-R1`](../research/outputs/WINDOWS-NET-LOWIL-R1-2026-11-18.txt)):
  low-IL токен не даёт прочитать PEB medium-моста; файловая система, сеть,
  token-файл и командная строка процесса там тоже не изолированы.
- **Не** изолирует файловую систему, сеть и token-файл. В user namespace ребёнок
  сохраняет доступ к файлам, которые доступны тому же uid; путь к token-файлу
  скрывается из `/proc` родителя, но не становится недоступным по известному пути.
- **Не** доказывает K9: downstream-цепочка и композиция инструментов не проверяются;
  это один канал (`/proc` + env), а не «мост безопасен».
- WSL-прогон под `uid=0(root)`; успех под root не гарантия для обычного uid, где
  `unshare -U` может быть запрещён. Поэтому проба и fail-closed, а не тихий fallback.
- Проба `unshare` кэшируется: если условия изменятся после первого запроса, она не
  повторится; это проверка старта, а не постоянный мониторинг.
- Это не активация: `active` пуст, настоящий owner-ключ не создавался, `K9_proven`
  не выдавался.

## Решение владельца

- **A. Выбрано 18.11.2026 («давай а»):** изменение `bin/bridge.py` по этому проекту
  + тест `test_bridge_net_namespace.py` (Linux fail-closed, Windows без изменений).
  Реализовано в C-0328; evidence `BRIDGE-NET-NAMESPACE-R1-2026-11-18.txt`.
- **B.** Оставить прототип как измерение — не выбрано.
- **C.** Другой механизм (отдельный uid/контейнер/Windows job object) — не выбран;
  для Windows сделан отдельный срез H-0010/C-0330 (low-IL токен).

`bin/bridge.py` изменён в рамках явного решения A; это не активация и не K9.
