"""journal_dump — журналы в текст, чтобы их читал агент в комнате.

Журнал — двоичный (HSJ1). В комнате нет ни hexdump, ни coreutils, поэтому прогоны для задач
выкладываются текстом: одна строка — одно событие. Полезная нагрузка обрезается: для ответа
«чем закончился прогон» хватает вида события.

    python bin/journal_dump.py            # runs/dump/*.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, ".")
from bin import accept  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 300


def main() -> int:
    source = ROOT / "runs" / "accept"
    target = ROOT / "runs" / "dump"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(source.glob("*.bin")):
        try:
            records, _tail, _problems = accept.parse_journal(path.read_bytes())
        except Exception:  # noqa: BLE001
            continue
        lines = []
        for kind, payload in accept.events(records):
            text = payload.replace("\n", " ")
            if len(text) > LIMIT:
                text = text[:LIMIT] + "…"
            lines.append(f"{kind}: {text}")
        (target / f"{path.stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        count += 1
    print(f"выгружено журналов: {count} → runs/dump")
    return 0


if __name__ == "__main__":
    sys.exit(main())
