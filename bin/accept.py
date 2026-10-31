"""accept — приёмка прогона по критерию, объявленному ДО работы и невидимому исполнителю.

Почему именно так (по итогам P25):
  * критерий пишется до прогона (pre-registration) — иначе его подгонят под результат;
  * проверка исполняется ВНЕ комнаты: агент работает в гостевой системе, а приёмка читает журнал
    на хосте. Внутри комнаты он мог бы изменить проверялку (reward hacking: RHB 2026 — эксплуатация
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

import hashlib
import json
import re
import sys
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


def check(criteria: dict, records: list[tuple[int, str]]) -> tuple[bool, list[tuple[str, bool, str]]]:
    """Сверить журнал с критерием. Возвращает (итог, [(условие, выполнено, объяснение)])."""
    rows: list[tuple[str, bool, str]] = []
    if not criteria:
        return (False, [("критерий не пустой", False, "условий нет — принимать нечего")])
    evs = events(records)
    kinds = [kind for kind, _ in evs]

    def status() -> str:
        # статус — это последнее событие run/end и следующий за ним claim-вердикт
        anchored = "claim/anchored" in kinds
        if "run/end" not in kinds:
            return "нет run/end"
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
        rows.append((f"опора соответствует /{criteria['anchor_regex']}/", bool(matched),
                     f"опоры: {anchored[:5]}"))

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

    for wanted in criteria.get("require_events", []):
        rows.append((f"есть событие {wanted}", wanted in kinds, f"виды: {sorted(set(kinds))}"))

    if criteria.get("require_commit"):
        closed = bool(records) and records[-1][0] == 2
        rows.append(("журнал закрыт коммитом", closed,
                     f"последняя запись: {'коммит' if closed else 'данные или пусто'}"))

    return (all(ok for _, ok, _ in rows), rows)


def _load_criteria(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("критерий должен быть объектом JSON")
    return data


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if len(argv) < 2:
        print("accept <критерий.json> <журнал.bin>", file=sys.stderr)
        return 2
    criteria = _load_criteria(Path(argv[0]))
    journal = Path(argv[1])
    if not journal.exists():
        print(f"FAIL: нет журнала {journal}", file=sys.stderr)
        return 1

    records, _tail, problems = parse_journal(journal.read_bytes())
    ok, rows = check(criteria, records)

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
