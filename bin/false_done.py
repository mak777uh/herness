"""false_done — сравнить два вердикта над одним журналом: «по форме» и «по приёмке».

Зачем: пока у приёмки нет числа, она — дисциплина, а не прибор. Вопрос простой: сколько прогонов
выглядят законченными «по форме» (есть run/end, нет ошибок исполнения), но не проходят объявленный
критерий? Каждый такой случай — ложное «готово», которое прибор поймал.

    python bin/false_done.py accept/room-claims-statistics-v3.json runs/accept/*.bin

Форма (то, что видит наивный рантайм): журнал читается, есть run/end, нет step/error с провалом
модели и нет обрыва. Приёмка: `accept.check` по критерию из файла.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import accept  # noqa: E402


def form_verdict(path: Path) -> tuple[bool, str]:
    """Что сказал бы рантайм, который смотрит только на форму журнала."""
    records, tail, problems = accept.parse_journal(path.read_bytes())
    if problems:
        return (False, "; ".join(problems))
    kinds = [kind for kind, _ in accept.events(records)]
    if "run/end" not in kinds:
        return (False, "нет run/end")
    failed = [rest for kind, rest in accept.events(records) if kind == "step/error"]
    hard = [text for text in failed if "бюджет" in text or "не понял" in text]
    if hard:
        return (False, f"ошибки исполнения: {len(hard)}")
    return (True, "run/end без ошибок исполнения")


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if len(argv) < 2:
        print("false_done <критерий.json> <журнал.bin>...", file=sys.stderr)
        return 2
    criteria = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    rows = []
    caught = 0
    for name in argv[1:]:
        path = Path(name)
        if not path.exists():
            continue
        form, form_note = form_verdict(path)
        ok, accept_rows = accept.check(criteria, accept.parse_journal(path.read_bytes())[0])
        caught += 1 if (form and not ok) else 0
        rows.append((path.name, form, ok, form_note,
                     "; ".join(f"{n}: {'ok' if p else 'FAIL'}" for n, p, _ in accept_rows if not p)))
    print(f"{'журнал':32} {'форма':6} {'приёмка':8} причина отказа приёмки")
    for name, form, ok, note, failures in rows:
        print(f"{name:32} {'ok' if form else 'нет':6} {'PASS' if ok else 'FAIL':8} {failures or note}")
    print(f"\nвсего: {len(rows)}; ложных «готово» поймано: {caught}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
