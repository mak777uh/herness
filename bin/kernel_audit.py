"""kernel_audit — проверка, какие стены в ядре есть, а каких нет.

Стены — это не договоры. Ядро ничего не обещает: оно просто не пускает.
Здесь перечислено, что должно быть включено в конфиге, и почему.

    python bin/kernel_audit.py                    # проверить все конфиги
    python bin/kernel_audit.py config-6.18.60-net # один конфиг
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "core-rs" / "kernel"

# Стены: имя опции, ожидаемое значение, зачем.
# Три исхода: есть (ok), нет (missing), не проверялось (unknown).
WALLS = [
    # изоляция
    ("SECURITY_LANDLOCK", "y", "ограничение файлового доступа для процесса"),
    ("SECCOMP", "y", "фильтр системных вызовов"),
    ("CGROUPS", "y", "лимиты памяти и CPU"),
    ("NAMESPACES", "y", "пространства имён"),
    ("USER_NS", "y", "пространства пользователей"),
    # защита памяти
    ("STACKPROTECTOR_STRONG", "y", "канарейки в стеке"),
    ("X86_SMEP", "y", "запрет исполнения в страницах данных"),
    ("X86_SMAP", "y", "запрет доступа к пространству пользователя из ядра"),
    ("PAGE_TABLE_ISOLATION", "y", "изоляция таблиц страниц (Meltdown)"),
    ("STRICT_KERNEL_RWX", "y", "ядро не пишет в исполняемые страницы"),
    ("HARDENED_USERCOPY", "y", "проверка копирования из/в пользователя"),
    ("FORTIFY_SOURCE", "y", "проверки переполнений на этапе сборки"),
    # рандомизация
    ("RANDOMIZE_BASE", "y", "случайный адрес ядра (KASLR)"),
    ("SLAB_FREELIST_RANDOM", "y", "случайный порядок в куче"),
    ("SLAB_FREELIST_HARDENED", "y", "защита связей в куче"),
    ("RANDOM_KMALLOC_CACHES", "y", "разные кэши для разных размеров"),
    ("SHUFFLE_PAGE_ALLOCATOR", "y", "случайный порядок страниц"),
    # обнуление
    ("INIT_ON_ALLOC_DEFAULT_ON", "y", "память обнуляется при выделении"),
    ("INIT_ON_FREE_DEFAULT_ON", "y", "память обнуляется при освобождении"),
    # прочее
    ("BUG_ON_DATA_CORRUPTION", "y", "падение при повреждении структур"),
    ("DEBUG_LIST", "y", "проверка связных списков"),
    ("STATIC_USERMODEHELPER", "y", "нельзя подменить помощника в пространстве пользователя"),
    ("SECURITY_DMESG_RESTRICT", "y", "журнал ядра закрыт для пользователя"),
    ("SECURITY_PERF_EVENTS_RESTRICT", "y", "счётчики производительности закрыты"),
    ("X86_KERNEL_IBT", "y", "защита непрямых переходов"),
    ("LOCK_DOWN_KERNEL_FORCE", "integrity", "перевод ядра в режим ограничений"),
    # митигации процессора
    ("MITIGATION_RETPOLINE", "y", "защита от Spectre v2"),
    ("CPU_MITIGATIONS", "y", "митигации процессора включены"),
    # модули не нужны
    ("MODULES", "n", "модулей нет — меньше поверхности"),
]


def read_config(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.replace("CONFIG_", "", 1)] = value.strip('"')
    return values


def audit(path: Path) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    values = read_config(path)
    ok, missing = [], []
    for name, expected, why in WALLS:
        actual = values.get(name)
        if actual == expected:
            ok.append((name, why, actual))
        else:
            missing.append((name, why, actual or "нет"))
    return ok, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="аудит стен ядра")
    parser.add_argument("config", nargs="?", help="имя конфига")
    parser.add_argument("--out", default="research/outputs/kernel-audit.txt")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    configs = [KERNEL / args.config] if args.config else sorted(KERNEL.glob("config-*"))
    lines = ["# Стены ядра: что есть, чего нет", ""]
    total_missing = 0
    for path in configs:
        if not path.exists():
            lines.append(f"{path.name}: файла нет")
            continue
        ok, missing = audit(path)
        total_missing += len(missing)
        lines.append(f"## {path.name}: стен {len(ok)} из {len(WALLS)}")
        lines.append("")
        if missing:
            lines.append("| нет стены | зачем нужна | сейчас |")
            lines.append("|---|---|---|")
            for name, why, actual in missing:
                lines.append(f"| `{name}` | {why} | {actual} |")
            lines.append("")
        else:
            lines.append("все стены на месте")
            lines.append("")
    lines.append(f"всего недостающих стен: {total_missing}")
    text = "\n".join(lines) + "\n"
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
