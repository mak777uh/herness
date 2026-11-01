"""musique_room — собрать образ комнаты для одной задачи MuSiQue.

Кладёт 20 файлов p01.md … p20.md (по одному на абзац) в корень образа. Индекс файла совпадает с
порядком абзацев в наборе, то есть с тем, как размечена поддержка (`is_supporting`).

    python bin/musique_room.py --index 0 --image core-rs/musique.img
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "lab" / "p27" / "musique" / "tasks.json"
DEV = ROOT / "lab" / "p27" / "musique" / "dev.jsonl"
STAGING = ROOT / "runs" / "musique-staging"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="образ комнаты для задачи MuSiQue")
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--image", default="core-rs/musique.img")
    parser.add_argument("--size-mb", type=int, default=64)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    tasks = json.loads(TASKS.read_text(encoding="utf-8"))["tasks"]
    if not 0 <= args.index < len(tasks):
        print(f"нет задачи с индексом {args.index}", file=sys.stderr)
        return 2
    task = tasks[args.index]
    question_id = task["id"].replace("T-musique-", "")

    row = None
    for line in DEV.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        candidate = json.loads(line)
        if candidate["id"] == question_id:
            row = candidate
            break
    if row is None:
        print(f"нет вопроса {question_id} в dev.jsonl", file=sys.stderr)
        return 2

    if STAGING.exists():
        shutil.rmtree(STAGING, ignore_errors=True)
    STAGING.mkdir(parents=True, exist_ok=True)
    for index, paragraph in enumerate(row["paragraphs"], start=1):
        name = f"p{index:02d}.md"
        body = f"# {paragraph['title']}\n\n{paragraph['paragraph_text'].strip()}\n"
        (STAGING / name).write_text(body, encoding="utf-8")

    image = ROOT / args.image
    if image.exists():
        image.unlink()
    wsl = (
        f"cd /mnt/c/111/herness && rm -f {args.image} && "
        f"dd if=/dev/zero of={args.image} bs=1M count={args.size_mb} status=none && "
        f"mkfs.ext4 -q -F {args.image} && rm -rf /tmp/mq && mkdir -p /tmp/mq && "
        f"mount -o loop {args.image} /tmp/mq && cp runs/musique-staging/* /tmp/mq/ && "
        f"sync && umount /tmp/mq && echo готово"
    )
    result = subprocess.run(["wsl", "-e", "bash", "-lc", wsl], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print(result.stdout[-400:], result.stderr[-400:], file=sys.stderr)
        return 1
    print(f"образ готов: {args.image}; вопрос {question_id}; файлов {len(row['paragraphs'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

