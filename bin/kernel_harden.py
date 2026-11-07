"""kernel_harden — собрать конфиг с настоящими стенами.

Берёт базовый конфиг (обычно config-6.18.60-net) и включает опции закалки, которых в нём нет.
Каждая опция — стена, а не договор: ядро просто не пускает.

Почему не всё включается: некоторые опции требуют поддержки в архитектуре или ядре. Если опция
не включается, это надо назвать, а не молча пропустить.

    python bin/kernel_harden.py --base config-6.18.60-net --out config-6.18.60-hardened2
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "core-rs" / "kernel"

# Опции, которые надо включить. Значение — то, что должно стоять в конфиге.
ENABLE = {
    # защита памяти
    "STACKPROTECTOR": "y",
    "STACKPROTECTOR_STRONG": "y",
    "X86_SMEP": "y",
    "X86_SMAP": "y",
    "PAGE_TABLE_ISOLATION": "y",
    "RANDOMIZE_KSTACK_OFFSET": "y",
    # рандомизация
    "RANDOMIZE_BASE": "y",
    "SLAB_FREELIST_RANDOM": "y",
    "SLAB_FREELIST_HARDENED": "y",
    "RANDOM_KMALLOC_CACHES": "y",
    # прочее
    "DEBUG_LIST": "y",
    "STATIC_USERMODEHELPER": "y",
    "SECURITY_DMESG_RESTRICT": "y",
    "SECURITY_PERF_EVENTS_RESTRICT": "y",
    "MITIGATION_RETPOLINE": "y",
    "CPU_MITIGATIONS": "y",
    # производительность: обход файлов важнее размера
    "CC_OPTIMIZE_FOR_PERFORMANCE": "y",
}

# Опции, которые надо выключить.
DISABLE = {
    "CC_OPTIMIZE_FOR_SIZE": "n",
    "X86_DISABLED_FEATURE_RETPOLINE": "n",
    "X86_DISABLED_FEATURE_RETPOLINE_LFENCE": "n",
}

# Опции, которые нельзя включить в этой конфигурации, и почему.
# Это не «забыли», а объявленное ограничение.
CANNOT = {
    "LOCK_DOWN_KERNEL_FORCE": "требует CONFIG_SECURITY_LOCKDOWN_LSM; в tinyconfig его нет",
    "MODULES": "модулей нет намеренно: меньше поверхности; включать не нужно",
}


def option_line(name: str, value: str) -> str:
    return f"CONFIG_{name}={value}" if value == "y" else f"# CONFIG_{name} is not set"


def apply(base: Path, out: Path) -> tuple[int, int, list[str]]:
    lines = base.read_text(encoding="utf-8", errors="replace").splitlines()
    enabled = disabled = 0
    seen: set[str] = set()
    result = []
    for line in lines:
        stripped = line.strip()
        matched = None
        if stripped.startswith("CONFIG_") and "=" in stripped:
            matched = stripped.split("=", 1)[0][len("CONFIG_"):]
        elif stripped.startswith("# CONFIG_") and stripped.endswith(" is not set"):
            matched = stripped[len("# CONFIG_"):-len(" is not set")]
        if matched in ENABLE:
            result.append(option_line(matched, ENABLE[matched]))
            seen.add(matched)
            enabled += 1
            continue
        if matched in DISABLE:
            result.append(option_line(matched, DISABLE[matched]))
            seen.add(matched)
            disabled += 1
            continue
        result.append(line)

    for name, value in {**ENABLE, **DISABLE}.items():
        if name not in seen:
            result.append(option_line(name, value))
            if name in ENABLE:
                enabled += 1
            else:
                disabled += 1

    out.write_text("\n".join(result) + "\n", encoding="utf-8")
    return enabled, disabled, sorted(CANNOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="сборка закалённого конфига ядра")
    parser.add_argument("--base", default="config-6.18.60-net")
    parser.add_argument("--out", default="config-6.18.60-hardened2")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    base = KERNEL / args.base
    out = KERNEL / args.out
    if not base.exists():
        print(f"нет базового конфига: {base}", file=sys.stderr)
        return 2
    enabled, disabled, cannot = apply(base, out)
    print(f"записано: {out.relative_to(ROOT)}; включено {enabled}, выключено {disabled}")
    for name in cannot:
        print(f"  не включается: {name} — {CANNOT[name]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
