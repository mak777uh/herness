"""prune_probes — удалить проверки-разведки, которые больше не нужны.

Шаг 2 плана: сократить проверки. Из книги: «улучшение — чаще удаление».
Удаляем только то, что:
  - не входит в гейты;
  - было разведкой (probe_api, models_probe, or_probe...) и уже дало результат;
  - не используется другими скриптами.

    python bin/prune_probes.py --check
    python bin/prune_probes.py --run
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin"

# Разведки, которые уже дали результат и больше не нужны.
# Каждая: почему удаляем.
PRUNE = {
    "_browser_probe.py": "разведка браузера, результат в research/",
    "_recheck.py": "разовая перепроверка, результат в research/",
    "factcheck_h2.py": "разовая проверка фактов, результат в research/",
    "factcheck2_h2.py": "разовая проверка фактов, результат в research/",
    "models_probe.py": "разведка моделей, результат в research/",
    "models_probe2.py": "разведка моделей, результат в research/",
    "or_probe.py": "разведка OpenRouter, результат в research/",
    "or_probe2.py": "разведка OpenRouter, результат в research/",
    "probe_api.py": "разведка API, результат в research/",
    "probe_commandcode.py": "разведка, результат в research/",
    "probe_extension.py": "разведка расширений, результат в research/",
    "probe_free_models.py": "разведка бесплатных моделей, результат в research/",
    "probe_harness.py": "разведка харнессов, результат в research/",
    "probe_harness2.py": "разведка харнессов, результат в research/",
    "live_probe.py": "разведка живого прогона, результат в research/",
    "self_audit.py": "разовый самоаудит, результат в research/",
    "scope_audit.py": "разовый аудит области, результат в research/",
    "loop_audit.py": "разовый аудит цикла, результат в research/",
    "audit_facts.py": "сухие факты, заменено repo_analysis.py",
    "audit_harness.py": "внешний взгляд, результат в research/",
}


def used_elsewhere(name: str) -> bool:
    """Упоминается ли файл в других скриптах или гейтах.

    Себя и списки удаления не считаем: иначе ни один файл не удалится.
    """
    skip = {name, "prune_probes.py", "probes_inventory.py"}
    for path in BIN.glob("*.py"):
        if path.name in skip:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if name in text:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="удалить разведки")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    removable = []
    kept = []
    for name, why in PRUNE.items():
        path = BIN / name
        if not path.exists():
            continue
        if used_elsewhere(name):
            kept.append((name, "используется в других скриптах"))
        else:
            removable.append((name, why))

    print(f"можно удалить: {len(removable)}")
    for name, why in removable:
        print(f"  {name}: {why}")
    print(f"оставлено: {len(kept)}")
    for name, why in kept:
        print(f"  {name}: {why}")

    if args.check:
        return 0
    if args.run:
        for name, _ in removable:
            (BIN / name).unlink()
        print(f"\nудалено: {len(removable)}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
