"""local_cleanup — удалить локальные копии репозиториев, оставив нужные.

ОСТАВИТЬ:
  C:\\111\\herness            — сам харнесс
  C:\\111\\system\\repos\\morph — морфогенез
  C:\\111\\proofs-registry     — только локально, на GitHub нет (владелец: не трогать)
  cicada3301                  — локальная копия, если есть

УДАЛИТЬ: остальные наши репозитории и рабочие копии.

Сначала --plan (показать), потом --run (удалить). Удаление необратимо.

    python bin/local_cleanup.py --plan
    python bin/local_cleanup.py --run
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "outputs" / "local-cleanup.txt"

KEEP_PATHS = {
    "C:/111/herness",
    "C:/111/system/repos/morph",
    "C:/111/proofs-registry",
}

# Наши репозитории и рабочие копии, которые надо удалить.
DROP_PATHS = [
    "C:/111/spec",                    # flowguard-spec (есть в parts)
    "C:/111/lexspec-review",          # lexspec (есть в parts)
    "C:/111/VecDHT",                  # VecDHT (есть в parts)
    "C:/111/_vec",                    # рабочая копия ветки VecDHT
    "C:/111/work/nomos",              # nomos (есть в parts)
    "C:/111/work/flowguard",          # дубликат spec
    "C:/111/work/harness",            # дубликат herness
    "C:/111/cases",
    "C:/111/work/rocketpool-invariants",
    "C:/111/work/verified-cells-cairo",
    "C:/111/work/verified_cells_cairo",
    "C:/111/work/sealed-invoice",
    "C:/111/pharos-agent-arena",
    "C:/111/lean-agent-verify",
    "C:/111/modelproof",
    "C:/111/gh-audit",
    "C:/111/projects",
    "C:/111/work",
    "C:/111/agents",
    "C:/111/research",
    "C:/111/lab",
    "C:/111/system",
    "C:/111/env",
    "C:/111/vuln-work",
    "C:/111/treasury",
    "C:/111/stealth",
    "C:/111/incoming",
    "C:/111/poidh",
    "C:/111/probe-tmp",
    "C:/111/bench",
    "C:/111/browser-mcp",
    "C:/111/chat-research",
    "C:/111/chrome-cdp",
    "C:/111/findings",
    "C:/111/grants",
    "C:/111/hashn",
    "C:/111/inbox",
    "C:/111/proposals",
    "C:/111/reports",
    "C:/111/tmp",
    "C:/111/disk_audit",
    "C:/111/audit",
    "C:/111/applications",
    "C:/111/agntn_raw",
    "C:/111/node_modules",
    "C:/111/__pycache__",
    "C:/111/_attack",
    "C:/111/_attack2",
    "C:/111/_attack3",
    "C:/111/_claims",
    "C:/111/_dsh_asar",
    "C:/111/_dshhome2",
    "C:/111/_dshhome3",
    "C:/111/_gos1_probe",
    "C:/111/_lexprobe",
    "C:/111/_lexprobe2",
    "C:/111/_lexprobe3",
    "C:/111/_lexprobe4",
    "C:/111/_lexprobe5",
    "C:/111/_m7",
    "C:/111/_m7v2",
    "C:/111/_m7v3",
    "C:/111/_pagila",
    "C:/111/_pg",
    "C:/111/_profile",
    "C:/111/_schemas",
    "C:/111/_xatt",
    "C:/111/_xatt2",
    "C:/111/.dsh-plugins",
    "C:/111/.sentry-native",
]


def size_of(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="очистка локальных копий")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    lines = ["# Очистка локальных копий", ""]
    lines.append("## Оставить")
    for path in sorted(KEEP_PATHS):
        exists = "есть" if Path(path).exists() else "нет"
        lines.append(f"- {path} ({exists})")
    lines.append("")

    existing = [(p, Path(p)) for p in DROP_PATHS if Path(p).exists()]
    total = sum(size_of(path) for _, path in existing)
    lines.append(f"## Удалить: {len(existing)} каталогов, {total / (1024 ** 3):.1f} ГБ")
    for raw, path in existing:
        lines.append(f"- {raw} ({size_of(path) / (1024 ** 2):.0f} МБ)")
    lines.append("")

    if args.plan:
        lines.append("это план; ничего не удалено")
        text = "\n".join(lines) + "\n"
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
        print(text)
        return 0

    if args.run:
        removed, failed = [], []
        for raw, path in existing:
            try:
                shutil.rmtree(path)
                removed.append(raw)
                print(f"удалён: {raw}", flush=True)
            except OSError as error:
                failed.append(f"{raw}: {error}")
                print(f"ОШИБКА {raw}: {error}", flush=True)
        lines.append(f"удалено: {len(removed)}")
        lines.append(f"ошибок: {len(failed)}")
        for item in failed:
            lines.append(f"  {item}")
        text = "\n".join(lines) + "\n"
        OUT.write_text(text, encoding="utf-8")
        print(text)
        return 0 if not failed else 1

    print("укажи --plan или --run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
