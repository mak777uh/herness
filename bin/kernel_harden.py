"""kernel_harden — собрать конфиг с настоящими стенами.

Берёт базовый конфиг (обычно config-6.18.60-net) и включает опции закалки, которых в нём нет.
Каждая опция — стена, а не договор: ядро просто не пускает.

    python bin/kernel_harden.py --base config-6.18.60-net --out config-6.18.60-hardened2
"""

from __future__ import annotations

import argparse
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
    "LOCK_DOWN_KERNEL_FORCE_INTEGRITY": "y",
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


def apply(base: Path, out: Path) -> tuple[int, int]:
    lines = base.read_text(encoding="utf-8", errors="replace").splitlines()
    enabled = disabled = 0
    seen: set[str] = set()

    def set_option(name: str, value: str) -> str:
        return f"CONFIG_{name}={value}" if value == "y" else f"# CONFIG_{name} is not set"

    result = []
    for line in lines:
        stripped = line.strip()
        matched = None
        if stripped.startswith("CONFIG_") and "=" in stripped:
            matched = stripped.split("=", 1)[0][len("CONFIG_"):]
        elif stripped.startswith("# CONFIG_") and stripped.endswith(" is not set"):
            matched = stripped[len("# CONFIG_"):-len(" is not set")]
        if matched in ENABLE:
            result.append(set_option(matched, ENABLE[matched]))
            seen.add(matched)
            enabled += 1
            continue
        if matched in DISABLE:
            result.append(set_option(matched, DISABLE[matched]))
            seen.add(matched)
            disabled += 1
            continue
        result.append(line)

    # Опции, которых в базе не было вовсе, — дописываем в конец.
    for name, value in {**ENABLE, **DISABLE}.items():
        if name not in seen:
            result.append(set_option(name, value))
            if name in ENABLE:
                enabled += 1
            else:
                disabled += 1

    out.write_text("\n".join(result) + "\n", encoding="utf-8")
    return enabled, disabled


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
    enabled, disabled = apply(base, out)
    print(f"записано: {out.relative_to(ROOT)}; включено {enabled}, выключено {disabled}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
