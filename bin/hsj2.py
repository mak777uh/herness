"""hsj2 — сборка кадров журнала для проверок (зеркало `core-rs/src/journal.rs`).

Зачем: проверки плагина и хоста должны строить журнал **тем же** форматом, что пишет комната.
Иначе получается старая болезнь: прибор проверяет формат, которого уже нет (F-0087).

    файл:  "HSJ2" + version u32 LE
    кадр:  len u32 | seq u64 | crc u32 | kind u8 | payload[len]
    crc = первые 4 байта SHA-256 от len || seq || kind || payload
"""

from __future__ import annotations

import hashlib
import struct

MAGIC = b"HSJ2"
VERSION = 2
DATA = 1
COMMIT = 2


def frame(seq: int, kind: int, payload: bytes) -> bytes:
    if kind not in (DATA, COMMIT):
        raise ValueError(f"kind {kind}: ожидался 1 (Data) или 2 (Commit)")
    head = struct.pack("<I", len(payload)) + struct.pack("<Q", seq)
    digest = hashlib.sha256(head + bytes([kind]) + payload).digest()
    crc = struct.unpack("<I", digest[:4])[0]
    return head + struct.pack("<I", crc) + bytes([kind]) + payload


def journal(events: list[tuple[int, str | bytes]]) -> bytes:
    out = MAGIC + struct.pack("<I", VERSION)
    for index, (kind, payload) in enumerate(events, start=1):
        raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        out += frame(index, kind, raw)
    return out


def run_start(task: str) -> tuple[int, str]:
    return DATA, f"run/start task: {task}"


def run_end(answer: str) -> tuple[int, str]:
    return COMMIT, f"run/end {answer}"
