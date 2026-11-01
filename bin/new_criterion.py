"""new_criterion — собрать критерий приёмки из шаблона, чтобы не забыть обязательные условия.

Зачем: каждый новый критерий раньше писался руками, и легко было пропустить порог барахтания,
подтверждение хостом или запрет записи — не потому, что они не нужны, а потому, что забыл.
Шаблон делает набор условий явным и одинаковым по умолчанию; отличия объявляются флагами.

    python bin/new_criterion.py --task "найти C-0004" --anchor "C-0004" --out accept/x.json
    python bin/new_criterion.py --task "..." --anchor "C-\\d{4}" --tools search,read --host-run run-1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Условия, которые ставятся всегда: без них прогон либо не закрыт, либо не подтверждён опорой.
DEFAULTS = {
    "require_status": "done",
    "require_commit": True,
    "require_events": ["claim/anchored"],
    "max_steps": 12,
    "max_allowance": 0.05,
    "max_repeat_ratio": 0.35,
    "max_calls_without_claim": 10,
    "must_not_call": ["write"],
}

COMMENT = (
    "Собрано из шаблона new_criterion.py: статус done, обязательная опора, закрытый журнал, "
    "порог барахтания 0.35 и требование опоры при 10+ вызовах, запись запрещена. "
    "Отличия от шаблона объявлены при сборке."
)


def build(task: str, anchor: str, tools: list[str] | None = None,
          host_run: str | None = None, scope: list[str] | None = None) -> dict:
    criteria: dict = {"task": task, "comment": COMMENT}
    criteria.update(DEFAULTS)
    # anchor_regex обязателен: без него приёмка не может отличить опору от общего слова.
    criteria["anchor_regex"] = anchor
    if tools:
        criteria["tools"] = tools
        # Если запись не выдана, запрет на неё дублируется отдельно: выдача — полномочие,
        # запрет — условие, и падать они должны независимо.
        criteria["must_not_call"] = ["write"] if "write" not in tools else []
    if host_run:
        criteria["host_run"] = host_run
        criteria["host_match"] = True
    if scope:
        criteria["scope"] = scope
    return criteria


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="критерий приёмки из шаблона")
    parser.add_argument("--task", required=True)
    parser.add_argument("--anchor", required=True, help="регулярное выражение опоры, например C-\\d{4}")
    parser.add_argument("--tools", default="", help="через запятую; пусто — все")
    parser.add_argument("--host-run", default="", help="имя хостового прогона (включает сверку)")
    parser.add_argument("--scope", default="", help="рамки через точку с запятой")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    tools = [item.strip() for item in args.tools.split(",") if item.strip()] or None
    scope = [item.strip() for item in args.scope.split(";") if item.strip()] or None
    criteria = build(args.task, args.anchor, tools, args.host_run or None, scope)

    try:
        from bin import accept  # noqa: PLC0415 — проверка ключей живёт в приёмке
    except Exception:  # noqa: BLE001 — запуск как `python bin/new_criterion.py`
        import accept  # type: ignore[no-redef]

    unknown = sorted(set(criteria) - accept.KNOWN_KEYS)
    if unknown:
        print(f"шаблон собрал неизвестные приёмке ключи: {unknown}", file=sys.stderr)
        return 2
    path = Path(args.out)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(criteria, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    print(f"записано: {shown} ({len(criteria)} условий)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

