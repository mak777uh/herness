"""Кросс-сверка HSJ2-кадра: одни и те же замороженные байты — Rust и Python (ADR-0056).

Зачем отдельный тест: CRC записи считается в двух реализациях — Rust-ядро (journal.rs walk)
и Python-приёмка (bin/accept.py parse_journal). Пока кросс-сверки байтов не было, формулы
могли разойтись незаметно (IMPLEMENTATION-STATUS: «кросс-сверка байтов не делалась»).

Вектор tests/vectors/journal_frame.json заморожен: байты и CRC посчитаны эталонной
Python-формулой CRC = sha256(len_le32 ++ seq_le64 ++ kind_u8 ++ payload)[0..4]. Тот же файл
читает Rust-тест hsj2_frame_cross_vector_matches_python (journal.rs, --lib). Здесь проверяем
Python-сторону: разбор принимает байты, CRC-литералы сходятся, переворот kind без пересчёта
CRC отвергается. Расхождение любой из сторон ломает тест — это и есть кросс-сверка.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import accept  # noqa: E402

VECTOR = ROOT / "tests" / "vectors" / "journal_frame.json"


def main() -> int:
    vec = json.loads(VECTOR.read_text(encoding="utf-8"))
    data = bytes.fromhex(vec["hex"])
    records_meta = vec["records"]

    # 1. Производственный разбор принимает эталонные байты без хвоста и проблем.
    records, tail, problems = accept.parse_journal(data)
    want = [(m["kind"], m["payload"]) for m in records_meta]
    clean_ok = records == want and tail == 0 and not problems
    print(f"[{'ok' if clean_ok else 'FAIL'}] разбор кадра: {records} (хвост {tail}, проблем {len(problems)})")

    # 2. CRC каждого кадра, пересчитанный Python sha256, совпадает с замороженным литералом.
    crc_ok = True
    pos = 8
    for m in records_meta:
        length = int.from_bytes(data[pos : pos + 4], "little")
        seq = int.from_bytes(data[pos + 4 : pos + 12], "little")
        kind = data[pos + 16]
        payload = data[pos + 17 : pos + 17 + length]
        head = length.to_bytes(4, "little") + seq.to_bytes(8, "little")
        crc = hashlib.sha256(head + bytes([kind]) + payload).digest()[:4].hex()
        frame_crc = data[pos + 12 : pos + 16].hex()
        match = crc == m["crc"] == frame_crc
        crc_ok = crc_ok and match
        print(f"[{'ok' if match else 'FAIL'}] CRC seq={seq} kind={kind}: пересчёт {crc}, "
              f"кадр {frame_crc}, вектор {m['crc']}")
        pos += 17 + length

    # 3. Замороженный негативный контроль: переворот kind без пересчёта CRC — отказ.
    kf = vec["kind_flip"]
    bad = bytearray(data)
    flip_ok = bad[kf["offset"]] == kf["from"]
    bad[kf["offset"]] = kf["to"]
    rec2, tail2, _ = accept.parse_journal(bytes(bad))
    rejected = len(rec2) == 0 and tail2 > 0
    flip_ok = flip_ok and rejected
    print(f"[{'ok' if flip_ok else 'FAIL'}] переворот kind: записей {len(rec2)}, хвост {tail2} "
          f"({'отвергнут' if rejected else 'ПРОШЁЛ — дефект'})")

    good = clean_ok and crc_ok and flip_ok
    print(f"[{'ok' if good else 'FAIL'}] кросс-вектор HSJ2-кадра: Python-сторона сходится")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())