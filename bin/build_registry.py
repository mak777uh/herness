"""build_registry — реестр инструментов: append-only, с хешем среды и происхождением.

Эксперимент E1 плана P33. Запись неизменяема: правка — новая запись со ссылкой на предыдущую.
Агент в реестр не пишет: файл принадлежит хосту.

    python bin/build_registry.py --build     # собрать из текущего набора инструментов
    python bin/build_registry.py --check     # проверить структуру
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "lab" / "tools" / "registry.jsonl"
ROOM = ROOT / "lab" / "room.json"

# Контракты существующих инструментов: что делает, что возвращает.
TOOLS = {
    "search": {
        "contract": "ищет подстроку в файлах каталога; возвращает совпадения, сводку по файлам и строку «разные (N)»",
        "returns": "текст: найдено K в M файлах, файлы с числом совпадений, до 40 строк, разные варианты",
        "permissions": ["fs:read"],
    },
    "list": {
        "contract": "перечисляет содержимое каталога",
        "returns": "каталоги первыми с косой чертой, затем файлы с размерами",
        "permissions": ["fs:read"],
    },
    "read": {
        "contract": "читает файл с номерами строк, начиная с указанной",
        "returns": "до 8 КиБ текста с номерами строк",
        "permissions": ["fs:read"],
    },
    "write": {
        "contract": "пишет файл внутри рабочего каталога",
        "returns": "подтверждение записи",
        "permissions": ["fs:write"],
    },
    "seal": {
        "contract": "запечатывает файл: sha256 канонического префикса до маркера «## Seal»",
        "returns": "отпечаток и путь sidecar",
        "permissions": ["fs:read", "fs:write"],
    },
    "netprobe": {
        "contract": "проверяет доступность адреса из комнаты",
        "returns": "код ответа или ошибку соединения",
        "permissions": ["net:probe"],
    },
}


def environment_hash() -> str:
    """Хеш среды: манифест комнаты. Меняется образ — меняется хеш."""
    if not ROOM.exists():
        return "нет манифеста"
    data = json.loads(ROOM.read_text(encoding="utf-8"))
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


def entry(name: str, spec: dict, version: int = 1, previous: str | None = None) -> dict:
    return {
        "id": name,
        "version": version,
        "contract": spec["contract"],
        "returns": spec["returns"],
        "permissions": spec["permissions"],
        "environment": environment_hash(),
        "provenance": "встроен в цикл, core-rs/src/loopmod.rs",
        "status": "active",
        "previous": previous,
        "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def build() -> int:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry(name, spec), ensure_ascii=False) for name, spec in TOOLS.items()]
    REGISTRY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"записано: {REGISTRY.relative_to(ROOT)}; инструментов {len(lines)}; среда {environment_hash()}")
    return 0


def problems(rows: list[dict]) -> list[str]:
    out = []
    seen = set()
    for index, row in enumerate(rows, 1):
        for field in ("id", "version", "contract", "returns", "permissions", "environment", "provenance", "status"):
            if not row.get(field):
                out.append(f"строка {index}: нет поля {field}")
        key = (row.get("id"), row.get("version"))
        if key in seen:
            out.append(f"строка {index}: повтор {key}")
        seen.add(key)
        if row.get("environment") == "нет манифеста":
            out.append(f"строка {index}: хеш среды не вычислен")
    return out


def check() -> int:
    if not REGISTRY.exists():
        print("нет реестра: собрать bin/build_registry.py --build")
        return 1
    rows = [json.loads(line) for line in REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    found = problems(rows)
    if found:
        print("ПРОБЛЕМЫ:")
        for item in found:
            print("  -", item)
        return 1
    print(f"[ok] реестр: {len(rows)} записей, у всех есть контракт, среда и происхождение")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="реестр инструментов")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.build:
        return build()
    if args.check:
        return check()
    print("укажи --build или --check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
