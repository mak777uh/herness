"""registry_state — состояние инструментов, выведенное из append-only событий.

Почему так: `registry.jsonl` — замороженный genesis-снимок контрактов, а не таблица
полномочий. Полномочие (`active`) нельзя хранить рядом с описанием: иначе JSON-правка
«status: active» становится допуском. Допуск — это событие в цепочке, и он же вычисляется
заново при каждом чтении.

    python bin/registry_state.py --check      # цепочка, снимок и state.json согласованы
    python bin/registry_state.py --write      # пересобрать производный state.json
    python bin/registry_state.py --show       # состояние
    python bin/registry_state.py --authorize search   # S13_TOOL_INACTIVE, если не active

Границы v0:
- `active` требует события `admitted` с owner-подписью, admission- и evidence-digest;
  поля проверяются, но сама подпись здесь не верифицируется — это делает promoter;
- настоящий owner-ключ не создаётся, ни один legacy-инструмент не делается active;
- `net` — отдельный bridge path вне реестра: у него своя политика, не событие реестра.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "lab" / "tools" / "registry.jsonl"
EVENTS = ROOT / "lab" / "tools" / "registry.events.jsonl"
STATE = ROOT / "lab" / "tools" / "registry.state.json"
POLICY = ROOT / "lab" / "tools" / "policy.json"

STATE_SCHEMA = "herness-registry-state-v1"
EVENT_SCHEMA = "herness-registry-event-v1"
EVENT_TYPES = (
    "genesis",
    "quarantined",
    "rejected",
    "candidate",
    "admitted",
    "revoked",
    "expired",
)
LEGACY = ("search", "list", "read", "write", "seal", "netprobe")
DIGEST_RE = __import__("re").compile(r"^sha256:[0-9a-f]{64}$")


class RegistryError(Exception):
    pass


def refuse(reason: str) -> RegistryError:
    return RegistryError(f"S13_TOOL_INACTIVE: {reason}")


def _reject_float(_text: str) -> Any:
    raise RegistryError("float в каноническом JSON запрещён")


def _check_subset(value: Any) -> None:
    if isinstance(value, float):
        raise RegistryError("float в каноническом JSON запрещён")
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, list):
        for item in value:
            _check_subset(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise RegistryError("ключ канонического JSON должен быть ASCII-строкой")
            _check_subset(item)
        return
    raise RegistryError(f"тип {type(value).__name__} не входит в JCS-подмножество")


def canonical(value: Any) -> bytes:
    """JCS-подмножество v0: без float, ключи отсортированы, UTF-8."""
    _check_subset(value)
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    try:
        return digest_bytes(path.read_bytes())
    except OSError as exc:
        raise RegistryError(f"нет файла {path}: {exc}") from exc


def genesis_prev() -> str:
    return digest_bytes(b"herness-registry-genesis-v1")


def line_hash(line: bytes) -> str:
    return digest_bytes(line)


def read_lines(path: Path) -> list[bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RegistryError(f"нет файла {path}: {exc}") from exc
    return [line for line in raw.splitlines() if line.strip()]


def read_snapshot(path: Path = SNAPSHOT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(read_lines(path), 1):
        try:
            row = json.loads(line.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RegistryError(f"registry.jsonl:{index}: не JSON: {exc}") from exc
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise RegistryError(f"registry.jsonl:{index}: нет строкового id")
        row["_line"] = index
        rows.append(row)
    return rows


def read_events(path: Path = EVENTS) -> list[tuple[bytes, dict[str, Any]]]:
    events: list[tuple[bytes, dict[str, Any]]] = []
    for index, line in enumerate(read_lines(path), 1):
        try:
            event = json.loads(line.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RegistryError(f"registry.events.jsonl:{index}: не JSON: {exc}") from exc
        if not isinstance(event, dict):
            raise RegistryError(f"registry.events.jsonl:{index}: событие не объект")
        if line != canonical(event):
            raise RegistryError(f"registry.events.jsonl:{index}: строка не JCS")
        if event.get("schema") != EVENT_SCHEMA:
            raise RegistryError(f"registry.events.jsonl:{index}: чужая схема")
        events.append((line, event))
    return events


def validate_events(
    events: list[tuple[bytes, dict[str, Any]]],
    snapshot_digest: str,
    policy_digest: str,
) -> list[str]:
    problems: list[str] = []
    if not events:
        return ["нет событий: пустой реестр не даёт полномочий"]
    previous = genesis_prev()
    for index, (line, event) in enumerate(events):
        seq = event.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int) or seq != index:
            problems.append(f"событие {index}: seq {seq!r}, ждали {index}")
        if event.get("prev") != previous:
            problems.append(f"событие {index}: prev не совпадает с хешем предыдущей строки")
        if event.get("type") not in EVENT_TYPES:
            problems.append(f"событие {index}: неизвестный тип {event.get('type')!r}")
        at = event.get("at")
        if not isinstance(at, str) or not at.endswith("Z"):
            problems.append(f"событие {index}: at не UTC")
        body = event.get("body")
        if not isinstance(body, dict):
            problems.append(f"событие {index}: body не объект")
        if index == 0:
            if event.get("type") != "genesis":
                problems.append("первое событие не genesis")
            if event.get("prev") != genesis_prev():
                problems.append("genesis: неверный prev")
            if event.get("tool_id") is not None:
                problems.append("genesis: tool_id должен быть null")
            if isinstance(body, dict):
                if body.get("snapshot_digest") != snapshot_digest:
                    problems.append("genesis: snapshot_digest не совпадает с registry.jsonl")
                if body.get("policy_digest") != policy_digest:
                    problems.append("genesis: policy_digest не совпадает с policy.json")
        else:
            if event.get("type") == "genesis":
                problems.append(f"событие {index}: genesis не может быть не первым")
            tool_id = event.get("tool_id")
            if not isinstance(tool_id, str) or not tool_id:
                problems.append(f"событие {index}: нет tool_id")
        previous = line_hash(line)
    return problems


def _activation_problem(event: dict[str, Any]) -> str | None:
    """Допуск без доказательств — только `admitted_inactive`, не `active`."""
    body = event.get("body") or {}
    if body.get("owner_signed") is not True:
        return "admitted без owner-подписи"
    for field in ("admission_digest", "evidence_digest"):
        value = body.get(field)
        if not isinstance(value, str) or not DIGEST_RE.match(value):
            return f"admitted без корректного {field}"
    return None


def derive(
    snapshot_rows: list[dict[str, Any]],
    events: list[tuple[bytes, dict[str, Any]]],
    snapshot_digest: str,
    policy_digest: str,
) -> dict[str, Any]:
    problems = validate_events(events, snapshot_digest, policy_digest)
    if problems:
        raise RegistryError("; ".join(problems))

    tools: dict[str, dict[str, Any]] = {}
    for row in snapshot_rows:
        tools[row["id"]] = {
            "state": "unreviewed",
            "seq": 0,
            "reason": "нет события после genesis",
            "history": ["unreviewed"],
        }

    for index, (_, event) in enumerate(events):
        if index == 0:
            continue
        tool_id = event["tool_id"]
        kind = event["type"]
        if kind == "quarantined":
            state = "quarantined"
        elif kind == "rejected":
            state = "rejected"
        elif kind == "candidate":
            state = "candidate"
        elif kind == "admitted":
            state = "active" if _activation_problem(event) is None else "admitted_inactive"
        elif kind == "revoked":
            state = "revoked"
        elif kind == "expired":
            state = "expired"
        else:  # validate_events уже отверг неизвестный тип
            state = "unreviewed"
        record = tools.setdefault(
            tool_id,
            {"state": "unreviewed", "seq": 0, "reason": "нет события после genesis", "history": ["unreviewed"]},
        )
        record["state"] = state
        record["seq"] = index
        record["reason"] = str((event.get("body") or {}).get("reason") or "")
        record["history"] = list(record.get("history") or []) + [state]
        if kind == "candidate":
            record["card"] = (event.get("body") or {}).get("card")
        if kind == "admitted":
            record["admission_digest"] = (event.get("body") or {}).get("admission_digest")
            record["evidence_digest"] = (event.get("body") or {}).get("evidence_digest")

    active = sorted(tool_id for tool_id, record in tools.items() if record["state"] == "active")
    return {
        "schema": STATE_SCHEMA,
        "snapshot_digest": snapshot_digest,
        "events_digest": line_hash(events[-1][0]) if events else digest_bytes(b""),
        "head_seq": len(events) - 1,
        "epoch": int(((events[0][1].get("body") or {}) if events else {}).get("epoch", 0)),
        "tools": {key: tools[key] for key in sorted(tools)},
        "active": active,
    }


def computed_state(
    snapshot: Path = SNAPSHOT, events: Path = EVENTS, policy: Path = POLICY
) -> dict[str, Any]:
    rows = read_snapshot(snapshot)
    parsed = read_events(events)
    return derive(rows, parsed, digest_file(snapshot), digest_file(policy))


def state_bytes(state: dict[str, Any]) -> bytes:
    # state.json — производный артефакт; он не является входом полномочия.
    return (json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")


def write_state(path: Path = STATE) -> int:
    data = state_bytes(computed_state())
    path.write_bytes(data)
    print(f"записано: {path.relative_to(ROOT)}; active: {computed_state()['active'] or 'нет'}")
    return 0


def check_files() -> list[str]:
    problems: list[str] = []
    try:
        rows = read_snapshot()
        events = read_events()
        snapshot_digest = digest_file(SNAPSHOT)
        policy_digest = digest_file(POLICY)
        state = derive(rows, events, snapshot_digest, policy_digest)
    except RegistryError as exc:
        return [str(exc)]
    for row in rows:
        if "status" in row:
            problems.append(
                f"registry.jsonl: у {row.get('id')} хранится status={row.get('status')!r}: "
                "полномочие должно быть производным"
            )
    for tool in LEGACY:
        record = state["tools"].get(tool)
        if record is None:
            problems.append(f"{tool}: нет состояния в производном реестре")
        elif record["state"] not in ("quarantined", "rejected"):
            problems.append(f"{tool}: {record['state']}, ждали quarantined/rejected")
    head = state["tools"].get("head")
    if head is not None and head["state"] == "active":
        problems.append("head: active без owner-подписи")
    if state["active"]:
        problems.append(f"active не пуст: {state['active']} — нужен owner admission")
    try:
        actual = STATE.read_bytes()
    except OSError:
        problems.append("нет registry.state.json: запустить --write")
    else:
        if actual != state_bytes(state):
            problems.append("registry.state.json устарел: запустить --write")
    source = (ROOT / "core-rs" / "src" / "loopmod.rs").read_text(encoding="utf-8")
    if 'include_str!("../../lab/tools/registry.state.json")' not in source:
        problems.append("loopmod.rs не встраивает registry.state.json")
    if "S13_TOOL_INACTIVE" not in source:
        problems.append("в loopmod.rs нет отказа S13_TOOL_INACTIVE")
    return problems


def authorize(tool: str) -> tuple[bool, str]:
    if tool == "net":
        return True, "net: отдельный bridge path вне реестра"
    state = computed_state()
    record = state["tools"].get(tool)
    if record is None:
        return False, f"S13_TOOL_INACTIVE: {tool} отсутствует в реестре"
    if record["state"] != "active":
        return False, f"S13_TOOL_INACTIVE: {tool} в состоянии {record['state']}"
    return True, tool


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="производное состояние реестра инструментов")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--authorize", metavar="TOOL")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.write:
        return write_state()
    if args.authorize:
        ok, message = authorize(args.authorize)
        print(message)
        return 0 if ok else 1
    if args.show:
        print(state_bytes(computed_state()).decode("utf-8"), end="")
        return 0
    if args.check:
        problems = check_files()
        for problem in problems:
            print(f"[FAIL] {problem}")
        if problems:
            return 1
        print("[ok] реестр: снимок заморожен, цепочка событий цела, active производный и пуст")
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
