"""gate_probe — доказать, что гейт умеет падать.

Гейт, который не падает на реалистичном дефекте, ничего не проверяет. Здесь для каждого гейта
подкладывается **похожий на настоящее** дефект во временную копию репозитория, и требуется, чтобы
гейт его заметил. Пустой файл дефектом не считается: он ловится любым условием.

    python bin/gate_probe.py              # все пробы
    python bin/gate_probe.py --only секреты ссылки
    python bin/gate_probe.py --list
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bin.hs as hs  # noqa: E402

# Что копируется в песочницу: ровно то, что читают пробы. Копия полного репозитория слишком дорога.
COPY = [
    "CLAIMS.md",
    "NOT-CLAIMED.md",
    "README.md",
    "depths.json",
    "harnesses.json",
    "docs",
    "lab",
    "accept",
    "src",
    "core",
    "bin",
    "procedures.json",
]


def sandbox() -> Path:
    target = Path(tempfile.mkdtemp(prefix="gate-probe-"))
    for name in COPY:
        source = ROOT / name
        if not source.exists():
            continue
        destination = target / name
        if source.is_dir():
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns("*.bin", "__pycache__"))
        else:
            shutil.copy2(source, destination)
    return target


def probe_secrets(root: Path) -> None:
    (root / "docs" / "PROBE-secret.md").write_text(
        "# проба\n\nключ провайдера: sk-proj-0123456789abcdefghijklmnopqrstuv\n", encoding="utf-8"
    )


def probe_claims(root: Path) -> None:
    path = root / "CLAIMS.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.rstrip("\n") + "\n| C-9999 | утверждение без типа | | `true` | CLAIMS.md | 01.01.2026 | `x` |\n",
        encoding="utf-8",
    )


def probe_links(root: Path) -> None:
    (root / "docs" / "PROBE-link.md").write_text(
        "# проба\n\nсм. [нет такого файла](PROBE-missing.md)\n", encoding="utf-8"
    )


def probe_depths(root: Path) -> None:
    (root / "docs" / "ADR-9999-probe.md").write_text(
        "# ADR-9999 — проба\n\nДата: 01.01.2026. Статус: предложено.\n", encoding="utf-8"
    )


def probe_harnesses(root: Path) -> None:
    path = root / "harnesses.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("items", []).append({"id": "probe", "name": "проба"})
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def probe_criteria(root: Path) -> None:
    path = root / "docs" / "CRITERIA.md"
    text = path.read_text(encoding="utf-8")
    # Критерий без способа установления и с выдуманным статусом: так выглядит копипаста строки.
    path.write_text(
        text.rstrip("\n") + "\n| K999 | проба | выдуман | | docs/CRITERIA.md |\n", encoding="utf-8"
    )


def probe_failures(root: Path) -> None:
    (root / "lab" / "failures" / "F-9999.md").write_text(
        "id: F-9999\ndate: 06.11.2026\ntitle: проба без обязательных полей\n", encoding="utf-8"
    )


def probe_prereg(root: Path) -> None:
    (root / "lab" / "prereg" / "H-9999.json").write_text(
        json.dumps({"name": "проба", "closed": True}, ensure_ascii=False), encoding="utf-8"
    )


def probe_adoptions(root: Path) -> None:
    path = root / "lab" / "adoptions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    # Внедрённое решение без источника и без отрицательного контроля — так выглядит «взял, потому что
    # понравилось».
    data.append({"id": "A-9999", "mechanism": "проба", "status": "adopted", "decision": "взято"})
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def probe_procs(root: Path) -> None:
    path = root / "procedures.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("procedures", []).append({"id": "P-9999", "name": "проба"})
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


PROBES = {
    "секреты": (hs.gate_secrets, probe_secrets),
    "утверждения": (hs.gate_claims, probe_claims),
    "ссылки": (hs.gate_links, probe_links),
    "глубины": (hs.gate_depths, probe_depths),
    "харнессы": (hs.gate_harnesses, probe_harnesses),
    "критерии": (hs.gate_criteria, probe_criteria),
    "отказы": (hs.gate_failures, probe_failures),
    "пре-регистрация": (hs.gate_prereg, probe_prereg),
    "решения": (hs.gate_adoptions, probe_adoptions),
    "процедуры": (hs.gate_procs, probe_procs),
}


def run(names: list[str]) -> int:
    rows = []
    broken = 0
    for name, (gate, inject) in PROBES.items():
        if names and name not in names:
            continue
        clean = sandbox()
        try:
            baseline = gate(clean)
            inject(clean)
            after = gate(clean)
            caught = len(after) > len(baseline)
            rows.append((name, len(baseline), len(after), caught))
            if not caught:
                broken += 1
        finally:
            shutil.rmtree(clean, ignore_errors=True)

    lines = ["# Пробы гейтов: падает ли гейт на реалистичном дефекте", ""]
    lines.append(f"{'гейт':16} до  после  поймал")
    for name, before, after, caught in rows:
        lines.append(f"{name:16} {before:>2}  {after:>5}  {'да' if caught else 'НЕТ'}")
    lines += ["", f"поймали: {len(rows) - broken} из {len(rows)}"]
    text = "\n".join(lines) + "\n"
    (ROOT / "research" / "outputs" / "gate-probes.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0 if broken == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="пробы гейтов")
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.list:
        print(", ".join(PROBES))
        return 0
    return run(args.only)


if __name__ == "__main__":
    sys.exit(main())
