"""canary — протухание по событию, а не по календарю (эксперимент E3 плана P33).

Правило: инструмент объявлен проверенным против конкретного хеша среды. Хеш изменился —
инструмент `stale` до прохождения канарейки. Канарейка — короткая детерминированная проверка
поведения, а не полный прогон.

    python bin/canary.py --check     # статусы против текущей среды
    python bin/canary.py --probe     # отрицательный контроль: смена среды и нерелевантное изменение
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import build_registry as reg  # noqa: E402

OUT = ROOT / "research" / "outputs" / "canary-check.txt"


def statuses(rows: list[dict], current: str) -> list[tuple[str, str]]:
    return [(row["id"], "active" if row["environment"] == current else "stale") for row in rows]


def probe() -> int:
    rows = [json.loads(line) for line in reg.REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    current = reg.environment_hash()
    lines = ["# Canary: протухание по событию", ""]

    # 1. Текущая среда: всё активно.
    now = statuses(rows, current)
    ok_now = all(state == "active" for _, state in now)
    lines.append(f"{'текущая среда':34} {'active у всех' if ok_now else 'ЕСТЬ stale'}")

    # 2. Среда изменилась (другой хеш): все становятся stale.
    changed = statuses(rows, "deadbeefdeadbeef")
    ok_changed = all(state == "stale" for _, state in changed)
    lines.append(f"{'среда изменилась':34} {'все stale' if ok_changed else 'НЕ ВСЕ stale'}")

    # 3. Нерелевантное изменение: манифест тот же, добавили неиспользуемый файл в комнату.
    #    Хеш среды считается по манифесту, а не по содержимому образа, поэтому статус не меняется —
    #    и это надо назвать честно: такой канарейкой нерелевантное изменение не отличить.
    lines.append(
        f"{'нерелевантное изменение':34} не отличается: хеш считается по манифесту, "
        "а не по содержимому образа"
    )

    lines += [
        "",
        "# Что это доказывает: смена манифеста комнаты переводит все инструменты в stale.",
        "# Что это НЕ доказывает: изменение содержимого образа при том же манифесте не видно.",
        "# Для второго нужен хеш содержимого (build_room --check уже сверяет число файлов).",
    ]
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if ok_now and ok_changed else 1


def check() -> int:
    rows = [json.loads(line) for line in reg.REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    current = reg.environment_hash()
    stale = [name for name, state in statuses(rows, current) if state == "stale"]
    if stale:
        print(f"stale: {', '.join(stale)} — среда изменилась, нужна канарейка")
        return 1
    print(f"[ok] все {len(rows)} инструментов проверены против среды {current}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="канарейка инструментов")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.probe:
        return probe()
    return check()


if __name__ == "__main__":
    sys.exit(main())
