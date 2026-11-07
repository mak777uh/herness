"""build_registry — реестр инструментов: контракт, замыкание, происхождение, хеш среды.

Эксперимент E1 плана P33 + A-0042 (контракт с примерами) + замыкание (flowguard-spec).

У каждого инструмента:
  контракт из четырёх уровней — имя, вход, выход, семантика;
  1–5 примеров вызова;
  ЗАМЫКАНИЕ — что инструменту доступно: файлы, сеть, время, память, объём ответа.

Замыкание — это не «мы проверили, что он не выходит». Это объявление, против которого
проверяется код: если инструмент не получает доступа к записи, он не может писать
структурно, а не «по дисциплине».

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

# Контракты и замыкания существующих инструментов.
TOOLS = {
    "search": {
        "contract": "ищет подстроку в файлах каталога",
        "input": {"path": "каталог или файл внутри комнаты", "needle": "подстрока, регистр не важен"},
        "returns": "текст: найдено K в M файлах, файлы с числом совпадений, до 40 строк, разные варианты",
        "output": {"found": "число совпадений", "files": "список путей с числом", "lines": "до 40 строк вида путь:строка: текст", "distinct": "строка «разные (N): …»"},
        "semantics": "ищет по всем файлам каталога рекурсивно; совпадение ищется во всей строке, показывается окно вокруг него; если в двух последних результатах есть ответ — собери и ответь",
        "closure": {
            "fs": {"read": ["/mnt/**"], "write": []},
            "net": [],
            "time_ms": 2000,
            "memory_mb": 32,
            "output_bytes": 16000,
        },
        "examples": ["TOOL search /mnt/docs C-0196", "TOOL search /mnt/runs/dump administration"],
    },
    "list": {
        "contract": "перечисляет содержимое каталога",
        "input": {"path": "каталог внутри комнаты"},
        "returns": "каталоги первыми с косой чертой, затем файлы с размерами",
        "output": {"entries": "список: имя каталога с «/» или имя файла с размером в байтах"},
        "semantics": "один уровень вглубь, без рекурсии; если в каталоге больше 100 записей — выводится начало и число остальных",
        "closure": {
            "fs": {"read": ["/mnt/**"], "write": []},
            "net": [],
            "time_ms": 200,
            "memory_mb": 8,
            "output_bytes": 8000,
        },
        "examples": ["TOOL list /mnt", "TOOL list /mnt/runs/dump"],
    },
    "read": {
        "contract": "читает файл с номерами строк, начиная с указанной",
        "input": {"path": "файл внутри комнаты", "line": "необязательный номер первой строки, по умолчанию 1"},
        "returns": "до 8 КиБ текста с номерами строк",
        "output": {"lines": "строки вида «номер: текст»", "truncated": "признак, что файл длиннее выдачи"},
        "semantics": "выдача ограничена 8 КиБ; если файл длиннее, продолжение читается с указанного номера строки",
        "closure": {
            "fs": {"read": ["/mnt/**"], "write": []},
            "net": [],
            "time_ms": 100,
            "memory_mb": 4,
            "output_bytes": 8192,
        },
        "examples": ["TOOL read /mnt/CLAIMS.md", "TOOL read /mnt/CLAIMS.md 220"],
    },
    "write": {
        "contract": "пишет файл внутри рабочего каталога",
        "input": {"path": "файл внутри рабочего каталога", "text": "содержимое целиком"},
        "returns": "подтверждение записи",
        "output": {"ok": "подтверждение", "bytes": "сколько байт записано"},
        "semantics": "пишет только внутри рабочего каталога, вне его отказывает; перезаписывает файл целиком",
        "closure": {
            "fs": {"read": ["/mnt/**"], "write": ["/mnt/work/**"]},
            "net": [],
            "time_ms": 200,
            "memory_mb": 8,
            "output_bytes": 500,
        },
        "examples": ["TOOL write /mnt/work/notes.md текст"],
    },
    "seal": {
        "contract": "запечатывает файл: sha256 канонического префикса до маркера «## Seal»",
        "input": {"path": "файл внутри рабочего каталога"},
        "returns": "отпечаток и путь sidecar",
        "output": {"digest": "sha256", "sidecar": "путь к файлу с отпечатком"},
        "semantics": "отпечаток считается по содержимому ДО маркера «## Seal»; правка после маркера его не меняет",
        "closure": {
            "fs": {"read": ["/mnt/**"], "write": ["/mnt/work/**"]},
            "net": [],
            "time_ms": 200,
            "memory_mb": 8,
            "output_bytes": 500,
        },
        "examples": ["TOOL seal /mnt/work/notes.md"],
    },
    "netprobe": {
        "contract": "проверяет доступность адреса из комнаты",
        "input": {"host": "адрес", "port": "необязательный порт"},
        "returns": "код ответа или ошибку соединения",
        "output": {"reachable": "да/нет", "detail": "код или текст ошибки"},
        "semantics": "проверяет только доступность, содержимое не загружает; сеть из комнаты идёт только через мост",
        "closure": {
            "fs": {"read": [], "write": []},
            "net": ["10.0.2.2:8790"],
            "time_ms": 3000,
            "memory_mb": 4,
            "output_bytes": 500,
        },
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


def entry(name: str, spec: dict, version: int = 3, previous: str | None = None) -> dict:
    return {
        "id": name,
        "version": version,
        "contract": spec["contract"],
        "input": spec["input"],
        "returns": spec["returns"],
        "output": spec["output"],
        "semantics": spec["semantics"],
        "closure": spec["closure"],
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
            "closure", "examples", "environment", "provenance", "status")
CLOSURE_KEYS = ("fs", "net", "time_ms", "memory_mb", "output_bytes")


def problems(rows: list[dict]) -> list[str]:
    out = []
    seen = set()
    for index, row in enumerate(rows, 1):
        for field in REQUIRED:
            if not row.get(field):
                out.append(f"строка {index}: нет поля {field}")
        closure = row.get("closure") or {}
        if closure:
            for key in CLOSURE_KEYS:
                if key not in closure:
                    out.append(f"строка {index}: в замыкании нет {key}")
            if not isinstance(closure.get("fs"), dict):
                out.append(f"строка {index}: замыкание fs не структура")
            for limit in ("time_ms", "memory_mb", "output_bytes"):
                value = closure.get(limit)
                if not isinstance(value, int) or value <= 0:
                    out.append(f"строка {index}: замыкание {limit} не положительное число")
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
    print(f"[ok] реестр: {len(rows)} записей, у всех есть контракт, замыкание и примеры вызова")
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
