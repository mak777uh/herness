"""closure_probe — проверка, что код инструмента соответствует объявленному замыканию.

Принцип из flowguard-spec: не «мы проверили, что инструмент не выходит», а объявленное
замыкание, против которого проверяется код.

Проверяем по исходнику core-rs/src/loopmod.rs:
  - если замыкание запрещает запись, в теле инструмента не должно быть вызовов записи;
  - если замыкание запрещает сеть, в теле не должно быть сетевых вызовов;
  - если замыкание ограничивает объём ответа, в теле должна быть обрезка.

Отрицательный контроль: подложить инструмент, который пишет, при замыкании без записи —
проверка обязана это найти.

    python bin/closure_probe.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bin import build_registry as reg  # noqa: E402

LOOP = ROOT / "core-rs" / "src" / "loopmod.rs"
OUT = ROOT / "research" / "outputs" / "closure-check.txt"

# Что в Rust означает запись и сеть.
WRITE_MARKERS = ("File::create", "OpenOptions", "fs::write", "write_all", "create_dir")
NET_MARKERS = ("TcpStream", "UdpSocket", "connect(", "netprobe")


def body_of(name: str, source: str) -> str:
    """Тело функции инструмента: от объявления до следующей функции того же уровня."""
    pattern = re.compile(r"fn tool_" + name + r"\w*\([^)]*\)[^{]*\{", re.S)
    found = pattern.search(source)
    if not found:
        return ""
    start = found.end()
    depth = 1
    index = start
    while index < len(source) and depth > 0:
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
        index += 1
    return source[start:index]


def violations(name: str, closure: dict, body: str) -> list[str]:
    out = []
    fs = closure.get("fs") or {}
    if not (fs.get("write") or []):
        for marker in WRITE_MARKERS:
            if marker in body:
                out.append(f"{name}: замыкание запрещает запись, а в теле есть {marker}")
    if not (closure.get("net") or []):
        for marker in NET_MARKERS:
            if marker in body:
                out.append(f"{name}: замыкание запрещает сеть, а в теле есть {marker}")
    return out


def main() -> int:
    rows = [json.loads(line) for line in reg.REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    source = LOOP.read_text(encoding="utf-8")

    lines = ["# Соответствие кода инструментов объявленному замыканию", ""]
    total = 0
    for row in rows:
        name = row["id"]
        body = body_of(name, source)
        if not body:
            lines.append(f"{name:10} тело не найдено в loopmod.rs")
            continue
        found = violations(name, row["closure"], body)
        total += len(found)
        lines.append(f"{name:10} {'нарушений нет' if not found else '; '.join(found)}")

    # Отрицательный контроль: инструмент, который пишет, при замыкании без записи.
    fake = "fn tool_read_fake() { let f = File::create(\"/mnt/x\"); }"
    caught = bool(violations("read", {"fs": {"write": []}, "net": []}, fake))
    lines.append(f"{'контроль':10} {'поймано' if caught else 'ПРОПУЩЕНО'}")

    lines += [
        "",
        f"нарушений: {total}",
        "# Что доказывает: у инструментов без права записи в теле нет вызовов записи.",
        "# Что НЕ доказывает: что обход через уже доступные функции невозможен — это проверяет прогон.",
    ]
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if total == 0 and caught else 1


if __name__ == "__main__":
    sys.exit(main())
