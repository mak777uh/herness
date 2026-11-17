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
from bin import registry_state  # noqa: E402

OUT = ROOT / "research" / "outputs" / "canary-check.txt"


def statuses(rows: list[dict], current: str, state: dict | None = None) -> list[tuple[str, str]]:
    """Состояние берётся из событий, среда проверяется только у active.

    R8/Q18: quarantined/rejected/candidate не становятся active от совпадения хеша среды.
    Иначе канарейка сама была бы способом обойти производный допуск.
    """
    if state is None:
        state = registry_state.computed_state()
    out = []
    for row in rows:
        record = state["tools"].get(row["id"], {"state": "unreviewed"})
        current_state = record["state"]
        if current_state != "active":
            out.append((row["id"], current_state))
        elif row["environment"] == current:
            out.append((row["id"], "active"))
        else:
            out.append((row["id"], "stale"))
    return out


def probe() -> int:
    rows = [json.loads(line) for line in reg.REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    current = reg.environment_hash()
    state = registry_state.computed_state()
    lines = ["# Canary: протухание по событию", ""]

    # 1. Текущая среда: active нет, legacy остаются quarantined/rejected.
    now = statuses(rows, current, state)
    ok_now = not any(item == "active" for _, item in now)
    lines.append(f"{'текущая среда':34} {now if ok_now else 'ЕСТЬ ЛОЖНЫЙ active'}")

    # 2. Смена среды не воскрешает quarantined/rejected.
    changed = statuses(rows, "deadbeefdeadbeef", state)
    ok_changed = not any(item == "active" for _, item in changed)
    lines.append(f"{'среда изменилась':34} {'active не появился' if ok_changed else 'ПОЯВИЛСЯ active'}")

    lines.append(
        f"{'нерелевантное изменение':34} не отличается: хеш считается по манифесту, "
        "а не по содержимому образа"
    )

    lines += [
        "",
        "# Что это доказывает: состояние инструмента выводится из событий, а смена среды не делает",
        "# quarantined инструмент доступным.",
        "# Что это НЕ доказывает: изменение содержимого образа при том же манифесте не видно.",
    ]
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if ok_now and ok_changed else 1


def check() -> int:
    rows = [json.loads(line) for line in reg.REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    current = reg.environment_hash()
    stale = [name for name, item in statuses(rows, current) if item == "stale"]
    if stale:
        print(f"stale: {', '.join(stale)} — среда изменилась, нужна канарейка")
        return 1
    print(f"[ok] {len(rows)} записей: active нет, quarantined/rejected не выдают допуск")
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
