"""plan_check — приёмка режима «план»: план без правок.

Режим «план» (docs/MODE-SPEC.md): агент изучает задачу и предлагает план, ничего не меняя.
Проверяется по журналу, без доверия к тексту:
  1) ни одного вызова write;
  2) в ответе есть не меньше трёх шагов (строки, начинающиеся с цифры или «-»);
  3) есть раздел «неизвестно» — пустой допустим, но раздел обязателен.

    python bin/plan_check.py <журнал.bin>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bin import accept  # noqa: E402

MIN_STEPS = 3


def check(journal: Path) -> tuple[bool, list[tuple[str, bool, str]]]:
    records, _tail, _problems = accept.parse_journal(journal.read_bytes())
    events = list(accept.events(records))
    calls = [rest for kind, rest in events if kind == "tool/call"]
    writes = [call for call in calls if call.split()[:1] == ["write"]]
    answers = [rest for kind, rest in events if kind == "run/end"]
    text = answers[-1] if answers else ""

    by_line = re.findall(r"(?m)^\s*(?:\d+[.)]|[-*])\s+\S", text)
    inline = re.findall(r"(?:^|[\s;])(\d+[.)])\s+\S", text)
    steps = by_line or inline
    has_unknown = bool(re.search(r"(?i)неизвестн", text))

    rows = [
        ("ни одного write", not writes, f"вызовов write: {len(writes)}"),
        (f"шагов в плане ≥ {MIN_STEPS}", len(steps) >= MIN_STEPS, f"шагов: {len(steps)}"),
        # Раздел «неизвестно» обязателен по спецификации режима (docs/MODE-SPEC.md §1).
        ("есть раздел «неизвестно»", has_unknown, "найден" if has_unknown else "нет"),
    ]
    return all(ok for _, ok, _ in rows), rows


def main(argv: list[str]) -> int:
    if not argv:
        print("нужно: python bin/plan_check.py <журнал.bin>", file=sys.stderr)
        return 2
    ok, rows = check(Path(argv[0]))
    for name, passed, detail in rows:
        print(f"[{'ok' if passed else 'FAIL'}] {name} — {detail}")
    print("итог:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
