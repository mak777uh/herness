"""selfref — утверждения, подтверждённые собственной прозой, и храповик на их число.

Проблема, которую это ловит: команда `check_artifacts.py C-XXXX` с артефактом `research/*.md`
доказывает, что мы так написали, а не что так есть. Такое утверждение нельзя перепроверить
снаружи, и именно поэтому ошибка «каталог tests/ пуст» жила неделю: у неё было «доказательство».

Механизм — храповик, а не запрет:
  * новый самоссылочный случай валит гейт (долг не растёт);
  * запись в базе, которая перестала быть самоссылочной, тоже валит гейт (база обязана убывать);
  * сам список виден и посчитан, а не спрятан.

Замена: `python bin/evidence.py fetch <url>` → запись `evidence/index.jsonl` → в CLAIMS.md
команда `python bin/evidence.py verify <id>` (0 только при FRESH) и артефакт `evidence/index.jsonl`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = Path("evidence") / "selfref-baseline.json"
COLUMNS = 7
SELF_MARK = "check_artifacts"
ARTIFACT_RE = re.compile(r"^research/[^|]+\.md$")

__all__ = ["claims", "problems", "write_baseline", "main"]


def claims(root: Path = ROOT) -> list[str]:
    """Список id, у которых доказательство — собственный текст."""
    path = root / "CLAIMS.md"
    if not path.exists():
        return []
    found: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| C-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != COLUMNS:
            continue
        claim_id, _text, _kind, command, artifact = cells[:5]
        if SELF_MARK in command and ARTIFACT_RE.match(artifact.strip("`")):
            found.append(claim_id)
    return found


def _load(root: Path) -> list[str]:
    path = root / BASELINE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in data.get("claims", [])]


def problems(root: Path = ROOT) -> list[str]:
    path = root / BASELINE
    if not path.exists():
        return [f"нет {BASELINE.as_posix()}: базовый список самоссылочных утверждений не зафиксирован"]
    current = set(claims(root))
    baseline = set(_load(root))
    out: list[str] = []
    for claim_id in sorted(current - baseline):
        out.append(f"{claim_id}: самоссылочное утверждение (доказательство — research/*.md); "
                   f"нужен evidence/ и команда verify")
    for claim_id in sorted(baseline - current):
        out.append(f"{claim_id}: в базе, но уже не самоссылочное — убрать из базы (она сжимается)")
    return out


def write_baseline(root: Path = ROOT) -> int:
    current = claims(root)
    path = root / BASELINE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "note": ("Утверждения, подтверждённые собственной прозой на 31.10.2026. Список только "
                 "убывает: новый случай валит гейт, устаревшая запись тоже. Замена — "
                 "evidence/ + `python bin/evidence.py verify <id>`."),
        "count": len(current),
        "claims": current,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"записано: {path.as_posix()} ({len(current)} утверждений)")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if "--baseline" in argv:
        return write_baseline()
    current = claims()
    baseline = set(_load(ROOT))
    print(f"самоссылочных сейчас: {len(current)}, в базе: {len(baseline)}")
    for claim_id in current:
        mark = " " if claim_id in baseline else "+"
        print(f"  {mark} {claim_id}")
    issues = problems()
    for issue in issues:
        print(f"  [!] {issue}")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
