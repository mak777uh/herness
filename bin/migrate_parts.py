"""migrate_parts — перенести репозитории в herness как атомарные ячейки.

Что делает:
  1. клонирует каждый репозиторий с GitHub в herness/parts/<имя>;
  2. сохраняет историю (это клон, а не копия файлов);
  3. пишет манифест: откуда, какой коммит, какой хеш;
  4. не удаляет ничего в исходных местах.

    python bin/migrate_parts.py --plan     # показать, что будет сделано
    python bin/migrate_parts.py --run      # выполнить
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "parts"
MANIFEST = PARTS / "MANIFEST.json"

# Пять репозиториев по списку владельца. Морфогенез не трогаем.
REPOS = [
    ("flowguard-spec", "https://github.com/mak777uh/flowguard-spec.git"),
    ("lexspec", "https://github.com/mak777uh/lexspec.git"),
    ("VecDHT", "https://github.com/mak777uh/VecDHT.git"),
    ("nomos", "https://github.com/mak777uh/nomos.git"),
]


def run(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def plan() -> int:
    print("что будет сделано:")
    for name, url in REPOS:
        target = PARTS / name
        state = "уже есть" if target.exists() else "клонировать"
        print(f"  {name:20} {state:12} <- {url}")
    print(f"\nманифест: {MANIFEST.relative_to(ROOT)}")
    print("исходные каталоги НЕ удаляются")
    return 0


def migrate() -> int:
    PARTS.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, url in REPOS:
        target = PARTS / name
        if target.exists():
            code, _ = run(["git", "-C", str(target), "rev-parse", "HEAD"])
            if code == 0:
                print(f"{name}: уже склонирован, пропускаю")
            else:
                print(f"{name}: каталог есть, но не git — пропускаю (разобрать вручную)")
                continue
        else:
            print(f"{name}: клонирую...", flush=True)
            code, text = run(["git", "clone", "--quiet", url, str(target)])
            if code != 0:
                print(f"{name}: ОШИБКА клонирования: {text[-300:]}")
                continue
        code, commit = run(["git", "-C", str(target), "rev-parse", "HEAD"])
        code2, subject = run(["git", "-C", str(target), "log", "-1", "--format=%s"])
        code3, count = run(["git", "-C", str(target), "rev-list", "--count", "HEAD"])
        entries.append({
            "name": name,
            "url": url,
            "commit": commit.strip() if code == 0 else "",
            "subject": subject.strip()[:100] if code2 == 0 else "",
            "commits": int(count.strip()) if code3 == 0 and count.strip().isdigit() else 0,
        })
        print(f"{name}: готово, коммит {commit.strip()[:8]}, коммитов {count.strip()}")

    data = {
        "version": 1,
        "principle": "части — атомарные независимые ячейки; herness связывает их, но не растворяет",
        "migrated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "not_migrated": ["- (Morphogenesis) — владелец объяснит позже"],
        "parts": entries,
    }
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nманифест записан: {MANIFEST.relative_to(ROOT)}; частей {len(entries)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="перенос репозиториев в herness/parts")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.plan:
        return plan()
    if args.run:
        return migrate()
    print("укажи --plan или --run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
