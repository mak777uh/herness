"""Извлечение журнала из образа комнаты БЕЗ мутации оригинала (этап 1.6, READONLY-ACCEPT-R1).

Приёмка не должна менять свидетельство, которое проверяет (ADR-0049). Прежняя процедура
в accept-run.ps1 и crash-resume.ps1 звала `e2fsck -fy` на ОРИГИНАЛЕ (код возврата выброшен)
и монтировала его `mount -o loop` без `ro` — это чинило улику на месте. Замер 11.11.2026:
e2fsck -fy меняет SHA-256 даже чистого образа.

Теперь:
  1. SHA-256 оригинала ДО;
  2. копия образа в /tmp; e2fsck -fy и монтирование — ТОЛЬКО копии (rc e2fsck проверен);
  3. журнал копируется на хост;
  4. копия удаляется; SHA-256 оригинала ПОСЛЕ; не совпало — FAIL (улика изменена).

e2fsck на копии накатывает журнал (в отличие от ro,noload, который читает устаревшее
закоммиченное состояние) — поэтому dirty-образ после жёсткого убийства QEMU читается верно.

    python bin/extract_journal.py <image> <out_journal>

Коды: 0 — журнал вынут, оригинал не изменён; 1 — оригинал изменён (FAIL);
2 — извлечь не удалось (нет образа/WSL/journal, e2fsck не чинит копию).
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WSL_ROOT = "/mnt/c/111/herness"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(ROOT)
    except ValueError:
        drive = resolved.drive.lower().rstrip(":")
        return f"/mnt/{drive}/" + Path(*resolved.parts[1:]).as_posix()
    return f"{WSL_ROOT}/{rel.as_posix()}"


def wsl(script: str) -> tuple[int, str]:
    result = subprocess.run(
        ["wsl", "-e", "bash", "-lc", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def extract(image: Path, out: Path) -> int:
    if not image.exists():
        print(f"ПРИЁМКА: нет образа {image} — это UNKNOWN, не PASS")
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    before = sha256(image)
    img_wsl = wsl_path(image)
    out_wsl = wsl_path(out)
    # Копия в /tmp (WSL). Оригинал не открывается на запись ни на одном шаге.
    script = f"""cd {WSL_ROOT}
rm -rf /tmp/acc-ro
mkdir -p /tmp/acc-ro/mnt
cp '{img_wsl}' /tmp/acc-ro/copy.img || exit 1
e2fsck -fy /tmp/acc-ro/copy.img >/dev/null 2>&1
rc=$?
if [ $rc -ge 4 ]; then echo "e2fsck копии: rc=$rc (не чинится)"; exit 1; fi
mount -o loop /tmp/acc-ro/copy.img /tmp/acc-ro/mnt || exit 1
cp /tmp/acc-ro/mnt/hs-journal.bin '{out_wsl}' || {{ umount /tmp/acc-ro/mnt; exit 1; }}
umount /tmp/acc-ro/mnt
rm -rf /tmp/acc-ro
echo вынуто
"""
    code, output = wsl(script)
    if code != 0 or not out.exists():
        print("ПРИЁМКА: не удалось вынуть журнал из копии образа")
        print(output.strip()[-400:])
        return 2
    after = sha256(image)
    if before != after:
        print("ПРИЁМКА: FAIL — оригинальный образ изменён приёмкой (улика повреждена)")
        print(f"  до:    {before}")
        print(f"  после: {after}")
        return 1
    print(f"журнал вынут с копии: {out.name} ({out.stat().st_size} байт)")
    print(f"оригинал не изменён (SHA-256 {before[:16]}… до == после)")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python bin/extract_journal.py <image> <out_journal>")
        return 2
    image = Path(argv[0])
    out = Path(argv[1])
    if not image.is_absolute():
        image = ROOT / image
    if not out.is_absolute():
        out = ROOT / out
    return extract(image, out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))