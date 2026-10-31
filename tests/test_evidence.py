"""Тесты evidence: запись перепроверяема, а «нет» отличается от «не смог» и от «изменилось»."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import evidence  # noqa: E402

CASES: list[tuple[str, callable]] = []


def case(name: str):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def ok(body: bytes = b"hello") -> dict:
    return {"status": 200, "body": body, "headers": {"content-type": "text/plain"},
            "final_url": "https://example.test/x", "error": None}


@case("запись кладёт тело в objects и строку в индекс")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        result = ok()
        entry = evidence.record("https://example.test/x", result, moment="2026-10-31T12:00:00+00:00")
        evidence.append(entry, result["body"], root=base)
        entries = evidence.load(root=base)
        assert len(entries) == 1 and entries[0]["id"] == entry["id"]
        assert (base / "objects" / entry["sha256"]).read_bytes() == b"hello"
        assert entry["kind"] == "ok" and entry["body_stored"] is True


@case("verify: тот же ответ — FRESH")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        entry = evidence.record("https://example.test/x", ok(), moment="2026-10-31T12:00:00+00:00")
        evidence.append(entry, b"hello", root=Path(tmp))
        verdict, detail = evidence.verify(entry, fetch_fn=lambda url: ok(b"hello"))
        assert verdict == "FRESH", (verdict, detail)


@case("verify: другой ответ — CHANGED, и это не «ложь»")
def _():
    entry = evidence.record("https://example.test/x", ok(), moment="2026-10-31T12:00:00+00:00")
    verdict, detail = evidence.verify(entry, fetch_fn=lambda url: ok(b"hello, world"))
    assert verdict == "CHANGED", (verdict, detail)
    assert "не ложно" in detail or "требует перечитки" in detail


@case("verify: 404 — GONE, а не опровержение")
def _():
    entry = evidence.record("https://example.test/gone", ok(), moment="2026-10-31T12:00:00+00:00")
    verdict, detail = evidence.verify(
        entry, fetch_fn=lambda url: {"status": 404, "body": b"nope", "headers": {},
                                     "final_url": url, "error": "HTTP 404"})
    assert verdict == "GONE", (verdict, detail)
    assert "отсутствие" in detail


@case("verify: сеть не ответила — UNREACHABLE, а не «нет»")
def _():
    entry = evidence.record("https://example.test/x", ok(), moment="2026-10-31T12:00:00+00:00")
    verdict, detail = evidence.verify(
        entry, fetch_fn=lambda url: {"status": 0, "body": b"", "headers": {},
                                     "final_url": url, "error": "URLError: timeout"})
    assert verdict == "UNREACHABLE", (verdict, detail)


@case("тело больше лимита не сохраняется, но хеш и размер пишутся")
def _():
    big = b"x" * (evidence.MAX_BODY + 10)
    entry = evidence.record("https://example.test/big", ok(big), moment="2026-10-31T12:00:00+00:00")
    assert entry["body_stored"] is False
    assert entry["sha256"] and entry["bytes"] == len(big)


@case("битая строка индекса не роняет чтение")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        entry = evidence.record("https://example.test/x", ok(), moment="2026-10-31T12:00:00+00:00")
        evidence.append(entry, b"hello", root=base)
        with open(base / "index.jsonl", "a", encoding="utf-8") as handle:
            handle.write("{не json}\n")
        entries = evidence.load(root=base)
        assert len(entries) == 2
        assert entries[-1]["kind"] == "malformed"


@case("проверка без хеша не притворяется проверкой")
def _():
    entry = evidence.record("https://example.test/x", {"status": 0, "body": b"", "headers": {},
                                                      "final_url": "", "error": "boom"},
                            moment="2026-10-31T12:00:00+00:00")
    verdict, _detail = evidence.verify(entry, fetch_fn=lambda url: ok())
    assert verdict == "NO_BODY", verdict


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            ok_case = True
        except AssertionError:
            ok_case = False
        failed += 0 if ok_case else 1
        print(f"[{'ok' if ok_case else 'FAIL'}] {name}")
    print(f"\nevidence: {len(CASES) - failed}/{len(CASES)} ok")
    print(f"провалов: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
