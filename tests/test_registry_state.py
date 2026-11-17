"""Производный `active`: события, а не JSON-поле, дают допуск.

Проверки:
- текущая цепочка: шесть legacy quarantined/rejected, head candidate, active пуст;
- удаление quarantine-события меняет состояние (событие — источник, а не комментарий);
- подложенный `"status": "active"` в registry.jsonl не делает инструмент активным;
- событие admitted без owner-подписи/evidence даёт admitted_inactive, а не active;
- разрыв prev/seq ломается;
- preflight не находит search по умолчанию и не запускает его;
- registry.state.json свежий относительно событий.

    python tests/test_registry_state.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import build_registry, preflight, registry_state as rs  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((flag, message))


def current() -> tuple[list[dict], list[tuple[bytes, dict]], str, str, dict]:
    rows = rs.read_snapshot()
    events = rs.read_events()
    snapshot_digest = rs.digest_file(rs.SNAPSHOT)
    policy_digest = rs.digest_file(rs.POLICY)
    state = rs.derive(rows, events, snapshot_digest, policy_digest)
    return rows, events, snapshot_digest, policy_digest, state


def rechain(events: list[tuple[bytes, dict]]) -> list[tuple[bytes, dict]]:
    """Собрать валидную цепочку из выбранных событий: seq и prev пересчитаны."""
    out: list[tuple[bytes, dict]] = []
    prev = rs.genesis_prev()
    for index, (_, event) in enumerate(events):
        event = copy.deepcopy(event)
        event["seq"] = index
        event["prev"] = prev
        line = rs.canonical(event)
        out.append((line, event))
        prev = rs.line_hash(line)
    return out


def appended(events: list[tuple[bytes, dict]], tool: str, body: dict) -> list[tuple[bytes, dict]]:
    last_line = events[-1][0]
    event = {
        "schema": rs.EVENT_SCHEMA,
        "seq": len(events),
        "prev": rs.line_hash(last_line),
        "type": "admitted",
        "tool_id": tool,
        "at": "2026-11-17T00:00:09Z",
        "body": body,
    }
    line = rs.canonical(event)
    return events + [(line, json.loads(line.decode("utf-8")))]


def main() -> int:
    rows, events, snapshot_digest, policy_digest, state = current()

    for tool in rs.LEGACY:
        expected = {"search": "rejected"}.get(tool, "quarantined")
        actual = state["tools"].get(tool, {}).get("state")
        check(actual == expected, f"{tool}: {actual}, ждали {expected}")
    check(state["tools"].get("head", {}).get("state") == "candidate",
          "head остаётся candidate, а не active")
    check(state["active"] == [], f"active пуст: {state['active']}")

    # Удаление quarantine-события меняет состояние: источник — событие, не снимок.
    without_list = rechain([item for item in events if not (
        item[1].get("tool_id") == "list" and item[1].get("type") == "quarantined")])
    changed = rs.derive(rows, without_list, snapshot_digest, policy_digest)
    check(changed["tools"]["list"]["state"] == "unreviewed",
          "без quarantine-события list снова unreviewed (state меняется)")

    # JSON-поле status не читается: подложенный active не даёт полномочия.
    injected_rows = copy.deepcopy(rows)
    for row in injected_rows:
        if row["id"] == "list":
            row["status"] = "active"
    injected = rs.derive(injected_rows, events, snapshot_digest, policy_digest)
    check(injected["tools"]["list"]["state"] == "quarantined",
          "подложенный status=active не делает list активным")
    check(injected["active"] == [], "подложенный status=active не попадает в active")
    check(any("status" in item for item in build_registry.problems(injected_rows)),
          "build_registry отвергает хранение status в снимке")

    # admitted без owner-подписи/evidence — admitted_inactive, не active.
    unsigned = appended(events, "head", {"reason": "синтетическое событие без подписи"})
    unsigned_state = rs.derive(rows, unsigned, snapshot_digest, policy_digest)
    check(unsigned_state["tools"]["head"]["state"] == "admitted_inactive",
          "admitted без owner-подписи не становится active")
    check(unsigned_state["active"] == [], "admitted без evidence не попадает в active")

    # Полный синтетический admitted (in-memory) показывает, что active выводится.
    signed = appended(events, "head", {
        "reason": "selftest",
        "owner_signed": True,
        "admission_digest": "sha256:" + "0" * 64,
        "evidence_digest": "sha256:" + "1" * 64,
    })
    signed_state = rs.derive(rows, signed, snapshot_digest, policy_digest)
    check(signed_state["tools"]["head"]["state"] == "active",
          "полное admitted-событие даёт active только через вывод")
    check(signed_state["active"] == ["head"], "active содержит head только в синтетике")

    # Цепочка: правка body с пересчётом JCS ломает prev следующего события.
    tampered = list(events)
    line, event = tampered[3]
    event = copy.deepcopy(event)
    event["body"]["reason"] = "подмена"
    tampered[3] = (rs.canonical(event), event)
    problems = rs.validate_events(tampered, snapshot_digest, policy_digest)
    check(any("prev" in problem for problem in problems),
          f"правка события ломает цепочку: {problems[:1]}")

    # preflight: active пуст, search не находится; quarantined только для диагностики.
    preflight_rows = preflight.load()
    check(preflight.find("найти подстроку в файлах", preflight_rows) == [],
          "preflight по умолчанию не находит search")
    check(all(item["id"] != "search" for item in preflight.find(
        "найти подстроку в файлах", preflight_rows, ("quarantined",))),
        "search не находится в диагностике quarantined: он rejected")
    check(any(item["id"] == "list" for item in preflight.find(
        "перечислить содержимое каталога", preflight_rows, ("quarantined",))),
        "quarantined list виден только в диагностическом режиме")

    # CLI authority.
    ok, message = rs.authorize("search")
    check(not ok and "S13_TOOL_INACTIVE" in message, "authorize(search) — S13")
    ok, message = rs.authorize("head")
    check(not ok and "candidate" in message, "authorize(head) — candidate")
    ok, _ = rs.authorize("net")
    check(ok, "net — отдельный bridge path, не блокируется реестром")

    problems = rs.check_files()
    check(problems == [], f"registry.state.json и цепочка согласованы: {problems[:2]}")

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
