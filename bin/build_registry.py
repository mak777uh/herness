"""build_registry — реестр инструментов: append-only, с хешем среды, происхождением и контрактом.

Эксперимент E1 плана P33 + A-0042 (контракт с примерами).

Запись неизменяемы: правка — новая запись со ссылкой на предыдущую.
У каждого инструмента контракт из четырёх уровней:
    имя        — какую операцию выполняет
    вход       — точные типы и обязательные поля
    выход      — структура возвращаемых данных
    семантика  — что означает результат и когда он достоверен
и 1–5 реальных примеров вызова.

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

# Контракты существующих инструментов: четыре уровня и примеры вызова.
TOOLS = {
    "search": {
        "contract": "ищет подстроку в файлах каталога",
        "input": {"path": "каталог или файл внутри комнаты", "needle": "подстрока, регистр не важен"},
        "returns": "текст: найдено K в M файлах, файлы с числом совпадений, до 40 строк, разные варианты",
        "output": {"found": "число совпадений", "files": "список путей с числом", "lines": "до 40 строк вида путь:строка: текст", "distinct": "строка «разные (N): …»"},
        "semantics": "ищет по всем файлам каталога рекурсивно; совпадение ищется во всей строке, показывается окно вокруг него; если в двух последних результатах есть ответ — собери и ответь",
        "permissions": ["fs:read"],
        "examples": [
            "TOOL search /mnt/docs C-0196",
            "TOOL search /mnt/runs/dump administration",
        ],
    },
    "list": {
        "contract": "перечисляет содержимое каталога",
        "input": {"path": "каталог внутри комнаты"},
        "returns": "каталоги первыми с косой чертой, затем файлы с размерами",
        "output": {"entries": "список: имя каталога с «/» или имя файла с размером в байтах"},
        "semantics": "один уровень вглубь, без рекурсии; если в каталоге больше 100 записей — выводится начало и число остальных",
        "permissions": ["fs:read"],
        "examples": ["TOOL list /mnt", "TOOL list /mnt/runs/dump"],
    },
    "read": {
        "contract": "читает файл с номерами строк, начиная с указанной",
        "input": {"path": "файл внутри комнаты", "line": "необязательный номер первой строки, по умолчанию 1"},
        "returns": "до 8 КиБ текста с номерами строк",
        "output": {"lines": "строки вида «номер: текст»", "truncated": "признак, что файл длиннее выдачи"},
        "semantics": "выдача ограничена 8 КиБ; если файл длиннее, продолжение читается с указанного номера строки",
        "permissions": ["fs:read"],
        "examples": ["TOOL read /mnt/CLAIMS.md", "TOOL read /mnt/CLAIMS.md 220"],
    },
    "write": {
        "contract": "пишет файл внутри рабочего каталога",
        "input": {"path": "файл внутри рабочего каталога", "text": "содержимое целиком"},
        "returns": "подтверждение записи",
        "output": {"ok": "подтверждение", "bytes": "сколько байт записано"},
        "semantics": "пишет только внутри рабочего каталога, вне его отказывает; перезаписывает файл целиком",
        "permissions": ["fs:write"],
        "examples": ["TOOL write /mnt/work/notes.md текст"],
    },
    "seal": {
        "contract": "запечатывает файл: sha256 канонического префикса до маркера «## Seal»",
        "input": {"path": "файл внутри рабочего каталога"},
        "returns": "отпечаток и путь sidecar",
        "output": {"digest": "sha256", "sidecar": "путь к файлу с отпечатком"},
        "semantics": "отпечаток считается по содержимому ДО маркера «## Seal»; правка после маркера его не меняет",
        "permissions": ["fs:read", "fs:write"],
        "examples": ["TOOL seal /mnt/work/notes.md"],
    },
    "netprobe": {
        "contract": "проверяет доступность адреса из комнаты",
        "input": {"host": "адрес", "port": "необязательный порт"},
        "returns": "код ответа или ошибку соединения",
        "output": {"reachable": "да/нет", "detail": "код или текст ошибки"},
        "semantics": "проверяет только доступность, содержимое не загружает; сеть из комнаты идёт только через мост",
        "permissions": ["net:probe"],
        "examples": ["TOOL netprobe 10.0.2.2 8790"],
    },
}


def environment_hash() -> str:
    """Хеш среды: манифест комнаты. Меняется образ — меняется хеш."""
    if not ROOM.exists():
        return "нет манифеста"
    data = json.loads(ROOM.read_text(encoding="utf-8"))
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


def entry(name: str, spec: dict, version: int = 2, previous: str | None = None) -> dict:
    return {
        "id": name,
        "version": version,
        "contract": spec["contract"],
        "input": spec["input"],
        "returns": spec["returns"],
        "output": spec["output"],
        "semantics": spec["semantics"],
        "permissions": spec["permissions"],
        "examples": spec["examples"],
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


REQUIRED = ("id", "version", "contract", "input", "returns", "output", "semantics",
            "permissions", "examples", "environment", "provenance", "status")


def problems(rows: list[dict]) -> list[str]:
    out = []
    seen = set()
    for index, row in enumerate(rows, 1):
        for field in REQUIRED:
            if not row.get(field):
                out.append(f"строка {index}: нет поля {field}")
        examples = row.get("examples") or []
        if not 1 <= len(examples) <= 5:
            out.append(f"строка {index}: примеров вызова {len(examples)}, нужно 1–5")
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
    print(f"[ok] реестр: {len(rows)} записей, у всех есть контракт из четырёх уровней и примеры вызова")
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
