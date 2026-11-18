# PROPOSAL-0002 — PID-namespace для `/v1/net` (решение владельца)

Дата: 2026-11-18. Статус: **предложение, код моста не изменён**.
Измерение: `PROC-ISOLATION-R1` / C-0327,
[`../research/outputs/PROC-ISOLATION-R1-2026-11-18.txt`](../research/outputs/PROC-ISOLATION-R1-2026-11-18.txt).

## Зачем

`BRIDGE-KEY-ISOLATION-R1` (C-0324) закрыл наследование окружения: `/v1/net` больше не
передаёт `HS_BRIDGE_KEY` ребёнку. Но на Linux ребёнок того же uid всё равно читает
**стартовое** окружение моста через `/proc/<ppid>/environ`; это подтверждено: плечо A
дало `FOUND=1, FOUND_ANY=1`. PID-namespace скрывает родителя: плечо B дало
`FOUND=0, FOUND_ANY=0`. Прототип не подключён к мосту, потому что `bin/bridge.py` —
`needs_owner` («расширение поверхности моста»).

## Предлагаемое изменение (одно место)

В `bin/bridge.py`, в ветке `/v1/net`, заменить запуск:

```python
result = subprocess.run(
    [sys.executable, str(ROOT / "bin" / "net.py"), *argv],
    ...
    env=net_child_env(), close_fds=True,
)
```

на Linux-ветку:

```python
def net_argv(argv: list[str]) -> tuple[list[str], str]:
    """Linux: ребёнок в PID-namespace; иначе — текущий запуск."""
    command = [sys.executable, str(ROOT / "bin" / "net.py"), *argv]
    if not sys.platform.startswith("linux"):
        return command, ""
    unshare = shutil.which("unshare")
    if not unshare:
        return [], "unshare не найден: /v1/net выключен (fail-closed)"
    return [unshare, "-U", "-p", "-f", "--mount-proc", *command], ""
```

и при ошибке `net_argv` отвечать `503`/`504` с внятным текстом, **не** откатываться
молча к неизолированному запуску. На Windows поведение остаётся прежним: там нет
`/proc`, но остаётся чтение окружения процесса через PEB/отладчик — это отдельный
срез, не притворяться, что namespace его закрыл.

## Тест, который должен стать красным до и зелёным после

Новый `tests/test_bridge_net_namespace.py` (Linux/WSL; на Windows — N/A, не «зелёный»):

1. Поднять мост на loopback с синтетическим `HS_BRIDGE_KEY` и подставным `net.py`.
2. Подставной `net.py` печатает `NET_PROBE=1` (положительный контроль) и ищет
   `HS_BRIDGE_KEY=<канарейка>` по всему `/proc/*/environ`; печатает `FOUND_ANY`.
3. До изменения: `NET_PROBE=1`, `FOUND_ANY=1` — тест красный.
4. После изменения: `NET_PROBE=1`, `FOUND_ANY=0` — тест зелёный.
5. Проверить, что при отсутствии `unshare` мост отвечает отказом, а не запускает
   `net.py` без изоляции (отрицательный контроль fail-closed).

Поддерживающее измерение — `python bin/proc_isolation.py`; оно уже показывает
A `FOUND=1` / B `FOUND=0` и не заменяет интеграционный тест.

## Что это НЕ закрывает

- **Не** защищает Windows: там нужен отдельный механизм (job object/AppContainer/
  отдельный uid), это следующий срез.
- **Не** изолирует файловую систему, сеть и token-файл. В user namespace ребёнок
  сохраняет доступ к файлам, которые доступны тому же uid; путь к token-файлу
  скрывается из `/proc` родителя, но не становится недоступным по известному пути.
- **Не** доказывает K9: downstream-цепочка и композиция инструментов не проверяются;
  это один канал (`/proc` + env), а не «мост безопасен».
- WSL-прогон под `uid=0(root)`; успех под root не гарантия для обычного uid, где
  `unshare -U` может быть запрещён. Поэтому fail-closed, а не тихий fallback.
- Это не активация: `active` пуст, настоящий owner-ключ не создавался, `K9_proven`
  не выдавался.

## Решение владельца

- **A.** Разрешить изменение `bin/bridge.py` по этому проекту + тест
  `test_bridge_net_namespace.py` (Linux fail-closed, Windows без изменений).
- **B.** Оставить прототип как измерение; мост не трогать, остаток записан в C-0324/
  C-0327 и в handoff.
- **C.** Другой механизм (отдельный uid/контейнер/Windows job object) — тогда этот
  проект не применяется, нужен новый срез.

Без явного выбора владельца проект остаётся документом; `bin/bridge.py` не меняется.
