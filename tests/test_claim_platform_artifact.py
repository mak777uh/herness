"""E-0080: исторический platform-bound claim проверяется артефактом, не повторным probe.

Запуск: python tests/test_claim_platform_artifact.py
Windows и POSIX: 5/5 без N/A. QEMU, сеть, секреты и owner keys не используются.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bin import check_artifacts, verify_claims  # noqa: E402

RESULTS: list[tuple[bool, str]] = []
EXPECTED_COMMAND = "python bin/check_artifacts.py C-0340"
EXPECTATION = "(?s)VERDICT: RED.*fallback_calls: 0"


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


def claim_row() -> dict:
    rows = [row for row in verify_claims.parse() if row["id"] == "C-0340"]
    if len(rows) != 1:
        raise AssertionError(f"ожидалась одна строка C-0340, найдено {len(rows)}")
    return rows[0]


def synthetic_check(evidence: str | None) -> int:
    """Прогнать настоящий check_artifacts.main на временной claim/evidence паре."""
    original_root = check_artifacts.ROOT
    original_claims = check_artifacts.CLAIMS
    try:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            claims = root / "CLAIMS.md"
            claims.write_text(
                "| C-9999 | historical platform observation | test | "
                f"`{EXPECTED_COMMAND}` | evidence.txt | 25.11.2026 | `{EXPECTATION}` |\n",
                encoding="utf-8",
            )
            if evidence is not None:
                (root / "evidence.txt").write_text(evidence, encoding="utf-8")
            check_artifacts.ROOT = root
            check_artifacts.CLAIMS = claims
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                return check_artifacts.main(["C-9999"])
    finally:
        check_artifacts.ROOT = original_root
        check_artifacts.CLAIMS = original_claims


def test_current_command() -> None:
    row = claim_row()
    check(row["cmd"] == EXPECTED_COMMAND and "vsock_probe" not in row["cmd"],
          "C-0340 использует artifact-check и не запускает vsock_probe")


def test_real_artifact() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "check_artifacts.py"), "C-0340"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    check(proc.returncode == 0 and "найдено в свидетельстве" in proc.stdout,
          "неизменный VSOCK-WIN-R1 artifact принимается")


def test_pass_verdict_rejected() -> None:
    rc = synthetic_check("VERDICT: PASS\nfallback_calls: 0\n")
    check(rc == 1, "мутант VERDICT: PASS отвергается")


def test_nonzero_fallback_rejected() -> None:
    rc = synthetic_check("VERDICT: RED\nfallback_calls: 1\n")
    check(rc == 1, "мутант fallback_calls: 1 отвергается")


def test_missing_artifact_rejected() -> None:
    rc = synthetic_check(None)
    check(rc == 1, "отсутствующий artifact отвергается")


def main() -> int:
    tests = (
        test_current_command,
        test_real_artifact,
        test_pass_verdict_rejected,
        test_nonzero_fallback_rejected,
        test_missing_artifact_rejected,
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
    return 0 if failed_count == 0 and len(RESULTS) == 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
