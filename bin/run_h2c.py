"""Плечо C: та же дисциплина, но всего 2 источника — проверка границы чувствительности."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"C:\111\herness")
sys.path.insert(0, str(ROOT))

import bin.run_h2 as runner  # noqa: E402
import bin.score_h2 as scorer  # noqa: E402

H2C = ROOT / "lab" / "h2c"
runner.H2 = H2C
runner.SOURCES = {
    "P16-RESULTS.md": ROOT / "research" / "P16-RESULTS-2026-10-30.md",
    "SELF-WORK.md": ROOT / "lab" / "self-work" / "REPORT.md",
}

if __name__ == "__main__":
    code = runner.main(["3"])
    scorer.H2 = H2C
    scorer.SOURCES = list(runner.SOURCES)
    scorer.main()
    sys.exit(code)
