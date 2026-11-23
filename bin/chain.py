"""chain - проверка K9: композиция шагов и цепочка мостов.

Модель декларативная: checker читает объявленные замыкания шагов и разрешённые
адреса мостов, а не код downstream. Это policy-only проверка; она не доказывает
безопасность и не выдаёт `K9_proven`.

    python bin/chain.py check <chain.json>

Коды отказа (K5, явные):
  K9_ADJACENT_REQUIRED          — в цепочке нет adjacent-моста
  K9_CHAIN_UNPROVEN             — downstream-мост без доказательства композиции
  K9_DOWNSTREAM_MISSING_DEST    — adjacent форвардит адрес, downstream его не пропускает
  K9_DOWNSTREAM_MISSING_METHOD  — adjacent разрешает метод, downstream его не покрывает
                                  (coverage: [] = deny-all на своей стороне,
                                   отсутствие поля — K9_SCHEMA)
  K9_TAINT_ESCAPE               — в композиции есть и секрет, и сеть
  K9_SCHEMA                     — декларация не того типа

Выход: 0 — цепочка допустима, 3 — отказ, 2 — ошибка разбора.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAVEAT = "policy-only check; it does not inspect downstream code or its own egress"
SECRET_PREFIX = "secret:"


def _destinations(bridge: dict) -> list[str]:
    return [str(item) for item in (bridge or {}).get("allowed_destinations", [])]


def _methods(bridge: dict) -> list[str]:
    return [str(item) for item in (bridge or {}).get("allowed_methods", [])]


def _problem(code: str, message: str, **extra: object) -> dict:
    return {"code": code, "message": message, **extra}


def reads_secret(step: dict) -> bool:
    """Шаг читает секрет: источник начинается с `secret:`."""
    return any(str(source).startswith(SECRET_PREFIX) for source in step.get("reads", []))


def sends_external(step: dict) -> bool:
    """Шаг отправляет наружу: у него есть хотя бы один адрес в `sends`."""
    return bool(step.get("sends", []))


def step_leaks(step: dict) -> bool:
    """Утечка одного шага: он и читает секрет, и отправляет наружу."""
    return reads_secret(step) and sends_external(step)


def check_chain(decl: dict) -> dict:
    """Проверить одну декларацию цепочки. Возвращает отчёт, не бросает."""
    problems: list[dict] = []
    adjacent = decl.get("adjacent")
    downstream = decl.get("downstream", [])
    steps = decl.get("steps", [])

    if not isinstance(adjacent, dict) or not adjacent:
        problems.append(_problem("K9_ADJACENT_REQUIRED", "chain has no adjacent bridge"))
        adjacent = None
    if not isinstance(downstream, list):
        problems.append(_problem("K9_SCHEMA", "downstream must be a list"))
        downstream = []
    if not isinstance(steps, list):
        problems.append(_problem("K9_SCHEMA", "steps must be a list"))
        steps = []

    for index, bridge in enumerate(downstream):
        if not isinstance(bridge, dict):
            problems.append(_problem("K9_SCHEMA", "downstream entry must be an object", index=index))
            continue
        if bridge.get("proven") is not True:
            problems.append(_problem(
                "K9_CHAIN_UNPROVEN",
                f"downstream bridge {bridge.get('id', index)!r} has no composition proof",
                bridge=bridge.get("id", index),
            ))

    adjacent_destinations = _destinations(adjacent) if adjacent else []
    adjacent_methods = _methods(adjacent) if adjacent else []
    if adjacent and "allowed_methods" not in adjacent:
        problems.append(_problem(
            "K9_SCHEMA",
            f"adjacent bridge {adjacent.get('id', '?')!r} has no allowed_methods",
            bridge=adjacent.get("id", "?"),
        ))
    for bridge in downstream:
        if not isinstance(bridge, dict):
            continue
        destinations = _destinations(bridge)
        for destination in adjacent_destinations:
            if destination not in destinations:
                problems.append(_problem(
                    "K9_DOWNSTREAM_MISSING_DEST",
                    f"adjacent forwards {destination!r} but downstream "
                    f"{bridge.get('id', '?')!r} does not",
                    dest=destination,
                    bridge=bridge.get("id", "?"),
                ))
        methods = _methods(bridge)
        if "allowed_methods" not in bridge:
            problems.append(_problem(
                "K9_SCHEMA",
                f"downstream bridge {bridge.get('id', '?')!r} has no allowed_methods",
                bridge=bridge.get("id", "?"),
            ))
            continue
        if adjacent_methods:
            for method in adjacent_methods:
                if method not in methods:
                    problems.append(_problem(
                        "K9_DOWNSTREAM_MISSING_METHOD",
                        f"adjacent allows {method!r} but downstream "
                        f"{bridge.get('id', '?')!r} does not",
                        method=method,
                        bridge=bridge.get("id", "?"),
                    ))

    readers = [str(step.get("id", index)) for index, step in enumerate(steps)
               if isinstance(step, dict) and reads_secret(step)]
    senders = [str(step.get("id", index)) for index, step in enumerate(steps)
               if isinstance(step, dict) and sends_external(step)]
    if readers and senders:
        problems.append(_problem(
            "K9_TAINT_ESCAPE",
            "composition reads a secret and sends external; refused",
            readers=readers,
            senders=senders,
        ))

    if not adjacent:
        reachable: list[str] = []
    elif not downstream:
        reachable = sorted(set(adjacent_destinations))
    else:
        common = set(adjacent_destinations)
        for bridge in downstream:
            if isinstance(bridge, dict):
                common &= set(_destinations(bridge))
        reachable = sorted(common)

    broader = sorted({dest for bridge in downstream if isinstance(bridge, dict)
                      for dest in _destinations(bridge)} - set(adjacent_destinations))

    return {
        "law": "K9",
        "ok": not problems,
        "problems": problems,
        "caveat": CAVEAT,
        "reachable_through_chain": reachable,
        "downstream_broader_unreachable": broader,
        "reads_secret": readers,
        "sends_external": senders,
        "steps": len(steps),
        "per_step_leaks": [str(step.get("id", index)) for index, step in enumerate(steps)
                           if isinstance(step, dict) and step_leaks(step)],
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] != "check":
        print("usage: python bin/chain.py check <chain.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        decl = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"chain: {exc}", file=sys.stderr)
        return 2
    if not isinstance(decl, dict):
        print("chain: declaration must be a JSON object", file=sys.stderr)
        return 2
    result = check_chain(decl)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
