"""W07B: каноническая refs-only проекция локальных событий.

Сырой detail остаётся в локальном журнале комнаты. Хост получает только тип, статус, безопасные
идентификаторы и SHA-256 полной локальной строки. ACK хоста не превращается в acceptance.
"""

from __future__ import annotations

import hashlib
import json
import re

SCHEMA = "host-journal-event-v1"
EVENT_DOMAIN = b"HOST-JOURNAL-EVENT-V1\0"
MAX_BODY_BYTES = 16384
RUN_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?\Z")
SESSION_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z"
)
CALL_RE = re.compile(r"call-[0-9]{6,}\Z")
TOOL_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
CLAIM_RE = re.compile(r"c-[0-9]{4}\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
ZERO_DIGEST = "0" * 64
FIELDS = frozenset({"schema", "session", "type", "call_id", "status", "refs", "digests"})
TYPES = frozenset({
    "run/start", "run/end", "run/blocked", "run/no-work", "step/error",
    "model/reply", "tool/call", "tool/result", "claim/anchored", "claim/unverified", "step",
})
STATUSES = frozenset({"started", "ended", "blocked", "no-work", "error", "replied", "recorded", "ok", "denied"})
REF_KINDS = frozenset({"tool", "call", "claim"})


class EventError(ValueError):
    """Отказ typed boundary; сырые данные в сообщение не попадают."""


def exact_grant_refusal(detail: str, tool: str) -> bool:
    """Только точный per-run grant refusal; другие closure breaches не являются denied."""
    return detail == f"err S6_CLOSURE_BREACH: инструмент {tool} не выдан в этом прогоне"


def canonical(value: dict) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def valid_run(run: object) -> bool:
    return isinstance(run, str) and RUN_RE.fullmatch(run) is not None


def valid_session(session: object) -> bool:
    return isinstance(session, str) and SESSION_RE.fullmatch(session) is not None


def event_digest(line: str) -> str:
    return hashlib.sha256(EVENT_DOMAIN + line.encode("utf-8")).hexdigest()


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise EventError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_text: str):
    raise EventError("non-finite JSON number")


def decode(body: bytes, expected_session: str) -> dict:
    """Строгий JSON → проверенная typed schema. Никаких run/raw/extra полей."""
    if len(body) > MAX_BODY_BYTES:
        raise EventError("journal body too large")
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except EventError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise EventError("invalid JSON") from exc
    validate(value, expected_session)
    return value


def _valid_ref(ref: object) -> bool:
    if not isinstance(ref, dict) or set(ref) != {"id", "kind"}:
        return False
    kind, identifier = ref.get("kind"), ref.get("id")
    if not isinstance(kind, str) or not isinstance(identifier, str):
        return False
    if kind == "tool":
        return TOOL_RE.fullmatch(identifier) is not None
    if kind == "call":
        return CALL_RE.fullmatch(identifier) is not None
    if kind == "claim":
        return CLAIM_RE.fullmatch(identifier) is not None
    return False


def validate(value: object, expected_session: str) -> None:
    if not valid_session(expected_session):
        raise EventError("invalid expected session")
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise EventError("event fields are not exact")
    if value.get("schema") != SCHEMA or value.get("session") != expected_session:
        raise EventError("schema/session mismatch")
    kind = value.get("type")
    status = value.get("status")
    if not isinstance(kind, str) or kind not in TYPES:
        raise EventError("unknown event type")
    if not isinstance(status, str) or status not in STATUSES:
        raise EventError("unknown event status")
    call_id = value.get("call_id")
    if call_id is not None and (not isinstance(call_id, str) or CALL_RE.fullmatch(call_id) is None):
        raise EventError("invalid call id")
    refs = value.get("refs")
    if not isinstance(refs, list) or len(refs) > 2 or not all(_valid_ref(ref) for ref in refs):
        raise EventError("invalid refs")
    identities = [(ref["kind"], ref["id"]) for ref in refs]
    if len(set(identities)) != len(identities):
        raise EventError("duplicate ref")
    digests = value.get("digests")
    if not isinstance(digests, dict) or set(digests) != {"event"}:
        raise EventError("invalid digests")
    digest = digests.get("event")
    if (
        not isinstance(digest, str)
        or DIGEST_RE.fullmatch(digest) is None
        or digest == ZERO_DIGEST
    ):
        raise EventError("invalid event digest")

    if kind == "tool/call":
        if call_id is None or len(refs) != 1 or refs[0]["kind"] != "tool":
            raise EventError("tool/call needs call id and exactly one tool ref")
    elif kind == "tool/result":
        if call_id is None or refs != [{"id": call_id, "kind": "call"}]:
            raise EventError("tool/result needs matching call ref")
    else:
        if call_id is not None:
            raise EventError("call id is not allowed for this event")
        if kind != "claim/anchored" and refs:
            raise EventError("refs are not allowed for this event")
        if kind == "claim/anchored" and (len(refs) > 1 or any(ref["kind"] != "claim" for ref in refs)):
            raise EventError("claim/anchored accepts only one claim ref")

    expected_status = {
        "run/start": "started", "run/end": "ended", "run/blocked": "blocked",
        "run/no-work": "no-work", "step/error": "error", "model/reply": "replied",
        "tool/call": "recorded", "step": "recorded", "claim/anchored": "recorded",
        "claim/unverified": "recorded",
    }.get(kind)
    if expected_status is not None and status != expected_status:
        raise EventError("status does not match event type")
    if kind == "tool/result" and status not in {"ok", "error", "denied", "recorded"}:
        raise EventError("invalid tool/result status")


def _project(
    kind: str, detail: str, line: str, session: str,
    state: dict[str, int | str | None],
) -> dict:
    call_id = None
    refs: list[dict[str, str]] = []
    if kind == "tool/call":
        if state["pending"] is not None:
            raise EventError("nested tool/call without result")
        call_seq = int(state["call_seq"]) + 1
        state["call_seq"] = call_seq
        call_id = f"call-{call_seq:06d}"
        state["pending"] = call_id
        tool = detail.split(" ", 1)[0]
        state["pending_tool"] = tool
        if TOOL_RE.fullmatch(tool):
            refs.append({"id": tool, "kind": "tool"})
    elif kind == "tool/result":
        call_id = state["pending"]
        if call_id is None:
            raise EventError("tool/result without preceding tool/call")
        pending_tool = state["pending_tool"]
        refs.append({"id": call_id, "kind": "call"})
        state["pending"] = None
        state["pending_tool"] = None
    elif kind == "claim/anchored":
        match = re.search(r"(?<![A-Za-z0-9_])C-[0-9]{4}(?![A-Za-z0-9_])", detail)
        if match:
            refs.append({"id": match.group(0).lower(), "kind": "claim"})
    if kind == "run/start":
        status = "started"
    elif kind == "run/end":
        status = "ended"
    elif kind == "run/blocked":
        status = "blocked"
    elif kind == "run/no-work":
        status = "no-work"
    elif kind == "step/error":
        status = "error"
    elif kind == "model/reply":
        status = "replied"
    elif kind == "tool/result":
        head = detail.split(" ", 1)[0].lower()
        if head == "ok":
            status = "ok"
        elif exact_grant_refusal(detail, str(pending_tool)):
            status = "denied"
        elif head in {"err", "error", "ошибка", "failed"}:
            status = "error"
        else:
            status = "recorded"
    else:
        status = "recorded"
    payload = {
        "schema": SCHEMA, "session": session, "type": kind, "call_id": call_id,
        "status": status, "refs": refs, "digests": {"event": event_digest(line)},
    }
    validate(payload, session)
    return payload


def project(events: list[tuple[str, str]], session: str) -> list[dict]:
    """Проекция того же вида, что и Rust host_event; состояние вызовов идёт по всему потоку."""
    if not valid_session(session):
        raise EventError("invalid session")
    state: dict[str, int | str | None] = {"call_seq": 0, "pending": None, "pending_tool": None}
    projected = [
        _project(kind, detail, f"{kind} {detail}", session, state)
        for kind, detail in events
    ]
    if state["pending"] is not None:
        raise EventError("tool/call without tool/result at projection end")
    return projected


def project_payloads(payloads: list[str], session: str) -> list[dict]:
    """Проекция точных local payload: digest покрывает исходную строку без strip/reconstruction."""
    if not valid_session(session):
        raise EventError("invalid session")
    state: dict[str, int | str | None] = {"call_seq": 0, "pending": None, "pending_tool": None}
    out: list[dict] = []
    for line in payloads:
        kind, _, detail = line.partition(" ")
        out.append(_project(kind, detail, line, session, state))
    if state["pending"] is not None:
        raise EventError("tool/call without tool/result at projection end")
    return out


def projections(events: list[tuple[str, str]], session: str) -> list[bytes]:
    return [canonical(payload) for payload in project(events, session)]


def decode_host_event(text: str, expected_session: str) -> dict:
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, RecursionError) as exc:
        raise EventError("invalid host event JSON") from exc
    validate(value, expected_session)
    return value
