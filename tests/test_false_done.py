"""Контрольный набор для H-0009: сколько ложных «готово» ловит приёмка.

Набор строится синтетически, и это его граница: он проверяет КЛАССИФИКАТОР, а не поведение
модели. Каждый журнал помечен заранее: «честно готово» или «выглядит готовым». Дальше два
вердикта — «по форме» (что скажет рантайм, смотрящий только на наличие run/end) и «по приёмке».

Ожидание: форма считает готовыми все шесть, приёмка — только три честных. Если это перестанет
быть так, тест падает.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import accept, false_done  # noqa: E402

CRITERIA = {
    "task": "контроль",
    "require_status": "done",
    "anchor_regex": r"C-\d{4}",
    "require_commit": True,
    "require_events": ["claim/anchored"],
}

TRUE_DONE = [
    "run/start task: найти",
    "tool/call search /mnt statistics",
    "tool/result ok найдено 1: C-0021",
    "step 1, потрачено 0.00010000",
    "claim/anchored C-0021",
    "run/end C-0021 — тип statistics",
]

FALSE_DONE = [
    "run/start task: найти",
    "tool/call list /mnt",
    "tool/result ok CLAIMS.md файл",
    "step 1, потрачено 0.00010000",
    "claim/unverified в ответе нет элемента из результатов",
    "run/end готово",
]


def journal_bytes(events: list[str]) -> bytes:
    out = bytearray(b"HSJ1" + (1).to_bytes(4, "little"))
    records = [(1, text.encode()) for text in events] + [(2, b"commit")]
    for seq, (kind, payload) in enumerate(records, start=1):
        head = len(payload).to_bytes(4, "little") + seq.to_bytes(8, "little")
        crc = int.from_bytes(hashlib.sha256(head + payload).digest()[:4], "little")
        out += head + crc.to_bytes(4, "little") + bytes([kind]) + payload
    return bytes(out)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        labelled: list[tuple[Path, bool]] = []
        for index in range(3):
            honest = directory / f"honest-{index}.bin"
            honest.write_bytes(journal_bytes(TRUE_DONE))
            labelled.append((honest, True))
            fake = directory / f"fake-{index}.bin"
            fake.write_bytes(journal_bytes(FALSE_DONE))
            labelled.append((fake, False))

        form_ok = 0
        accepted = 0
        caught = 0
        for path, honest in labelled:
            form, _note = false_done.form_verdict(path)
            ok, _rows = accept.check(CRITERIA, accept.parse_journal(path.read_bytes())[0])
            form_ok += 1 if form else 0
            accepted += 1 if ok else 0
            if form and not ok:
                caught += 1
            if honest and not ok:
                print(f"  [!] честный прогон отвергнут: {path.name}")
            if not honest and ok:
                print(f"  [!] ложный прогон принят: {path.name}")

        total = len(labelled)
        print(f"журналов: {total}; форма считает готовыми: {form_ok}; приёмка приняла: {accepted}")
        print(f"ложных «готово» поймано: {caught} из 3")
        ok_case = form_ok == total and accepted == 3 and caught == 3
        print(f"[{'ok' if ok_case else 'FAIL'}] контрольный набор различает ложное и честное готово")
        return 0 if ok_case else 1


if __name__ == "__main__":
    sys.exit(main())
