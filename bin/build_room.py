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
import hashlib
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
    """Собрать образ через staging и переименование (F-ROOM-5).

    Раньше сборка шла прямо в целевой файл: `rm -f share.img` и `dd` в него же.
    Прерванная сборка оставляла полуразрушенный образ, а `--check` этого не
    видел — он считает файлы. Теперь новый образ пишется рядом
    (`share.img.new`) и подменяет старый только после успешной сборки:
    либо прежний рабочий образ, либо новый целый, третьего нет.
    """
    image = manifest["image"]
    staging = f"{image}.new"
    size = manifest.get("size_mb", 160)
    copies = manifest["copy"]
    script = [
        f"cd /mnt/c/111/herness && rm -f {staging} &&",
        f"dd if=/dev/zero of={staging} bs=1M count={size} status=none &&",
        f"mkfs.ext4 -q -F {staging} && mkdir -p /tmp/room && mount -o loop {staging} /tmp/room &&",
    ]
    for source, destination in copies.items():
        parent = str(Path(destination).parent)
        if parent not in (".", ""):
            script.append(f"mkdir -p /tmp/room/{parent} &&")
        script.append(f"cp -r {source} /tmp/room/{destination} &&")
    # Подмена только после того, как staging целиком собран и отмонтирован.
    script.append(f"sync && umount /tmp/room && mv -f {staging} {image} && echo собрано")
    code, out = wsl(" ".join(script))
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    print(tail)
    if code != 0:
        # Неудачный staging не должен остаться мусором рядом с образом.
        wsl(f"cd /mnt/c/111/herness && rm -f {staging} && umount /tmp/room 2>/dev/null; true")
        print("сборка не удалась — прежний образ оставлен как был")
    return 0 if code == 0 else 1


def check(manifest: dict) -> int:
    """Проверить образ: наличие источников, запрещённые каталоги и СОДЕРЖИМОЕ.

    F-ROOM-6 (08.11.2026). Раньше проверялось только число файлов: подменённый
    файл при том же количестве проходил, и «образ совпадает» было неправдой —
    тихий пропуск, то есть UNKNOWN, выданный за PASS. Теперь для каждого
    источника считается SHA-256 на хосте и в образе, и сверяется.

    Заодно убран `head -5000`: на большом образе он молча обрезал список и
    давал ложное «в образе меньше файлов».
    """
    image = manifest["image"]
    script = (
        f"cd /mnt/c/111/herness && mkdir -p /tmp/room && mount -o loop {image} /tmp/room && "
        "cd /tmp/room && find . -type f | sed 's|^\\./||' | sort && "
        "echo '---файлы-конец---' && "
        "find . -type f -print0 | sort -z | xargs -0 -r sha256sum && "
        "echo '---хеши-конец---' && cd / && umount /tmp/room"
    )
    code, out = wsl(script)
    if "---хеши-конец---" not in out:
        print("образ не смонтировался или хеши не снялись:", out.strip()[-400:])
        return 1

    files_part, rest = out.split("---файлы-конец---", 1)
    hashes_part = rest.split("---хеши-конец---", 1)[0]
    inside = {line.strip() for line in files_part.splitlines() if line.strip()}
    # sha256sum печатает "<хеш>  ./путь"
    image_hashes: dict[str, str] = {}
    for line in hashes_part.splitlines():
        line = line.strip()
        if not line or "  " not in line:
            continue
        digest, path = line.split("  ", 1)
        image_hashes[path.strip().lstrip("./")] = digest

    problems: list[str] = []

    for source_in_image in manifest["verify"]:
        if not any(path == source_in_image or path.startswith(source_in_image.rstrip("/") + "/") for path in inside):
            problems.append(f"в образе нет источника {source_in_image}")

    for forbidden in manifest.get("forbidden", []):
        if any(path == forbidden or path.startswith(forbidden.rstrip("/") + "/") for path in inside):
            problems.append(f"в образе запрещённый каталог {forbidden}")

    print(f"файлов в образе: {len(inside)}, хешей снято: {len(image_hashes)}")
    for source, destination in manifest["copy"].items():
        host = ROOT / source
        if not host.exists():
            problems.append(f"источника нет в репозитории: {source}")
            continue
        if host.is_file():
            pairs = [(destination, host)]
        else:
            pairs = []
            for path in sorted(host.rglob("*")):
                if path.is_file():
                    rel = path.relative_to(host).as_posix()
                    pairs.append((f"{destination.rstrip('/')}/{rel}", path))

        mismatched = 0
        missing = 0
        for image_path, host_path in pairs:
            if image_path not in image_hashes:
                missing += 1
                continue
            host_digest = hashlib.sha256(host_path.read_bytes()).hexdigest()
            if host_digest != image_hashes[image_path]:
                mismatched += 1
        print(f"  {source:24} файлов {len(pairs):>4}  нет в образе {missing:>3}  "
              f"разошлись по содержимому {mismatched:>3}")
        if missing:
            problems.append(f"{source}: в образе нет файлов ({missing} из {len(pairs)})")
        if mismatched:
            problems.append(f"{source}: содержимое расходится ({mismatched} из {len(pairs)})")

    if problems:
        print("ПРОБЛЕМЫ:")
        for problem in problems:
            print("  -", problem)
        return 1
    print("образ совпадает с манифестом по составу и содержимому")
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
