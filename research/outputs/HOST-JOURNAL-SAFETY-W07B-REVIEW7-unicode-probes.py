"""Read-only subprocess probes для E-0062 Unicode criterion boundary."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_host_journal_accept_review7 import JOURNAL  # noqa: E402

CASES = [
    ("visible-task", r'{"require_status":"done","task":"VISIBLE-\ud800"}', "VISIBLE-"),
    ("visible-status", r'{"require_status":"done\ud800"}', "done"),
    ("hidden-task", r'{"require_status":"done","hidden":{"task":"HIDDEN-\ud800"}}', "HIDDEN-"),
    ("json-key", r'{"require_status":"done","\ud800":1}', r"\ud800"),
]

for name, raw, sentinel in CASES:
    with tempfile.TemporaryDirectory() as tmp:
        criterion = Path(tmp) / "criterion.json"
        journal = Path(tmp) / "journal.bin"
        criterion.write_text(raw, encoding="utf-8")
        journal.write_bytes(JOURNAL)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "accept.py"), str(criterion), str(journal)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            check=False,
        )
        output = proc.stdout + proc.stderr
        assert proc.returncode == 2, (name, proc.returncode, output)
        assert "итог: PASS" not in output, (name, output)
        assert "Traceback" not in output, (name, output)
        assert sentinel not in output, (name, output)
        assert "недопустимую Unicode" in proc.stderr, (name, output)
        print(f"[ok] {name}: rc=2; no traceback; value not leaked")

with tempfile.TemporaryDirectory() as tmp:
    criterion = Path(tmp) / "criterion.json"
    journal = Path(tmp) / "journal.bin"
    criterion.write_text(
        '{"require_status":"done","task":"найти опору \\ud83d\\ude00"}',
        encoding="utf-8",
    )
    journal.write_bytes(JOURNAL)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "accept.py"), str(criterion), str(journal)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, (proc.returncode, output)
    assert "итог: PASS" in proc.stdout, output
    assert "Traceback" not in output, output
    print("[ok] valid-surrogate-pair: rc=0; PASS")
