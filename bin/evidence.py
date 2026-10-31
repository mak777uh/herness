"""evidence — источник, загруженный так, что его можно перепроверить.

Зачем: 38 из 127 утверждений подтверждены собственной прозой — `check_artifacts` ищет строку в
`research/*.md`, то есть доказывает «мы так написали». Здесь внешний факт привязывается к телу
ответа: URL, время, код, sha256. Перезапрос и сверка отделяют три разных события:

  FRESH       источник отдаёт тот же байт-в-байт ответ   → утверждение можно перепроверить
  CHANGED     источник отдаёт другое тело                → утверждение устарело, но не ложно
  GONE        источника больше нет (404/410)             → это отсутствие, а не опровержение
  UNREACHABLE не удалось достучаться                     → «не проверял», а не «нет»

`CHANGED` — не приговор: страница могла обновиться. Но и не «всё в порядке»: пока решение не
перечитано, утверждение остаётся непроверенным. Поэтому код возврата у `verify` — не 0.

Хранилище:
  evidence/index.jsonl        — все попытки, по строке на попытку (append-only, fsync)
  evidence/objects/<sha256>   — тело ответа, если оно 2xx и не больше 256 КиБ

Правило: тело больше лимита не сохраняется, но хеш и код пишутся — «слишком большое» это факт,
а не повод молчать.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
INDEX = EVIDENCE / "index.jsonl"
OBJECTS = EVIDENCE / "objects"
MAX_BODY = 256 * 1024
UA = "herness-evidence/1 (+https://github.com/mak777uh/herness)"
TIMEOUT = 30

__all__ = ["fetch", "record", "append", "load", "latest", "verify", "object_path", "main"]


def object_path(digest: str) -> Path:
    return OBJECTS / digest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _attempt_id(url: str, moment: str) -> str:
    seed = f"{url}|{moment}".encode("utf-8")
    return "ev-" + hashlib.sha1(seed).hexdigest()[:12]


def fetch(url: str, timeout: int = TIMEOUT) -> dict[str, Any]:
    """Загрузить URL. Не бросает: любая беда возвращается полем error (fail-closed по смыслу)."""
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            headers = {k.lower(): v for k, v in response.headers.items()}
            if headers.get("content-encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)
            return {"status": int(response.status), "body": raw, "headers": headers,
                    "final_url": response.geturl(), "error": None}
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read()
        except Exception:  # noqa: BLE001
            raw = b""
        headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
        return {"status": int(exc.code), "body": raw, "headers": headers,
                "final_url": url, "error": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001 — сеть, DNS, TLS, таймаут
        return {"status": 0, "body": b"", "headers": {}, "final_url": url,
                "error": f"{type(exc).__name__}: {str(exc)[:160]}"}


def record(url: str, result: dict[str, Any], *, note: str = "", moment: str | None = None) -> dict:
    """Собрать запись по результату fetch. Тело не кладём в индекс — только хеш и размер."""
    body: bytes = result.get("body") or b""
    headers = result.get("headers") or {}
    status = int(result.get("status") or 0)
    digest = hashlib.sha256(body).hexdigest() if body else ""
    store_body = bool(body) and status == 200 and len(body) <= MAX_BODY
    return {
        "id": _attempt_id(url, moment or _now()),
        "url": url,
        "final_url": result.get("final_url") or url,
        "status": status,
        "fetched_at": moment or _now(),
        "sha256": digest,
        "bytes": len(body),
        "content_type": headers.get("content-type"),
        "etag": headers.get("etag"),
        "last_modified": headers.get("last-modified"),
        "kind": "ok" if 200 <= status < 300 else ("absence" if status in (404, 410) else
                                                 ("error" if status == 0 else "http_error")),
        "body_stored": store_body,
        "body_digest": digest if store_body else None,
        "note": note,
        "error": result.get("error"),
        "version": 1,
    }


def append(entry: dict, body: bytes = b"", *, root: Path | None = None) -> dict:
    """Записать попытку: тело в objects/, строка в индекс. Индекс — append-only, с fsync.

    Тело пишется атомарно (tmp + replace), индекс дописывается с fsync: потеря строки индекса
    означает потерю свидетельства, а потеря тела — только повторную загрузку.
    """
    base = root or EVIDENCE
    index = base / "index.jsonl"
    objects = base / "objects"
    index.parent.mkdir(parents=True, exist_ok=True)
    if entry.get("body_stored") and entry.get("sha256") and body:
        objects.mkdir(parents=True, exist_ok=True)
        target = objects / entry["sha256"]
        if not target.exists():
            tmp = objects / f".{entry['sha256']}.{os.getpid()}.tmp"
            tmp.write_bytes(body)
            os.replace(tmp, target)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(index, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    return entry


def load(*, root: Path | None = None) -> list[dict]:
    index = (root or EVIDENCE) / "index.jsonl"
    if not index.exists():
        return []
    out = []
    for line in index.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            # битая строка не выкидывается: она и есть свидетельство того, что запись не удалась
            out.append({"id": "", "kind": "malformed", "url": "", "status": 0,
                        "raw": line[:200]})
            continue
        out.append(item)
    return out


def latest(entries: list[dict], *, url: str | None = None, ev_id: str | None = None) -> dict | None:
    found = None
    for item in entries:
        if item.get("kind") == "malformed":
            continue
        if ev_id and item.get("id") != ev_id:
            continue
        if url and item.get("url") != url:
            continue
        found = item
    return found


def verify(entry: dict, *, root: Path | None = None,
           fetch_fn: Callable[[str], dict[str, Any]] = fetch) -> tuple[str, str]:
    """Перезапросить источник и сравнить с записью. Возвращает (verdict, объяснение)."""
    url = entry.get("url") or ""
    if not url:
        return "NO_BODY", "в записи нет URL"
    expected = entry.get("sha256") or ""
    if not expected:
        return "NO_BODY", "в записи нет хеша: сравнивать нечего"
    again = fetch_fn(url)
    status = int(again.get("status") or 0)
    if again.get("error") and status == 0:
        return "UNREACHABLE", f"перезапрос не удался: {again['error']}"
    if status in (404, 410):
        return "GONE", f"источник отвечает {status}: это отсутствие, а не опровержение"
    body = again.get("body") or b""
    digest = hashlib.sha256(body).hexdigest()
    if digest == expected:
        return "FRESH", f"тот же ответ, sha256 {digest[:16]}…"
    if status != 200:
        return "CHANGED", f"ответ {status}, тело другое — утверждение требует перечитки"
    return "CHANGED", (f"источник отдаёт другой ответ (было {expected[:16]}…, "
                       f"стало {digest[:16]}…): утверждение устарело, но не ложно")


def _cmd_fetch(argv: list[str]) -> int:
    if not argv:
        print("нужен URL", file=sys.stderr)
        return 3
    url = argv[0]
    note = ""
    if "--note" in argv:
        note = argv[argv.index("--note") + 1]
    result = fetch(url)
    entry = record(url, result, note=note)
    append(entry, result.get("body") or b"")
    print(json.dumps({k: entry[k] for k in
                      ("id", "status", "kind", "bytes", "sha256", "body_stored", "error")},
                     ensure_ascii=False))
    return 0 if entry["kind"] == "ok" else 1


def _cmd_verify(argv: list[str]) -> int:
    if not argv:
        print("нужен id или URL", file=sys.stderr)
        return 3
    target = argv[0]
    entries = load()
    entry = latest(entries, ev_id=target) if target.startswith("ev-") else latest(entries, url=target)
    if entry is None:
        print(f"{target}: нет в индексе — сначала fetch", file=sys.stderr)
        return 3
    verdict, detail = verify(entry)
    print(f"{verdict}\t{entry.get('url')}\t{detail}")
    return {"FRESH": 0, "CHANGED": 1, "GONE": 2, "UNREACHABLE": 2, "NO_BODY": 2}.get(verdict, 2)


def _cmd_show(argv: list[str]) -> int:
    """Показать запись без сети: что именно мы зафиксировали. Нужно для утверждений, у которых
    проверка не должна зависеть от доступности источника (гейты не ходят в интернет)."""
    if not argv:
        print("нужен id или URL", file=sys.stderr)
        return 3
    target = argv[0]
    entries = load()
    entry = latest(entries, ev_id=target) if target.startswith("ev-") else latest(entries, url=target)
    if entry is None:
        print(f"{target}: нет в индексе — сначала fetch", file=sys.stderr)
        return 3
    for field in ("id", "url", "status", "kind", "bytes", "sha256", "body_stored",
                  "fetched_at", "note"):
        print(f"{field}: {entry.get(field)}")
    return 0


def _cmd_list(argv: list[str]) -> int:
    limit = 20
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    entries = [e for e in load() if e.get("kind") != "malformed"]
    print(f"попыток: {len(entries)}, объектов: "
          f"{len(list(OBJECTS.glob('*'))) if OBJECTS.exists() else 0}")
    for item in entries[-limit:]:
        print(f"  {item.get('id')}  {item.get('status')}  {item.get('kind'):<9} "
              f"{item.get('bytes'):>7} Б  {item.get('url')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print("fetch <url> [--note TEXT] | verify <id|url> | show <id|url> | list [--limit N]", file=sys.stderr)
        return 3
    command, rest = argv[0], argv[1:]
    if command == "fetch":
        return _cmd_fetch(rest)
    if command == "verify":
        return _cmd_verify(rest)
    if command == "show":
        return _cmd_show(rest)
    if command == "list":
        return _cmd_list(rest)
    print(f"неизвестная команда: {command}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())
