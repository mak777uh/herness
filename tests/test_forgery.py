"""Подделка с пересчётом CRC: разбор проходит, а сравнение с хостом обязано поймать.

Зачем отдельный тест: подмена байта ловится CRC — это случайная порча. Противник, знающий формат,
пересчитает CRC и seq, и тогда журнал читается как честный. Единственное, что остаётся против
такой подделки, — сверка с тем, что видел хост.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import accept, host_journal  # noqa: E402

ORIGINAL = [
    "run/start task: найти statistics",
    "tool/call search /mnt/CLAIMS.md statistics",
    "tool/result ok найдено 1: C-0021",
    "step 1, потрачено 0.00010000",
    "claim/anchored C-0021",
    "run/end C-0021 — тип statistics",
]

FORGED = [
    "run/start task: найти statistics",
    "tool/call read /mnt/NOT-CLAIMED.md",  # подменённое действие
    "tool/result ok найдено 1: C-0021",
    "step 1, потрачено 0.00010000",
    "claim/anchored C-0021",
    "run/end C-0021 — тип statistics",
]


def journal_bytes(events: list[str]) -> bytes:
    """Собрать журнал с ПРАВИЛЬНЫМИ CRC и seq — как это сделал бы знающий формат."""
    out = bytearray(b"HSJ1" + (1).to_bytes(4, "little"))
    records = [(1, text.encode()) for text in events] + [(2, b"commit")]
    for seq, (kind, payload) in enumerate(records, start=1):
        head = len(payload).to_bytes(4, "little") + seq.to_bytes(8, "little")
        crc = int.from_bytes(hashlib.sha256(head + payload).digest()[:4], "little")
        out += head + crc.to_bytes(4, "little") + bytes([kind]) + payload
    return bytes(out)


def main() -> int:
    criteria = {
        "task": "t",
        "host_run": "forge-run",
        "host_match": True,
        "require_status": "done",
        "anchor_regex": r"C-\d{4}",
    }
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        # хост видел ЧЕСТНЫЕ события: вызов search и «step 1 …» (пачкой, как их шлёт цикл)
        host_journal.append(
            "forge-run",
            "tool/call search /mnt/CLAIMS.md statistics | tool/result ok | step 1, потрачено 0.00010000",
            directory,
        )
        accept.host_journal.DEFAULT_DIR = directory  # приёмка смотрит в этот каталог

        honest = accept.parse_journal(journal_bytes(ORIGINAL))[0]
        ok_honest, _rows = accept.check(criteria, honest)

        forged_records, tail, problems = accept.parse_journal(journal_bytes(FORGED))
        ok_forged, rows_forged = accept.check(criteria, forged_records)
        mismatch = [
            detail for name, passed, detail in rows_forged
            if "совпадает" in name and not passed
        ]

        print(f"честный журнал: {'PASS' if ok_honest else 'FAIL'}")
        print(f"подделка с CRC: разбор чистый (хвост {tail}, проблем {len(problems)}), "
              f"приёмка {'PASS' if ok_forged else 'FAIL'}")
        print(f"поймано сравнением с хостом: {bool(mismatch)}; {mismatch[:1]}")
        good = ok_honest and not ok_forged and bool(mismatch) and tail == 0 and not problems
        print(f"[{'ok' if good else 'FAIL'}] подделка с пересчитанным CRC ловится сверкой с хостом")
        return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
