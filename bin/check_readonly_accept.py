"""Отрицательный контроль этапа 1.6 (READONLY-ACCEPT-R1): приёмка не чинит улику на месте.

Что проверяется:
  1. плечо A (текущая команда .ps1: e2fsck -fy ОРИГИНАЛ, mount rw) ОБЯЗАНО изменить SHA-256
     оригинала — иначе метрика не различает плечи и это UNKNOWN, не PASS;
  2. плечо B (bin/extract_journal.py: копия + e2fsck копии) ОБЯЗАНО сохранить SHA-256 оригинала
     и прочитать журнал без искажения;
  3. оба скрипта (accept-run.ps1, crash-resume.ps1) делегируют извлечение helper-у и не содержат
     e2fsck на оригинале. До фикса скриптов — красный, после — зелёный.

Образы disposable (во временном каталоге), настоящий acc.img не трогается.

    python bin/check_readonly_accept.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
from extract_journal import ROOT as _R, sha256, wsl, wsl_path  # noqa: E402

PAYLOAD = "HSJ1-readonly-accept-test-payload-1234567890"


def make_image(path: Path) -> bool:
    wp = wsl_path(path)
    script = f"""rm -f '{wp}'
dd if=/dev/zero of='{wp}' bs=1M count=16 status=none
mkfs.ext4 -q -F '{wp}'
mkdir -p /tmp/ro-make
mount -o loop '{wp}' /tmp/ro-make
printf '%s' '{PAYLOAD}' > /tmp/ro-make/hs-journal.bin
umount /tmp/ro-make
rmdir /tmp/ro-make
echo сделано
"""
    code, _ = wsl(script)
    return code == 0 and path.exists()


def arm_old(image: Path) -> bool:
    """Плечо A: точная копия текущей команды из accept-run.ps1 / crash-resume.ps1."""
    wp = wsl_path(image)
    before = sha256(image)
    script = f"""rm -rf /tmp/ro-old && mkdir -p /tmp/ro-old
e2fsck -fy '{wp}' >/dev/null 2>&1
mount -o loop '{wp}' /tmp/ro-old
cp /tmp/ro-old/hs-journal.bin /tmp/ro-old/journal.bin
umount /tmp/ro-old
rm -rf /tmp/ro-old
echo вынуто
"""
    wsl(script)
    after = sha256(image)
    return before != after  # True = оригинал изменён (дефект воспроизводится)


def arm_helper(image: Path, out: Path) -> bool:
    """Плечо B: helper извлечения с копии."""
    before = sha256(image)
    result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "extract_journal.py"), str(image), str(out)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    after = sha256(image)
    payload_ok = out.exists() and out.read_text(encoding="utf-8", errors="replace") == PAYLOAD
    return result.returncode == 0 and before == after and payload_ok


def static_problems() -> list[str]:
    problems = []
    for name in ("accept-run.ps1", "crash-resume.ps1"):
        text = (ROOT / "core-rs" / name).read_text(encoding="utf-8")
        if "extract_journal" not in text:
            problems.append(f"{name}: не делегирует извлечение bin/extract_journal.py")
        if "e2fsck" in text:
            problems.append(f"{name}: содержит e2fsck (чинит оригинал на месте)")
    return problems


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        img_a = tmp_path / "ro-a.img"
        img_b = tmp_path / "ro-b.img"
        out = tmp_path / "journal.bin"
        if not make_image(img_a) or not make_image(img_b):
            print("[UNKNOWN] не удалось создать disposable-образ (нет WSL/mkfs?)")
            return 2
        mutated = arm_old(img_a)
        if not mutated:
            print("[UNKNOWN] плечо A не изменило хеш оригинала — метрика не различает плечи")
            return 2
        helper_ok = arm_helper(img_b, out)

    problems = static_problems()
    checks = [
        ("плечо A: старая команда меняет оригинал (дефект воспроизводится)", mutated),
        ("плечо B: helper сохраняет оригинал и читает журнал без искажения", helper_ok),
        ("скрипты делегируют helper-у, без e2fsck на оригинале", not problems),
    ]
    for title, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {title}")
    for problem in problems:
        print("   ", problem)
    print()
    bad = sum(1 for _, ok in checks if not ok)
    if bad:
        print(f"[FAIL] провалено: {bad} из {len(checks)}")
        return 1
    print(f"[ok] пройдено: {len(checks)} из {len(checks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())