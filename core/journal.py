"""Журнал прогона: append-only события + артефакты с дайджестом.

Инварианты (ADR-0003):
  I1 — инструмент возвращает ссылку на артефакт, тело ложится на диск;
  I2 — модель не пишет в рабочую зону напрямую;
  I3 — журнал синхронизируется (fsync) до возврата управления.

Главное: записать результат инструмента без существующего артефакта нельзя. Не «не рекомендуется»,
а нельзя: результат без свидетельства — это и есть тот класс ошибки, ради которого всё строится.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .contracts import ContractError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class ArtifactRef:
    sha256: str
    path: str
    bytes: int


class Journal:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.artifacts = self.run_dir / "artifacts"
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / "events.jsonl"
        self._seq = 0
        self._prev = "genesis"
        if self.path.exists():
            # продолжаем цепочку, а не начинаем с нуля
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._seq = max(self._seq, int(event.get("seq", 0)))
                self._prev = event.get("hash", self._prev)
        self._fh = self.path.open("a", encoding="utf-8", newline="\n")

    # ---------------------------------------------------------------- ядро журнала

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _append(self, kind: str, payload: dict) -> dict:
        self._seq += 1
        event = {"seq": self._seq, "ts": _now(), "type": kind, "payload": payload,
                 "prev": self._prev}
        canonical = json.dumps(event, ensure_ascii=False, sort_keys=True)
        event["hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self._prev = event["hash"]
        self._fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())
        return event

    def event(self, kind: str, payload: dict | None = None) -> dict:
        return self._append(kind, payload or {})

    def close(self) -> None:
        try:
            self._fh.flush()
            os.fsync(self._fh.fileno())
        finally:
            self._fh.close()

    # ---------------------------------------------------------------- артефакты

    def put_artifact(self, data: bytes, ext: str = ".txt") -> ArtifactRef:
        sha = hashlib.sha256(data).hexdigest()
        path = self.artifacts / f"{sha}{ext}"
        if not path.exists():
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(data)
            with tmp.open("rb+") as fh:
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        return ArtifactRef(sha256=sha, path=str(path.relative_to(self.run_dir)), bytes=len(data))

    def verify(self, ref: ArtifactRef) -> None:
        path = self.run_dir / ref.path
        if not path.exists():
            raise ContractError(f"артефакт отсутствует на диске: {ref.path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != ref.sha256:
            raise ContractError(f"артефакт не совпадает с дайджестом: {ref.path}")

    # ---------------------------------------------------------------- события прогона

    def run_start(self, task: str, model: str) -> dict:
        return self._append("run/start", {"task": task, "model": model})

    def tool_call(self, call_id: str, name: str, arguments: dict) -> dict:
        return self._append("tool/call", {"call_id": call_id, "name": name, "arguments": arguments})

    def tool_result(self, call_id: str, ref: ArtifactRef, ok: bool, preview: str = "") -> dict:
        """Результат инструмента без проверенного артефакта записан быть не может."""
        self.verify(ref)
        return self._append("tool/result", {
            "call_id": call_id,
            "artifact": {"sha256": ref.sha256, "path": ref.path, "bytes": ref.bytes},
            "ok": ok,
            "preview": preview[:2000],
        })

    def assistant_message(self, text: str) -> dict:
        return self._append("assistant/message", {"text": text})

    def run_end(self, status: str) -> dict:
        return self._append("run/end", {"status": status})
