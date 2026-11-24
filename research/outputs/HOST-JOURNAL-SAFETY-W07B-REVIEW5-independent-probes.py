"""Read-only reproductions for the four E-0060 review findings."""

from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bin import accept, hsj2  # noqa: E402

LINES = [
    "run/start task: найти опору",
    "tool/call search /mnt CLAIMS",
    "tool/result ok /mnt/CLAIMS.md:4: опора",
    "step 1, потрачено 0.00010000",
    "claim/anchored /mnt/CLAIMS.md:4",
    "run/end Опора лежит в /mnt/CLAIMS.md:4",
]
JOURNAL = hsj2.journal([
    *[(hsj2.DATA, line) for line in LINES],
    (hsj2.COMMIT, b""),
])
RECORDS, TAIL, PROBLEMS = accept.parse_journal(JOURNAL)
assert not TAIL and not PROBLEMS


def direct(name: str, criteria: dict) -> None:
    try:
        ok, rows = accept.check(criteria, RECORDS)
        print(f"{name}: ok={ok}; rows={rows}")
    except Exception as exc:  # noqa: BLE001
        print(f"{name}: raised={type(exc).__name__}: {exc}")


def cli(name: str, raw: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        criterion = directory / "criterion.json"
        journal = directory / "journal.bin"
        criterion.write_text(raw, encoding="utf-8")
        journal.write_bytes(JOURNAL)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = accept.main([str(criterion), str(journal)])
        print(f"{name}: rc={code}")
        print(f"{name}: stdout={stdout.getvalue()!r}")
        print(f"{name}: stderr={stderr.getvalue()!r}")


direct("nested-hidden", {"hidden": {"max_steps": 1, "hidden": "SENTINEL-NESTED"}})
cli(
    "duplicate-hidden-malformed-first",
    '{"require_status":"done","hidden":"SENTINEL-DUP","hidden":{}}',
)
cli(
    "duplicate-hidden-malformed-last",
    '{"require_status":"done","hidden":{},"hidden":"SENTINEL-DUP"}',
)
cli(
    "nonfinite-infinity",
    '{"require_status":"done","hidden":{"max_steps":Infinity}}',
)
cli(
    "nonfinite-overflow",
    '{"require_status":"done","hidden":{"max_steps":1e309}}',
)
cli(
    "hidden-value-traceback",
    '{"require_status":"done","hidden":{"min_objects":"HIDDEN-SENTINEL-CONDITION"}}',
)
