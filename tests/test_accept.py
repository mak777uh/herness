"""Тесты приёмки: критерий, объявленный до прогона, обязан уметь не пройти."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import accept  # noqa: E402

CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def journal_bytes(events: list[str], *, break_seq: int | None = None,
                  torn: bytes = b"", commit: bool = True) -> bytes:
    """Собрать журнал HSJ1 по правилам Rust-ядра: len, seq, crc(sha256), kind, payload."""
    out = bytearray(b"HSJ1" + (1).to_bytes(4, "little"))
    records = [(1, text.encode("utf-8")) for text in events]
    if commit:
        records.append((2, b""))
    for seq, (kind, payload) in enumerate(records, start=1):
        head = len(payload).to_bytes(4, "little") + seq.to_bytes(8, "little")
        fragment = hashlib.sha256(head + payload).digest()
        crc = int.from_bytes(fragment[:4], "little")
        if break_seq is not None and seq == break_seq:
            crc ^= 0xFFFF
        out += head + crc.to_bytes(4, "little") + bytes([kind]) + payload
    out += torn
    return bytes(out)


OK_RUN = [
    "run/start task: найти опору",
    "tool/call search /mnt CLAIMS",
    "tool/result ok /mnt/CLAIMS.md:4: опора",
    "step 1, потрачено 0.00010000",
    "claim/anchored /mnt/CLAIMS.md:4",
    "run/end Опора лежит в /mnt/CLAIMS.md:4",
]

CRITERIA = {
    "task": "найти опору",
    "require_status": "done",
    "must_call": ["search"],
    "must_not_call": ["write"],
    "anchor_regex": r"CLAIMS\.md:\d+",
    "max_steps": 4,
    "max_allowance": 0.001,
    "require_commit": True,
}


def run(criteria: dict, events: list[str], **kwargs) -> tuple[bool, list]:
    records, tail, problems = accept.parse_journal(journal_bytes(events, **kwargs))
    ok, rows = accept.check(criteria, records)
    return ok and not problems and not tail, rows


@case("полный прогон по критерию проходит")
def _():
    ok, rows = run(CRITERIA, OK_RUN)
    assert ok, rows
    assert len(rows) == 7, rows


@case("невызванный инструмент валит приёмку")
def _():
    ok, rows = run(CRITERIA, [e for e in OK_RUN if not e.startswith("tool/call")])
    assert not ok, rows
    assert any("search" in detail for _, passed, detail in rows if not passed), rows


@case("запрещённый инструмент валит приёмку")
def _():
    events = OK_RUN + ["tool/call write /mnt/x текст", "tool/result ok записано"]
    events.insert(-1, "claim/anchored /mnt/CLAIMS.md:4")
    ok, rows = run(CRITERIA, events)
    assert not ok, rows
    assert any("write" in detail for _, passed, detail in rows if not passed), rows


@case("опора не того вида валит приёмку")
def _():
    events = [e for e in OK_RUN if not e.startswith("claim/anchored")]
    events.insert(-1, "claim/anchored просто слово")
    ok, rows = run(CRITERIA, events)
    assert not ok, rows


@case("без опоры прогон не считается выполненным")
def _():
    events = [e for e in OK_RUN if not e.startswith("claim/anchored")]
    events.insert(-1, "claim/unverified в ответе нет элемента из результатов")
    ok, rows = run({"task": "x", "require_status": "done"}, events)
    assert not ok, rows
    assert any("unverified" in detail for _, passed, detail in rows if not passed), rows


@case("превышение шагов валит приёмку")
def _():
    events = OK_RUN + [f"step {n}, потрачено 0.00020000" for n in range(2, 6)]
    ok, rows = run(CRITERIA, events)
    assert not ok, rows
    assert any("шагов ≤ 4" == name for name, passed, _ in rows if not passed), rows


@case("превышение расхода валит приёмку")
def _():
    events = [e.replace("0.00010000", "0.00500000") for e in OK_RUN]
    ok, rows = run(CRITERIA, events)
    assert not ok, rows


@case("оборванный хвост не чинится и валит приёмку")
def _():
    records, tail, problems = accept.parse_journal(journal_bytes(OK_RUN, torn=b"\x10\x00\x00\x00"))
    ok, _rows = accept.check(CRITERIA, records)
    assert ok, "содержимое целых записей должно читаться"
    assert tail == 4 and problems, (tail, problems)


@case("испорченная CRC отсекает запись и всё после неё")
def _():
    records, tail, problems = accept.parse_journal(journal_bytes(OK_RUN, break_seq=3))
    assert len(records) == 2, len(records)
    assert tail > 0 and problems, (tail, problems)


@case("журнал без коммита валит приёмку")
def _():
    records, tail, problems = accept.parse_journal(journal_bytes(OK_RUN, commit=False))
    ok, rows = accept.check(CRITERIA, records)
    assert not problems and not tail, (tail, problems)
    assert not ok, rows
    assert any("коммит" in name for name, passed, _ in rows if not passed), rows


@case("чужой заголовок не разбирается")
def _():
    records, tail, problems = accept.parse_journal(b"XXXX" + b"\x01\x00\x00\x00")
    assert records == [] and problems, (records, tail, problems)


@case("пустой критерий не проходит")
def _():
    ok, rows = run({}, OK_RUN)
    assert not ok and len(rows) == 1 and not rows[0][1], rows


@case("критерий из файла читается CLI и печатает итог")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        crit = Path(tmp) / "c.json"
        crit.write_text(json.dumps(CRITERIA, ensure_ascii=False), encoding="utf-8")
        log = Path(tmp) / "j.bin"
        log.write_bytes(journal_bytes(OK_RUN))
        assert accept.main([str(crit), str(log)]) == 0
        unverified = [e for e in OK_RUN if not e.startswith("claim/anchored")]
        unverified.insert(-1, "claim/unverified нет опоры")
        log.write_bytes(journal_bytes(unverified))
        assert accept.main([str(crit), str(log)]) == 1


@case("критерии в комнату не попадают: образа касается только names()")
def _():
    from bin import make_initramfs

    names = make_initramfs.names("check")
    assert "init" in names, names
    leaked = [name for name in names if name.startswith("accept") or "criteria" in name]
    assert leaked == [], leaked
    for path in sorted((ROOT / "accept").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("task"), path
        checks = {"require_status", "must_call", "must_not_call", "anchor_regex",
                  "max_steps", "max_allowance", "require_commit", "require_events"}
        assert checks & set(data), f"{path.name}: ни одного условия"
        assert "comment" in data, f"{path.name}: нет пояснения, зачем критерий такой"


@case("скрытая часть проходит — приёмка проходит")
def _():
    spec = dict(CRITERIA, hidden={"anchor_regex": r"CLAIMS\.md:\d+"})
    ok, rows = run(spec, OK_RUN)
    assert ok, rows
    assert any("скрытая часть" in name for name, _, _ in rows), rows


@case("скрытая часть проваливается — приёмка падает, причина не раскрыта")
def _():
    spec = dict(CRITERIA, hidden={"anchor_regex": r"ZZZ-нет-такого"})
    ok, rows = run(spec, OK_RUN)
    assert not ok, rows
    detail = next(detail for name, passed, detail in rows
                  if "скрытая часть" in name and not passed)
    assert "ZZZ" not in detail, detail
    assert "--show-hidden" in detail, detail


@case("с --show-hidden автор видит, какое условие провалилось")
def _():
    spec = dict(CRITERIA, hidden={"anchor_regex": r"ZZZ-нет-такого"})
    records, _tail, _problems = accept.parse_journal(journal_bytes(OK_RUN))
    ok, rows = accept.check(spec, records, show_hidden=True)
    assert not ok, rows
    detail = next(detail for name, passed, detail in rows
                  if "скрытая часть" in name and not passed)
    assert "ZZZ" in detail, detail


@case("неизвестное условие критерия — провал, а не пропуск")
def _():
    ok, rows = run(dict(CRITERIA, лишнее_условие=True), OK_RUN)
    assert not ok, rows
    assert any("понятно" in name and not passed for name, passed, _ in rows), rows


@case("вызов вне объявленной выдачи валит приёмку")
def _():
    events = list(OK_RUN)
    events.insert(-1, "tool/call write /mnt/x текст")
    events.insert(-1, "tool/result ok записано")
    ok, rows = run(dict(CRITERIA, tools=["search", "read"]), events)
    assert not ok, rows
    assert any("вне выдачи" in detail for _, passed, detail in rows if not passed), rows


@case("отказ по невыданному инструменту нарушением не считается")
def _():
    events = list(OK_RUN)
    events.insert(-1, "tool/call write /mnt/x текст")
    events.insert(-1, "tool/result err инструмент write не выдан в этом прогоне")
    ok, rows = run(dict(CRITERIA, tools=["search", "read"], must_not_call=[]), events)
    assert ok, rows


@case("стадия берётся из журнала: unrecorded и blocked")
def _():
    host_fail = list(OK_RUN)
    host_fail.insert(4, "step/error хост не подтвердил шаг: недоступен")
    records, _tail, _p = accept.parse_journal(journal_bytes(host_fail))
    ok, rows = accept.check({"task": "x", "require_status": "done"}, records)
    assert not ok, rows
    assert any("unrecorded" in detail for _, passed, detail in rows if not passed), rows

    blocked = ["run/start task: x", "run/blocked нужен доступ", "run/end ждёт человека"]
    records, _tail, _p = accept.parse_journal(journal_bytes(blocked))
    ok, rows = accept.check({"task": "x", "require_status": "blocked"}, records)
    assert ok, rows


@case("порог барахтания отсекает повторные вызовы")
def _():
    repeated = [
        "run/start task: t",
        "tool/call search /mnt a",
        "tool/result ok ничего",
        "step 1, потрачено 0.00010000",
        "tool/call search /mnt a",
        "tool/result ok ничего",
        "step 2, потрачено 0.00020000",
        "claim/anchored C-0001",
        "run/end C-0001",
    ]
    spec = dict(CRITERIA, max_repeat_ratio=0.35)
    ok, rows = run(spec, repeated)
    assert not ok, rows
    assert any("повторов" in detail for _, passed, detail in rows if not passed), rows



@case("много вызовов без опоры — отдельный отказ")
def _():
    many = [
        "run/start task: t",
    ]
    for index in range(12):
        many += [f"tool/call search /mnt шаг{index}", "tool/result ok ничего",
                 f"step {index + 1}, потрачено 0.00010000"]
    many += ["claim/unverified нет опоры", "run/end готово"]
    spec = dict(CRITERIA, max_calls_without_claim=10)
    ok, rows = run(spec, many)
    assert not ok, rows
    assert any("вызовах есть опора" in name and not passed for name, passed, _ in rows), rows
    # короткий прогон с опорой условие проходит
    ok_ok, rows_ok = run(spec, OK_RUN)
    assert any("вызовах есть опора" in name and passed for name, passed, _ in rows_ok), rows_ok


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            ok_case = True
        except AssertionError:
            ok_case = False
        failed += 0 if ok_case else 1
        print(f"[{'ok' if ok_case else 'FAIL'}] {name}")
    print(f"\nприёмка: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

