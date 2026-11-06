"""probe_extension — замер продления бюджета.

Вопрос владельца: агент может попросить продления до 50 % от исходного бюджета; каков оптимум.
Здесь бюджет задаётся критерием (max_steps), и одна и та же задача решается при 0 %, 25 % и 50 %.

Важно: продление имеет смысл только там, где бюджет — ограничение. Если задача решается за 3 шага,
любой бюджет даёт тот же результат, а разница в принятии будет шумом формы ответа (F-0065).

    python bin/probe_extension.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 6
TASK = "Какой тип свидетельства у утверждения C-0196? Ответь одним словом."
SOURCE = ROOT / "accept" / "history" / "T-claim-C-0196.json"
OUT = ROOT / "accept" / "extension"


def make_criteria() -> list[tuple[float, Path]]:
    OUT.mkdir(parents=True, exist_ok=True)
    base = json.loads(SOURCE.read_text(encoding="utf-8"))
    # Опора — по номеру утверждения: ответ обязан его повторить, иначе это не опора (F-0037).
    base["anchor_regex"] = "C-0196"
    made = []
    for fraction in (0.0, 0.25, 0.5):
        steps = max(1, int(round(BASE * (1 + fraction))))
        data = dict(base)
        data["max_steps"] = steps
        data["task"] = TASK
        path = OUT / f"ext-{int(fraction * 100):02d}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        made.append((fraction, path))
    return made


def run(fraction: float, criteria: Path) -> dict:
    shutil.copy2(ROOT / "share.img", ROOT / "core-rs" / "acc.img")
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", "core-rs/accept-run.ps1", "-Mode", "loop-bridge",
         "-Kernel", "vmlinuz-own-net", "-Net", "-TimeoutSec", "420",
         "-Criteria", str(criteria.relative_to(ROOT)).replace("\\", "/"), "-Task", TASK],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    tail = [line for line in result.stdout.splitlines() if "итог:" in line]
    journal = ROOT / "runs" / "accept" / "journal.bin"
    steps = 0
    if journal.exists():
        sys.path.insert(0, str(ROOT))
        from bin import accept  # noqa: E402
        records, _t, _p = accept.parse_journal(journal.read_bytes())
        steps = sum(1 for kind, _ in accept.events(records) if kind == "step")
        shutil.copy2(journal, ROOT / "runs" / "accept" / f"ext-{int(fraction * 100):02d}.bin")
    return {"fraction": fraction, "outcome": tail[-1] if tail else "нет итога", "steps": steps}


def main() -> int:
    rows = [run(fraction, path) for fraction, path in make_criteria()]
    text = (
        "# Замер продления бюджета (база 6 шагов, задача C-0196)\n\n"
        + "\n".join(f"предел {row['fraction']:.0%}: {row['outcome']}, шагов {row['steps']}" for row in rows)
        + "\n\n# Задача решается за 2–3 шага при любом бюджете: продление здесь не ограничение,\n"
        "# поэтому разница в принятии — шум формы ответа, а не польза продления (F-0065).\n"
        "# Для настоящего замера нужна задача, которая упирается в бюджет.\n"
    )
    (ROOT / "research" / "outputs" / "extension-probe.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
