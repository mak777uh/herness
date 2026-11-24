"""E-0075: hash-verified methodology inheritance для correction-overlay."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import prereg  # noqa: E402

RESULTS: list[tuple[bool, str]] = []
OVERLAY = "PILOT-GENERATOR-R1-BASELINE-CORRECTION.json"
OVERLAY_SHA256 = "9727c89059c077c275e9960c83507e9750721c0d0e66a2a36384c86038b5f87b"
SOURCE_SHA256 = "42fb4a435df7798a0505e459bf315b5582c04bfd20ce76b7fcf8789d7b9c2af5"


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def source_document() -> dict:
    return {
        "schema": 2,
        "id": "SOURCE",
        "date": "2026-11-25",
        "question": "source question",
        "hypothesis": "source hypothesis",
        "criterion": "source criterion",
        "arms": ["source arm"],
        "sensitivity": "source sensitivity",
        "unit_of_analysis": "source unit",
        "primary_metric": "source metric",
        "test": "source test",
        "stopping_rule": "source stopping rule",
    }


def overlay_document(digest: str, **overrides) -> dict:
    document = {
        "schema": 2,
        "id": "OVERLAY",
        "date": "2026-11-25",
        "question": "overlay question",
        "hypothesis": "overlay hypothesis",
        "criterion": "overlay criterion",
        "source_prereg": "lab/prereg/source.json",
        "source_prereg_sha256": digest,
        "historical_frozen": {"files": {}},
        "corrected_frozen": {"files": {}},
    }
    document.update(overrides)
    return document


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(root: Path, source: dict | None = None, overlay: dict | None = None) -> Path:
    directory = root / "lab" / "prereg"
    source_path = directory / "source.json"
    if source is not None:
        write_json(source_path, source)
    if overlay is not None:
        write_json(directory / "overlay.json", overlay)
    return directory


def main() -> int:
    # 1. Положительный синтетический overlay наследует ровно отсутствующие v2-поля.
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source = source_document()
        directory = fixture(root, source)
        write_json(directory / "overlay.json", overlay_document(digest(directory / "source.json")))
        items, problems = prereg.entries(directory, root)
        overlay = next(item for item in items if item["id"] == "OVERLAY")
        inherited = ("arms", "sensitivity", *prereg.REQUIRED_V2)
        check(not problems
              and all(overlay.get(field) == source[field] for field in inherited)
              and overlay["question"] == "overlay question"
              and overlay["hypothesis"] == "overlay hypothesis"
              and overlay["criterion"] == "overlay criterion",
              "positive overlay наследует отсутствующие поля и сохраняет явные")

    # 2. Настоящий sealed E-0074 принимается без изменения overlay/source/sidecar.
    overlay_path = ROOT / "lab" / "prereg" / OVERLAY
    source_path = ROOT / "lab" / "prereg" / "PILOT-GENERATOR-R1.json"
    sidecar_path = overlay_path.with_suffix(".json.sha256")
    before = {path: path.read_bytes() for path in (overlay_path, source_path, sidecar_path)}
    items, problems = prereg.entries()
    overlay = next((item for item in items if item["_file"] == OVERLAY), None)
    check(
        overlay is not None
        and not any(problem.startswith(OVERLAY + ":") for problem in problems)
        and bool(overlay.get("sensitivity"))
        and digest(overlay_path) == "sha256:" + OVERLAY_SHA256
        and digest(source_path) == "sha256:" + SOURCE_SHA256
        and all(path.read_bytes() == value for path, value in before.items()),
        "sealed E-0074/source/sidecar не изменены; inheritance подтверждён",
    )

    # 3. Wrong source digest fail-closed.
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        directory = fixture(root, source_document())
        write_json(directory / "overlay.json", overlay_document("sha256:" + "0" * 64))
        _, problems = prereg.entries(directory, root)
        check(any("source_prereg_sha256 не совпадает" in problem for problem in problems),
              "wrong source digest отвергнут")

    # 4. Missing source fail-closed.
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        directory = fixture(root, None, overlay_document("sha256:" + "1" * 64))
        _, problems = prereg.entries(directory, root)
        check(any("source_prereg не найден" in problem for problem in problems),
              "missing source отвергнут")

    # 5. Path traversal fail-closed.
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        directory = fixture(root, None, overlay_document("sha256:" + "2" * 64, source_prereg="../outside.json"))
        _, problems = prereg.entries(directory, root)
        check(any("безопасным repo-relative" in problem for problem in problems),
              "unsafe source path отвергнут")

    # 6. Incomplete source не становится допустимым через inheritance.
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source = source_document()
        source.pop("sensitivity")
        directory = fixture(root, source)
        write_json(directory / "overlay.json", overlay_document(digest(directory / "source.json")))
        _, problems = prereg.entries(directory, root)
        check(any("source_prereg не удовлетворяет схеме" in problem and "sensitivity" in problem
                  for problem in problems),
              "incomplete source отвергнут")

    # 7. Явное поле overlay имеет приоритет над source.
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        directory = fixture(root, source_document())
        write_json(directory / "overlay.json", overlay_document(
            digest(directory / "source.json"), primary_metric="overlay metric"))
        items, problems = prereg.entries(directory, root)
        overlay = next(item for item in items if item["id"] == "OVERLAY")
        check(not problems and overlay["primary_metric"] == "overlay metric",
              "explicit overlay field не перезаписан source")

    # 8. Несвязанный неполный prereg не получает исключения.
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        directory = root / "lab" / "prereg"
        incomplete = {key: value for key, value in source_document().items()
                      if key not in prereg.REQUIRED_V2}
        write_json(directory / "incomplete.json", incomplete)
        _, problems = prereg.entries(directory, root)
        check(any(problem.startswith("incomplete.json: нет полей")
                  and all(field in problem for field in prereg.REQUIRED_V2) for problem in problems),
              "unrelated incomplete prereg остаётся FAIL")

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"проверок: {len(RESULTS)}; провалов: {failed}")
    return 1 if failed or len(RESULTS) != 8 else 0


if __name__ == "__main__":
    raise SystemExit(main())
