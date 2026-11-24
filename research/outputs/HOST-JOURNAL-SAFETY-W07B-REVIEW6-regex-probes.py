"""Additional read-only probes for regex compiler OverflowError/RecursionError."""

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

for name, pattern in (
    ("regex-overflow", "a{999999999999999999999}"),
    ("regex-recursion", "(" * 2000 + "a" + ")" * 2000),
):
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        criterion = directory / "criterion.json"
        journal = directory / "journal.bin"
        criterion.write_text(
            json.dumps({"require_status": "done", "hidden": {"anchor_regex": pattern}}),
            encoding="utf-8",
        )
        journal.write_bytes(JOURNAL)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = accept.main([str(criterion), str(journal)])
        output = stdout.getvalue() + stderr.getvalue()
        assert code != 0, (name, code, output)
        assert "итог: PASS" not in output, (name, output)
        assert "Traceback" not in output, (name, output)
        assert pattern not in output, (name, output)
        print(f"[ok] {name}: rc={code}; no traceback; pattern not leaked")
