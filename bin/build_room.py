"""build_room — собрать образ комнаты по манифесту и проверить его на совпадение с репозиторием.

Зачем: дефект F-0035. Образ собирался руками и отстал от репозитория; задача стала невыполнимой,
а выглядело это как провал модели. Здесь сборка описана манифестом (`lab/room.json`), и после
сборки проверяется: каждый источник есть в образе, число файлов совпадает, а запрещённые каталоги
(выходы оценщика) отсутствуют.

    python bin/build_room.py --build     # пересобрать образ
    python bin/build_room.py --check     # только проверить текущий образ
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, ".")

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "lab" / "room.json"


def load() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def wsl(script: str) -> tuple[int, str]:
    result = subprocess.run(
        ["wsl", "-e", "bash", "-lc", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def build(manifest: dict) -> int:
    image = manifest["image"]
    size = manifest.get("size_mb", 160)
    copies = manifest["copy"]
    script = [
        f"cd /mnt/c/111/herness && rm -f {image} &&",
        f"dd if=/dev/zero of={image} bs=1M count={size} status=none &&",
        f"mkfs.ext4 -q -F {image} && mkdir -p /tmp/room && mount -o loop {image} /tmp/room &&",
    ]
    for source, destination in copies.items():
        parent = str(Path(destination).parent)
        if parent not in (".", ""):
            script.append(f"mkdir -p /tmp/room/{parent} &&")
        script.append(f"cp -r {source} /tmp/room/{destination} &&")
    script.append("sync && umount /tmp/room && echo собрано")
    code, out = wsl(" ".join(script))
    print(out.strip().splitlines()[-1] if out.strip() else "")
    return 0 if code == 0 else 1


def check(manifest: dict) -> int:
    image = manifest["image"]
    script = (
        f"cd /mnt/c/111/herness && mkdir -p /tmp/room && mount -o loop {image} /tmp/room && "
        "cd /tmp/room && find . -type f | sed 's|^\\./||' | sort | head -5000 && "
        "echo '---конец---' && cd / && umount /tmp/room"
    )
    code, out = wsl(script)
    if code != 0 and "---конец---" not in out:
        print("образ не смонтировался:", out.strip()[-400:])
        return 1
    inside = {line.strip() for line in out.splitlines() if line.strip() and not line.startswith("---")}
    problems: list[str] = []

    for source_in_image in manifest["verify"]:
        if not any(path == source_in_image or path.startswith(source_in_image.rstrip("/") + "/") for path in inside):
            problems.append(f"в образе нет источника {source_in_image}")

    for forbidden in manifest.get("forbidden", []):
        if any(path == forbidden or path.startswith(forbidden.rstrip("/") + "/") for path in inside):
            problems.append(f"в образе запрещённый каталог {forbidden}")

    print(f"файлов в образе: {len(inside)}")
    for source, destination in manifest["copy"].items():
        host = ROOT / source
        if host.is_file():
            count_host = 1
        elif host.is_dir():
            count_host = sum(1 for _ in host.rglob("*") if _.is_file())
        else:
            problems.append(f"источника нет в репозитории: {source}")
            continue
        if host.is_file():
            count_image = 1 if destination in inside else 0
        else:
            prefix = destination.rstrip("/") + "/"
            count_image = sum(1 for path in inside if path.startswith(prefix))
        print(f"  {source:24} в репозитории {count_host:>4}  в образе {count_image:>4}")
        if count_image < count_host:
            problems.append(f"{source}: в образе меньше файлов ({count_image} против {count_host})")

    if problems:
        print("ПРОБЛЕМЫ:")
        for problem in problems:
            print("  -", problem)
        return 1
    print("образ совпадает с манифестом")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="сборка и проверка комнаты")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    manifest = load()
    if args.build:
        code = build(manifest)
        if code != 0:
            return code
    if args.build or args.check:
        return check(manifest)
    print("укажи --build или --check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
