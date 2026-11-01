"""accept — приёмка прогона по критерию, объявленному ДО работы и невидимому исполнителю.

Почему именно так (по итогам P25):
  * критерий пишется до прогона (pre-registration) — иначе его подгонят под результат;
  * проверка исполняется ВНЕ комнаты: агент работает в гостевой системе, а приёмка читает журнал
    на хосте. Внутри комнаты он мог бы изменить проверялку (reward hacking: RHB 2026 — эксплуатация
from collections import Counter
    в 0–13,9 % эпизодов, а «укрепление среды» снижает её на 5,7 п.п. без потери успешности);
  * критерий не показывается модели: она видит только задачу;
  * провал — это провал: нет файла, нет записи, нет опоры — FAIL, а не «наверное, всё хорошо».

Формат критерия (JSON):

    {
      "task": "идентификатор задачи",
      "require_status": "done",
      "must_call": ["search"],
      "must_not_call": ["write", "exec"],
      "anchor_regex": "CLAIMS\\.md:\\d+",
      "max_steps": 8,
      "max_allowance": 0.01,
      "require_events": ["claim/anchored"]
    }

Проверка читает журнал (HSJ1) и сверяет каждое условие отдельно; итог — таблица с причинами.
"""

from __future__ import annotations

# Журнал хоста нужен приёмке для проверки подтверждения. Два пути импорта: как пакет (`bin.accept`)
# и как скрипт (`python bin/accept.py`), где пакета `bin` на пути нет.
try:
    from bin import host_journal  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    try:
        import host_journal  # type: ignore[import-not-found,no-redef]
    except Exception:  # noqa: BLE001
        host_journal = None  # type: ignore[assignment]

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

MAGIC = b"HSJ1"
RECORD_HEADER = 17


def parse_journal(data: bytes) -> tuple[list[tuple[int, str]], int, list[str]]:
    """Разобрать журнал: (записи (kind, payload), длина хвоста, проблемы).

    Повторяет правила Rust-ядра: остановка на первой невалидной записи, хвост не «чинится».
    """
    problems: list[str] = []
    if len(data) < 8 or data[:4] != MAGIC:
        return ([], len(data), ["нет заголовка HSJ1"])
    version = int.from_bytes(data[4:8], "little")
    if version != 1:
        return ([], len(data), [f"версия {version} не поддерживается"])

    pos = 8
    expected_seq = 1
    records: list[tuple[int, str]] = []
    while pos < len(data):
        if len(data) - pos < RECORD_HEADER:
            break
        length = int.from_bytes(data[pos : pos + 4], "little")
        seq = int.from_bytes(data[pos + 4 : pos + 12], "little")
        crc = int.from_bytes(data[pos + 12 : pos + 16], "little")
        kind = data[pos + 16]
        if length > 64 * 1024 * 1024:
            break
        end = pos + RECORD_HEADER + length
        if end > len(data):
            break
        payload = data[pos + RECORD_HEADER : end]
        digest = hashlib.sha256(data[pos : pos + 12] + payload).digest()
        expected_crc = int.from_bytes(digest[:4], "little")
        if expected_crc != crc or seq != expected_seq or kind not in (1, 2):
            break
        records.append((kind, payload.decode("utf-8", "replace")))
        expected_seq += 1
        pos = end
    tail = len(data) - pos
    if tail:
        problems.append(f"оборванный хвост {tail} байт")
    return (records, tail, problems)


def events(records: list[tuple[int, str]]) -> list[tuple[str, str]]:
    """Только события данных, разделённые на вид и подробность."""
    out = []
    for kind, payload in records:
        if kind != 1:
            continue
        head, _, rest = payload.partition(" ")
        out.append((head, rest))
    return out


KNOWN_KEYS = {
    "task", "comment", "hidden", "require_status", "must_call", "must_not_call",
    "anchor_regex", "max_steps", "max_allowance", "require_commit", "require_events",
    "tools", "host_run", "scope", "host_match", "max_repeat_ratio", "max_calls_without_claim",
}


def _rows(criteria: dict, evs: list[tuple[str, str]], kinds: list[str],
          records: list[tuple[int, str]]) -> list[tuple[str, bool, str]]:
    """Условия одной части критерия: видимой или скрытой."""
    rows: list[tuple[str, bool, str]] = []

    def status() -> str:
        # Стадия выводится одним правилом «чего прогон ждёт», а не собирается в трёх местах
        # (H-0008): сначала терминальные исходы, потом наличие опоры, потом всё остальное.
        errors = [rest for kind, rest in evs if kind == "step/error"]
        if any("хост не подтвердил" in text for text in errors):
            return "unrecorded"
        if any("бюджет денег" in text for text in errors):
            return "budget-money"
        if any("бюджет времени" in text for text in errors):
            return "budget-time"
        if "run/blocked" in kinds:
            return "blocked"
        if "run/no-work" in kinds:
            return "no-work"
        if "run/end" not in kinds:
            return "нет run/end"
        anchored = "claim/anchored" in kinds
        if "claim/unverified" in kinds and not anchored:
            return "unverified"
        return "done" if anchored else "done-без-опоры"

    if "require_status" in criteria:
        want = criteria["require_status"]
        got = status()
        rows.append((f"статус = {want}", got == want, f"фактически: {got}"))

    if "must_call" in criteria:
        called = [rest.split(" ", 1)[0] for kind, rest in evs if kind == "tool/call"]
        missing = [name for name in criteria["must_call"] if name not in called]
        rows.append((f"вызваны инструменты {criteria['must_call']}", not missing,
                     f"вызовы: {called}; не хватает: {missing}"))

    if "must_not_call" in criteria:
        called = [rest.split(" ", 1)[0] for kind, rest in evs if kind == "tool/call"]
        forbidden = [name for name in criteria["must_not_call"] if name in called]
        rows.append((f"не вызваны {criteria['must_not_call']}", not forbidden,
                     f"запрещённые вызовы: {forbidden}"))

    if "anchor_regex" in criteria:
        pattern = re.compile(criteria["anchor_regex"])
        anchored = [rest for kind, rest in evs if kind == "claim/anchored"]
        matched = [value for value in anchored if pattern.search(value)]
        # Поправка на ложный отказ (F-0028): цикл записывает в опору ПЕРВОЕ общее слово, и это
        # часто путь, а не номер. Проверяем ещё так: слово из ответа, подходящее под шаблон,
        # обязано встречаться в результатах инструментов. Это не ослабление — это тот же тест,
        # но применённый к кандидатам из ответа, а не к одному сохранённому.
        if not matched:
            results = [rest for kind, rest in evs if kind == "tool/result"]
            answers = [rest for kind, rest in evs if kind == "run/end"]
            for answer in answers:
                for token in re.findall(r"[A-Za-zА-Яа-я0-9/._-]+", answer):
                    found = pattern.search(token)
                    if not found:
                        continue
                    # Сверяем СОВПАДЕНИЕ, а не весь токен: «…/F-0029.md:4» содержит номер, но
                    # целиком в результатах не встречается (F-0037).
                    hit = found.group(0)
                    if any(hit in res for res in results):
                        matched.append(f"{hit} (из ответа, есть в результатах)")
                        break
        rows.append((f"опора соответствует /{criteria['anchor_regex']}/", bool(matched),
                     f"опоры: {(matched or anchored)[:5]}"))

    if "max_steps" in criteria:
        steps = sum(1 for kind, _ in evs if kind == "step")
        rows.append((f"шагов ≤ {criteria['max_steps']}", steps <= criteria["max_steps"],
                     f"шагов: {steps}"))

    if "max_allowance" in criteria:
        spent = 0.0
        for kind, rest in evs:
            if kind != "step":
                continue
            match = re.search(r"потрачено ([0-9.eE+-]+)", rest)
            if match:
                spent = max(spent, float(match.group(1)))
        rows.append((f"расход ≤ {criteria['max_allowance']}", spent <= criteria["max_allowance"],
                     f"потрачено: {spent:.8f}"))

    if "tools" in criteria:
        # Выдача инструментов — полномочие. Проверяем не «что модель просила», а «что сработало»:
        # вызов вне выдачи допустим только как отказ, иначе объявленная граница прогона — фикция.
        granted = set(criteria["tools"])
        violations = []
        pending = None
        for kind, rest in evs:
            if kind == "tool/call":
                pending = rest.split(" ", 1)[0]
            elif kind == "tool/result" and pending:
                if pending not in granted and "не выдан" not in rest:
                    violations.append(pending)
                pending = None
        rows.append((f"работали только выданные {sorted(granted)}", not violations,
                     f"вне выдачи выполнены: {violations}"))

    for wanted in criteria.get("require_events", []):
        rows.append((f"есть событие {wanted}", wanted in kinds, f"виды: {sorted(set(kinds))}"))

    if "host_run" in criteria:
        # Подтверждение хостом: авторитетную копию ведёт хост, и без неё прогон не принимается.
        # Проверяется не наличие файла, а сходимость цепочки — файл можно переписать.
        if host_journal is None:
            rows.append(("журнал хоста проверен", False, "модуль host_journal недоступен"))
        else:
            good, problems = host_journal.verify(str(criteria["host_run"]))
            rows.append((
                f"хост подтвердил прогон {criteria['host_run']}",
                good > 0 and not problems,
                f"записей: {good}" + (f"; проблемы: {problems[:1]}" if problems else ""),
            ))
            # Сравнение содержимого (host_match): хост получает ВЕСЬ поток событий, поэтому
            # сверяем списки целиком, без проекций и догадок о том, что доехало.
            if criteria.get("host_match"):
                host_events = [entry for entry in host_journal.events(str(criteria["host_run"])) if entry]
                room_events = [f"{kind} {rest}".strip() for kind, rest in evs]
                prefix_ok = bool(host_events) and room_events == host_events
                rows.append((
                    "журнал комнаты совпадает с хостовым",
                    prefix_ok,
                    f"хост видел {len(host_events)} событий, в комнате {len(room_events)}"
                    + ("" if prefix_ok else "; события расходятся"),
                ))

    if "max_calls_without_claim" in criteria:
        # Второй режим провала (C-0189): прогон идёт вперёд без повторов, тратит много вызовов
        # и не выдаёт опоры. Опора есть — условие не применяется; опоры нет и вызовов больше
        # порога — отказ с прямым названием причины.
        limit = int(criteria["max_calls_without_claim"])
        total = len([1 for kind, _ in evs if kind == "tool/call"])
        has_claim = "claim/anchored" in kinds
        passed = has_claim or total <= limit
        rows.append((f"при {limit}+ вызовах есть опора", passed,
                     f"вызовов {total}, опора " + ("есть" if has_claim else "нет")))

    if "max_repeat_ratio" in criteria:
        # Детектор барахтания: доля повторных одинаковых вызовов. Измерено (C-0183): на трудной
        # задаче 7 повторов из 14, на коротких — 0. Порог объявляется критерием, а не угадывается.
        calls = [rest for kind, rest in evs if kind == "tool/call"]
        repeats = sum(count - 1 for count in Counter(calls).values() if count > 1)
        ratio = (repeats / len(calls)) if calls else 0.0
        limit = float(criteria["max_repeat_ratio"])
        # ADR-0052: если ответ получен и опора есть, доля повторов — справочная величина, а не
        # вето. Отказ по ней означал бы «верный ответ не принимается за то, как он добыт».
        if "claim/anchored" in kinds:
            rows.append((f"доля повторов ≤ {limit:.2f} (справочно)", True,
                         f"повторов {repeats} из {len(calls)} ({ratio:.0%}), ответ с опорой — не вето"))
        else:
            rows.append((f"доля повторов ≤ {limit:.2f}", ratio <= limit,
                         f"повторов {repeats} из {len(calls)} ({ratio:.0%})"))

    if criteria.get("require_commit"):
        closed = bool(records) and records[-1][0] == 2
        rows.append(("журнал закрыт коммитом", closed,
                     f"последняя запись: {'коммит' if closed else 'данные или пусто'}"))

    return rows


def check(criteria: dict, records: list[tuple[int, str]],
          show_hidden: bool = False) -> tuple[bool, list[tuple[str, bool, str]]]:
    """Сверить журнал с критерием. Возвращает (итог, [(условие, выполнено, объяснение)]).

    Критерий может иметь две части: видимую и `hidden`. Зачем скрытая: видимая часть объявляется
    в отчёте, и под неё можно подогнаться; скрытая пишется заранее (в том же файле или отдельном
    коммите) и в отчёте не раскрывается. Провал скрытой части — провал приёмки, но причина не
    называется: иначе она станет частью видимой. Для разбора автором есть `show_hidden`.
    """
    if not criteria:
        return (False, [("критерий не пустой", False, "условий нет — принимать нечего")])
    evs = events(records)
    kinds = [kind for kind, _ in evs]
    rows = _rows(criteria, evs, kinds, records)

    # Неизвестное условие — это не «пропустим», а провал: опечатка в имени условия иначе тихо
    # отключала бы проверку.
    for key in sorted(set(criteria) - KNOWN_KEYS):
        rows.append((f"условие {key} понятно", False, "неизвестное условие критерия"))

    hidden = criteria.get("hidden")
    if isinstance(hidden, dict) and hidden:
        hidden_rows = _rows(hidden, evs, kinds, records)
        hidden_ok = bool(hidden_rows) and all(ok for _, ok, _ in hidden_rows)
        if hidden_ok:
            detail = "выполнена"
        elif show_hidden:
            detail = "не выполнена: " + "; ".join(name for name, ok, _ in hidden_rows if not ok)
        else:
            detail = "не выполнена (какие условия — на хосте, см. --show-hidden)"
        rows.append(("скрытая часть критерия", hidden_ok, detail))

    return (bool(rows) and all(ok for _, ok, _ in rows), rows)


def _load_criteria(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("критерий должен быть объектом JSON")
    return data


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    show_hidden = "--show-hidden" in argv
    argv = [arg for arg in argv if arg != "--show-hidden"]
    if len(argv) < 2:
        print("accept <критерий.json> <журнал.bin> [--show-hidden]", file=sys.stderr)
        return 2
    criteria = _load_criteria(Path(argv[0]))
    journal = Path(argv[1])
    if not journal.exists():
        print(f"FAIL: нет журнала {journal}", file=sys.stderr)
        return 1

    records, _tail, problems = parse_journal(journal.read_bytes())
    ok, rows = check(criteria, records, show_hidden=show_hidden)

    print(f"задача: {criteria.get('task', '?')}; записей: {len(records)}")
    for name, passed, detail in rows:
        print(f"  [{'ok' if passed else 'FAIL'}] {name} — {detail}")
    for problem in problems:
        print(f"  [!] {problem}")

    if not rows:
        print("FAIL: критерий пустой — проверять нечего")
        return 1
    print("итог:", "PASS" if ok and not problems else "FAIL")
    return 0 if ok and not problems else 1


if __name__ == "__main__":
    sys.exit(main())






