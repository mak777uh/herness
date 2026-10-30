"""Тест-векторы: замораживаем поведение Python как контракт для Rust-ядра."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin.seal import canonical  # noqa: E402

VECTORS = ROOT / "tests" / "vectors"


def canonical_json(payload: dict) -> str:
    """Та же канонизация, что в журнале: сортировка ключей, без пробелов, UTF-8."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def chain(events: list[dict]) -> list[dict]:
    out, prev = [], ""
    for event in events:
        body = canonical_json({**event, "prev": prev})
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        out.append({"event": event, "prev": prev, "hash": digest})
        prev = digest
    return out


def main() -> int:
    VECTORS.mkdir(parents=True, exist_ok=True)

    events = [
        {"seq": 1, "type": "run/start", "payload": {"task": "проверка"}},
        {"seq": 2, "type": "tool/call", "payload": {"name": "read_file", "args": {"path": "a.md"}}},
        {"seq": 3, "type": "run/end", "payload": {"status": "done"}},
    ]
    (VECTORS / "journal.json").write_text(
        json.dumps({"canonical": canonical_json(events[1]), "chain": chain(events)},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    seal_cases = [
        ("простое тело", "тело\n## Seal\nпечать"),
        ("CRLF", "тело\r\n## Seal\r\nпечать"),
        ("хвостовые пробелы", "тело   \n\n## Seal"),
        ("без маркера", "тело без маркера"),
    ]
    (VECTORS / "seal.json").write_text(
        json.dumps([{"name": name, "input": text, "canonical": canonical(text),
                     "sha256": hashlib.sha256(canonical(text).encode("utf-8")).hexdigest()}
                    for name, text in seal_cases], ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("векторы записаны в", VECTORS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
