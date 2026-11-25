"""E-0081: Decision brief links portable across Windows and POSIX.

Запуск: python tests/test_portable_brief_links.py
Восемь controls; сеть, секреты и owner keys не используются.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin.hs import LINK_RE, gate_links  # noqa: E402

RESULTS: list[tuple[bool, str]] = []
WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
BRIEFS = sorted((ROOT / "research").glob("ARCHITECTURE-BRIEF-v0*.md"))
PLAN = ROOT / "research" / "sources" / "APPROVED-PLAN-2026-11-23.txt"
ANSWERS = ROOT / "research" / "sources" / "OWNER-ANSWERS-2026-11-24.txt"


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def exact_source(path: Path, expected_bytes: int, expected_lf: int, expected_hash: str) -> None:
    if not path.is_file():
        check(False, f"source отсутствует: {path.relative_to(ROOT)}")
        return
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    lf = data.count(b"\n")
    cr = data.count(b"\r")
    check(
        len(data) == expected_bytes and lf == expected_lf and cr == 0 and digest == expected_hash,
        f"{path.name}: exact bytes/LF/hash ({len(data)}/{lf}/{digest})",
    )


def raw_attribute(path: Path) -> None:
    rel = path.relative_to(ROOT).as_posix()
    proc = subprocess.run(
        ["git", "check-attr", "text", "--", rel],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    check(
        proc.returncode == 0 and proc.stdout.strip().endswith(": unset"),
        f"{path.name}: git text attribute unset",
    )


def test_brief_targets() -> None:
    absolute: list[str] = []
    unresolved: list[str] = []
    for path in BRIEFS:
        text = path.read_text(encoding="utf-8")
        for target in LINK_RE.findall(text):
            target = target.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if WINDOWS_ABSOLUTE.match(target):
                absolute.append(f"{path.name}: {target}")
            elif not (path.parent / target).resolve().exists():
                unresolved.append(f"{path.name}: {target}")
    check(
        len(BRIEFS) == 5 and not absolute and not unresolved,
        f"briefs: 5 файлов, absolute={len(absolute)}, unresolved={len(unresolved)}",
    )


def test_plan_exact() -> None:
    exact_source(PLAN, 101675, 325, "62e1d9e3a62941e63272dd788424e764cc1bbd63e4b8144945983d03e7b4d92a")


def test_answers_exact() -> None:
    exact_source(ANSWERS, 9234, 182, "b087ff12574815c1ae8e5d4eb312dffd2000263f479847ab210e3d4dfde59873")


def test_plan_raw_attribute() -> None:
    raw_attribute(PLAN)


def test_answers_raw_attribute() -> None:
    raw_attribute(ANSWERS)


def test_revision_metadata() -> None:
    failures: list[str] = []
    checked = 0
    pattern = re.compile(
        r"^Предыдущая ревизия: .*?\]\(([^)]+)\), ([\d ]+) строк\w*, ([\d ]+) байт\w*, "
        r"SHA-256 `([0-9a-f]{64})`",
        re.MULTILINE,
    )
    for name in ("ARCHITECTURE-BRIEF-v0.2.md", "ARCHITECTURE-BRIEF-v0.3.md", "ARCHITECTURE-BRIEF-v0.4.md"):
        path = ROOT / "research" / name
        match = pattern.search(path.read_text(encoding="utf-8"))
        if not match:
            failures.append(f"{name}: нет revision metadata")
            continue
        target = (path.parent / match.group(1)).resolve()
        data = target.read_bytes()
        actual = (data.count(b"\n"), len(data), hashlib.sha256(data).hexdigest())
        expected = (
            int(match.group(2).replace(" ", "")),
            int(match.group(3).replace(" ", "")),
            match.group(4),
        )
        checked += 1
        if actual != expected:
            failures.append(f"{name}: {expected} != {actual}")
    check(checked == 3 and not failures, f"revision metadata: {checked}/3; {'; '.join(failures)}")


def test_gate_rejects_absolute() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "absolute.md").write_text(
            "[source](C:/Users/Admin/.qoder/plans/final-river-bison.md)\n",
            encoding="utf-8",
        )
        problems = gate_links(root)
    check(
        len(problems) == 1 and "абсолютный Windows-путь" in problems[0],
        "gate отвергает drive-letter ссылку даже когда путь существует на Windows",
    )


def test_gate_accepts_relative() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "target.txt").write_text("ok\n", encoding="utf-8")
        (root / "relative.md").write_text("[source](target.txt)\n", encoding="utf-8")
        problems = gate_links(root)
    check(not problems, "gate принимает разрешимую repo-relative ссылку")


def main() -> int:
    tests = (
        test_brief_targets,
        test_plan_exact,
        test_answers_exact,
        test_plan_raw_attribute,
        test_answers_raw_attribute,
        test_revision_metadata,
        test_gate_rejects_absolute,
        test_gate_accepts_relative,
    )
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 — ошибка чтения/парсинга тоже RED
            check(False, f"{test.__name__}: {type(exc).__name__}: {exc}")
    failed_count = 0
    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
        failed_count += 0 if flag else 1
    print(f"проверок: {len(RESULTS)}; провалов: {failed_count}")
    return 0 if failed_count == 0 and len(RESULTS) == 8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
