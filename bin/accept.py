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

Проверка читает журнал (HSJ2) и сверяет каждое условие отдельно; итог — таблица с причинами.
"""

from __future__ import annotations

# Журнал хоста нужен приёмке для проверки подтверждения. Два пути импорта: как пакет (`bin.accept`)
# и как скрипт (`python bin/accept.py`), где пакета `bin` на пути нет.
try:
    from bin import host_journal, journal_event  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    try:
        import host_journal  # type: ignore[import-not-found,no-redef]
        import journal_event  # type: ignore[import-not-found,no-redef]
    except Exception:  # noqa: BLE001
        host_journal = None  # type: ignore[assignment]
        journal_event = None  # type: ignore[assignment]

import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

MAGIC = b"HSJ2"
RECORD_HEADER = 17
VERSION = 2  # HSJ2 (ADR-0056): CRC покрывает len+seq+kind+payload; старые HSJ1 отвергаются


class JournalRecords(list[tuple[int, str]]):
    """Parsed records вместе с целостностью всего журнала.

    API parse_journal сохранён: records ведёт себя как обычный список, но прямой
    ``accept.check(criteria, records)`` больше не теряет tail/problems, если caller
    не сохранил их отдельно. Вручную сконструированный список считается чистым.
    """

    def __init__(self, records=(), *, tail: int = 0, problems: list[str] | None = None):
        super().__init__(records)
        self.tail = tail
        self.problems = list(problems or [])

    @property
    def complete(self) -> bool:
        return self.tail == 0 and not self.problems


def parse_journal(data: bytes) -> tuple[list[tuple[int, str]], int, list[str]]:
    """Разобрать журнал: (записи (kind, payload), длина хвоста, проблемы).

    Повторяет правила Rust-ядра: остановка на первой невалидной записи, хвост не «чинится».
    """
    problems: list[str] = []
    if len(data) < 8 or data[:4] != MAGIC:
        problems = ["нет заголовка HSJ2"]
        return (JournalRecords(tail=len(data), problems=problems), len(data), problems)
    version = int.from_bytes(data[4:8], "little")
    if version != VERSION:
        problems = [f"версия {version} не поддерживается (нужен HSJ2)"]
        return (JournalRecords(tail=len(data), problems=problems), len(data), problems)

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
        # HSJ2 (ADR-0056): kind входит в CRC — порядок len+seq, kind, payload (как в Rust).
        digest = hashlib.sha256(data[pos : pos + 12] + bytes([kind]) + payload).digest()
        expected_crc = int.from_bytes(digest[:4], "little")
        if expected_crc != crc or seq != expected_seq or kind not in (1, 2):
            break
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"invalid UTF-8 в записи {seq}")
            break
        records.append((kind, text))
        expected_seq += 1
        pos = end
    tail = len(data) - pos
    if tail:
        problems.append(f"оборванный хвост {tail} байт")
    return (JournalRecords(records, tail=tail, problems=problems), tail, problems)


def events(records: list[tuple[int, str]]) -> list[tuple[str, str]]:
    """Только события данных, разделённые на вид и подробность."""
    out = []
    for kind, payload in records:
        if kind != 1:
            continue
        head, _, rest = payload.partition(" ")
        out.append((head, rest))
    return out


def payloads(records: list[tuple[int, str]]) -> list[str]:
    """Точные payload событий данных: host_match хеширует байты без реконструкции."""
    return [payload for kind, payload in records if kind == 1]


def tool_pairing_problems(evs: list[tuple[str, str]]) -> list[str]:
    """Lifecycle пар: call→result→step; duplicate run/end и события после него запрещены.

    Первое событие обязано быть run/start. Отсутствие run/end остаётся отдельным
    статусом no-done; требование последнего run/end дополнительно проверяет Rust
    verify_order. Исходный pairing corpus не содержит wrong-first/wrong-last границ.
    """
    problems: list[str] = []
    if not evs:
        return ["событий нет"]
    if evs[0][0] != "run/start":
        problems.append(f"первое событие {evs[0][0]}, а не run/start")

    phase = "idle"  # idle → waiting-result → waiting-step → idle
    ended = False
    calls = 0
    steps = 0
    for kind, _rest in evs:
        if ended:
            problems.append(f"событие {kind} после run/end")
        if kind == "run/end":
            if ended:
                problems.append("повторный run/end")
            ended = True
        elif kind == "tool/call":
            calls += 1
            if phase == "waiting-result":
                problems.append("tool/call без result предшествующего вызова")
            elif phase == "waiting-step":
                problems.append("tool/call без завершающего step предшествующего вызова")
            else:
                phase = "waiting-result"
        elif kind == "tool/result":
            if phase != "waiting-result":
                problems.append("tool/result без предшествующего tool/call")
            else:
                phase = "waiting-step"
        elif kind == "step":
            steps += 1
            if phase == "waiting-result":
                problems.append("step до tool/result")
            elif phase != "waiting-step":
                problems.append("step без предшествующего tool/result")
            else:
                phase = "idle"
    if phase == "waiting-result":
        problems.append("tool/call без tool/result")
    elif phase == "waiting-step":
        problems.append("tool/call без завершающего step")
    if steps != calls:
        problems.append(f"шагов {steps}, вызовов {calls}")
    return problems


KNOWN_KEYS = {
    "task", "comment", "hidden", "require_status", "must_call", "must_not_call",
    "anchor_regex", "max_steps", "max_allowance", "require_commit", "require_events", "min_objects",
    "tools", "host_run", "host_session", "scope", "host_match", "max_repeat_ratio", "max_calls_without_claim",
}
# Это проверки формы метаданных, а не самостоятельные критерии приёмки. Они должны валить
# malformed criterion, но не заменять реальное visible/hidden условие (W07B-REVIEW3/REVIEW4).
_BINDING_VALIDATION_ROWS = {
    "host_session привязана к host_run",
    "host_match привязан к host_run",
}


def _has_substantive_rows(rows: list[tuple[str, bool, str]]) -> bool:
    return any(name not in _BINDING_VALIDATION_ROWS for name, _ok, _detail in rows)


_STRING_KEYS = {"task", "comment", "require_status", "anchor_regex", "host_run", "host_session"}
_BOOL_KEYS = {"require_commit", "host_match"}
_INT_KEYS = {"max_steps", "min_objects", "max_calls_without_claim"}
_NUMBER_KEYS = {"max_allowance", "max_repeat_ratio"}
_STRING_LIST_KEYS = {"must_call", "must_not_call", "require_events", "tools", "scope"}


def _finite_number(value: object) -> bool:
    # bool — подкласс int, но не числовой порог. Большие ints конечны и не требуют float cast.
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _criterion_errors(criteria: dict, *, nested: bool) -> list[str]:
    """Имена известных полей с неверным типом/значением; значения не попадают в отчёт."""
    errors: list[str] = []
    for key, value in criteria.items():
        if key == "hidden":
            if nested:
                errors.append(key)
            continue
        if key in _STRING_KEYS and not isinstance(value, str):
            errors.append(key)
        elif key in _BOOL_KEYS and type(value) is not bool:
            errors.append(key)
        elif key in _INT_KEYS and type(value) is not int:
            errors.append(key)
        elif key in _NUMBER_KEYS and not _finite_number(value):
            errors.append(key)
        elif key in _STRING_LIST_KEYS and not (
            isinstance(value, list) and all(isinstance(item, str) for item in value)
        ):
            errors.append(key)
    pattern = criteria.get("anchor_regex")
    if isinstance(pattern, str):
        try:
            re.compile(pattern)
        except (re.error, OverflowError, RecursionError):
            errors.append("anchor_regex")
    return sorted(set(errors))


def _rows(criteria: dict, evs: list[tuple[str, str]], kinds: list[str],
          records: list[tuple[int, str]]) -> list[tuple[str, bool, str]]:
    """Условия одной части критерия: видимой или скрытой."""
    rows: list[tuple[str, bool, str]] = []

    def status() -> str:
        # Стадия выводится одним правилом «чего прогон ждёт», а не собирается в трёх местах
        # (H-0008): сначала терминальные исходы, потом наличие опоры, потом всё остальное.
        errors = [rest for kind, rest in evs if kind == "step/error"]
        if "run/blocked" in kinds:
            return "blocked"
        if "run/no-work" in kinds:
            return "no-work"
        if any("хост не подтвердил" in text for text in errors):
            return "unrecorded"
        if any("бюджет денег" in text for text in errors):
            return "budget-money"
        if any("бюджет времени" in text for text in errors):
            return "budget-time"
        if any("не сообщил расход" in text for text in errors):
            return "unknown-cost"
        if "run/end" not in kinds:
            return "no-done"
        if any(kind == "run/end" and rest.startswith("шаги кончились") for kind, rest in evs):
            return "no-done"
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

    if "min_objects" in criteria:
        # Опора ловится на одном файле, поэтому ответ про совокупность ею не проверяется (A-0020).
        # Считаем разные объекты в вызовах: для подсчёта нужно открыть несколько, а не один.
        objects = set()
        for kind, rest in evs:
            if kind != "tool/call":
                continue
            parts = rest.split()
            if len(parts) < 2:
                continue
            objects.add(" ".join(parts[1:]).strip())
        need = int(criteria["min_objects"])
        rows.append((f"объектов открыто ≥ {need}", len(objects) >= need, f"открыто: {len(objects)}"))

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
        costs = [rest for kind, rest in evs if kind == "step"]
        values: list[float] = []
        cost_problem = "нет стоимости шагов"
        number = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
        for detail in costs:
            match = re.fullmatch(rf"[0-9]+, потрачено ({number})", detail)
            if match is None:
                cost_problem = "неизвестная или malformed стоимость"
                break
            value = float(match.group(1))
            if not math.isfinite(value) or value < 0:
                cost_problem = "стоимость отрицательная или не конечна"
                break
            values.append(value)
        unknown_cost = any(
            kind == "step/error" and "не сообщил расход" in rest
            for kind, rest in evs
        )
        spent = max(values) if values else 0.0
        passed = bool(values) and len(values) == len(costs) and not unknown_cost and spent <= criteria["max_allowance"]
        detail = f"потрачено: {spent:.8f} (оценка провайдера, не факт биллинга)"
        if not costs:
            detail = "нет стоимости шагов; бюджет проверить нельзя"
        elif cost_problem != "нет стоимости шагов" or len(values) != len(costs):
            detail = cost_problem + "; бюджет проверить нельзя"
        elif unknown_cost:
            detail = "провайдер не сообщил расход; бюджет проверить нельзя"
        # F-MONEY-2 (08.11.2026). Число из журнала — это `usage.allowance`
        # провайдера, то есть ОЦЕНКА расхода, а не факт биллинга. Раньше оно
        # подавалось как «потрачено», и оценка выглядела фактом: в знаменатель
        # CostPerVerifiedSuccess (AGENTS.md §5) годится только факт.
        # Формат `потрачено: N` сохранён — на него смотрят парсеры и тесты;
        # пометка добавлена рядом.
        rows.append((f"расход ≤ {criteria['max_allowance']}", passed, detail))

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
                if pending not in granted and not (
                    journal_event is not None
                    and journal_event.exact_grant_refusal(rest, pending)
                ):
                    violations.append(pending)
                pending = None
        rows.append((f"работали только выданные {sorted(granted)}", not violations,
                     f"вне выдачи выполнены: {violations}"))

    for wanted in criteria.get("require_events", []):
        rows.append((f"есть событие {wanted}", wanted in kinds, f"виды: {sorted(set(kinds))}"))

    if "host_session" in criteria and "host_run" not in criteria:
        rows.append(("host_session привязана к host_run", False, "нет ожидаемого host_run"))

    if criteria.get("host_match") and "host_run" not in criteria:
        rows.append(("host_match привязан к host_run", False, "нет ожидаемого host_run"))

    if "host_run" in criteria:
        # Подтверждение хостом: авторитетную копию ведёт хост, и без неё прогон не принимается.
        # host_match требует ожидаемую host_session ДО чтения цепочки: иначе критерий может
        # случайно подтвердить события другого прогона/сессии.
        session = criteria.get("host_session")
        session_ok = journal_event is not None and journal_event.valid_session(session)
        if criteria.get("host_match") and not session_ok:
            rows.append(("ожидаемая host_session задана", False, "host_match без canonical host_session"))
        elif host_journal is None:
            rows.append(("журнал хоста проверен", False, "модуль host_journal недоступен"))
        else:
            good, problems = host_journal.verify(str(criteria["host_run"]))
            rows.append((
                f"хост подтвердил прогон {criteria['host_run']}",
                good > 0 and not problems,
                f"записей: {good}" + (f"; проблемы: {problems[:1]}" if problems else ""),
            ))
            if criteria.get("host_match"):
                try:
                    host_events = [
                        journal_event.canonical(journal_event.decode_host_event(entry, session))
                        for entry in host_journal.events(str(criteria["host_run"])) if entry
                    ]
                    room_events = [
                        journal_event.canonical(payload)
                        for payload in journal_event.project_payloads(payloads(records), session)
                    ]
                    complete = getattr(records, "complete", True)
                    matched = complete and bool(host_events) and room_events == host_events
                    detail = f"хост видел {len(host_events)} событий, в комнате {len(room_events)}"
                    if not complete:
                        detail += "; журнал комнаты повреждён"
                except (journal_event.EventError, ValueError, TypeError):
                    matched = False
                    detail = "typed host/room projection невалидна"
                rows.append(("журнал комнаты совпадает с хостовым", matched,
                             detail + ("" if matched else "; события расходятся")))

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
    visible_errors = _criterion_errors(criteria, nested=False)
    rows: list[tuple[str, bool, str]] = []
    if visible_errors:
        for key in visible_errors:
            rows.append((f"условие {key} понятно", False, "неверный тип или значение условия"))
    else:
        try:
            rows = _rows(criteria, evs, kinds, records)
        except (TypeError, ValueError, re.error, OverflowError, OSError):
            # Ошибка вычисления не становится PASS и не печатает значения критерия.
            rows.append(("условия критерия проверены", False, "не удалось проверить условие"))
    # Integrity — обязательная проверка, но не заменяет содержательный критерий. Иначе
    # task/comment/host_match без проверяемых условий получали PASS от одной этой строки.
    has_substantive_checks = _has_substantive_rows(rows)
    complete = getattr(records, "complete", True)
    tail = getattr(records, "tail", 0)
    problems = getattr(records, "problems", [])
    detail = f"tail={tail}; problems={len(problems)}"
    if problems:
        detail += "; " + "; ".join(problems[:3])
    rows.append(("журнал прочитан полностью", complete, detail))
    pairing_problems = tool_pairing_problems(evs)
    rows.append((
        "каждый tool/call имеет ровно один tool/result",
        not pairing_problems,
        "; ".join(pairing_problems) if pairing_problems else "пары корректны",
    ))

    # Неизвестное условие — это не «пропустим», а провал: опечатка в имени условия иначе тихо
    # отключала бы проверку.
    for key in sorted(set(criteria) - KNOWN_KEYS):
        rows.append((f"условие {key} понятно", False, "неизвестное условие критерия"))

    hidden = criteria.get("hidden")
    if "hidden" in criteria and not isinstance(hidden, dict):
        # Присутствующий malformed hidden — не «нет проверки», а провал: иначе опечатка
        # в критерии тихо отключает held-out часть рядом с проходящим visible positive.
        if show_hidden:
            detail = "не выполнена: hidden должен быть объектом"
        else:
            detail = "не выполнена (какие условия — на хосте, см. --show-hidden)"
        rows.append(("скрытая часть критерия", False, detail))
    elif isinstance(hidden, dict) and hidden:
        hidden_errors = _criterion_errors(hidden, nested=True)
        hidden_unknown = sorted(set(hidden) - KNOWN_KEYS)
        hidden_rows: list[tuple[str, bool, str]] = []
        evaluation_failed = False
        if not hidden_errors:
            try:
                hidden_rows = _rows(hidden, evs, kinds, records)
            except (TypeError, ValueError, re.error, OverflowError, OSError):
                # Hidden values не попадают в stderr даже при необработанном условии.
                evaluation_failed = True
        has_substantive_checks = has_substantive_checks or _has_substantive_rows(hidden_rows)
        hidden_ok = (
            not hidden_errors
            and not evaluation_failed
            and bool(hidden_rows)
            and not hidden_unknown
            and all(ok for _, ok, _ in hidden_rows)
        )
        if hidden_ok:
            detail = "выполнена"
        elif show_hidden:
            failures = [f"некорректное условие {key}" for key in hidden_errors]
            if evaluation_failed:
                failures.append("не удалось проверить скрытое условие")
            failures += [name for name, ok, _ in hidden_rows if not ok]
            failures += [f"неизвестное условие {key}" for key in hidden_unknown]
            detail = "не выполнена: " + "; ".join(failures)
        else:
            detail = "не выполнена (какие условия — на хосте, см. --show-hidden)"
        rows.append(("скрытая часть критерия", hidden_ok, detail))

    if not has_substantive_checks:
        rows.append(("есть содержательная проверка", False,
                     "критерий не задаёт содержательных проверок"))

    return (has_substantive_checks and all(ok for _, ok, _ in rows), rows)


class CriterionError(ValueError):
    """Критерий не читается как строгий JSON объект."""


def _criterion_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise CriterionError("критерий содержит повторяющийся JSON ключ")
        result[key] = value
    return result


def _reject_constant(_text: str) -> object:
    raise CriterionError("критерий содержит non-finite JSON число")


def _check_criterion_json(value: object) -> None:
    """JSON criterion состоит только из конечных чисел и валидных UTF-8 строк."""
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            # json.loads принимает escaped lone surrogate, но такой критерий нельзя
            # безопасно напечатать. Отказываем до check и без значения в диагностике.
            raise CriterionError("критерий содержит недопустимую Unicode строку") from None
        return
    if type(value) is float and not math.isfinite(value):
        raise CriterionError("критерий содержит non-finite JSON число")
    if isinstance(value, list):
        for item in value:
            _check_criterion_json(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_criterion_json(key)
            _check_criterion_json(item)


def _load_criteria(path: Path) -> dict:
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_criterion_pairs,
            parse_constant=_reject_constant,
        )
        _check_criterion_json(data)
    except CriterionError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise CriterionError("критерий не является строгим JSON объектом") from None
    if not isinstance(data, dict):
        raise CriterionError("критерий должен быть объектом JSON")
    return data


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    show_hidden = "--show-hidden" in argv
    argv = [arg for arg in argv if arg != "--show-hidden"]
    if len(argv) < 2:
        print("accept <критерий.json> <журнал.bin> [--show-hidden]", file=sys.stderr)
        return 2
    try:
        criteria = _load_criteria(Path(argv[0]))
    except CriterionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
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






