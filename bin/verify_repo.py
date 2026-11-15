"""verify_repo — сколько чисел в README чужого репозитория можно воспроизвести.

Зачем (фаза 1). У харнесса есть прибор для **своих** утверждений (`CLAIMS.md`: команда,
артефакт, ожидание). Снаружи нужен ответ на более простой вопрос: в README написано
«412K downloads» — а чем это проверить? Инструмент не судит истинность числа: он измеряет
**наличие способа его воспроизвести** и честно называет долю.

Что читается: проза и строки markdown-таблиц. Заголовок, разделитель, блоки кода, бейджи
и HTML — не читаются. Команда ищется в той же строке и в соседних строках того же блока;
за пределы блока поиск не выходит, иначе число получило бы чужую команду.

    python bin/verify_repo.py path/or/url                  # отчёт в research/verify/
    python bin/verify_repo.py https://github.com/x/y --out /tmp/rep
    python bin/verify_repo.py path --json                  # только json в stdout
    python bin/verify_repo.py path --fail-under 0.5        # rc=1, если доля ниже порога

Коды возврата: 0 — отчёт построен; 1 — сработал --fail-under; 2 — вход не годится
(нет README, нет каталога, клон не удался).

Что НЕ делает: не проверяет, правда ли число; не отличает маркетинг от ошибки; не судит
репозиторий; не запускает чужой код. Отчёт — про форму утверждения, а не про его содержание.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.2.0"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "research" / "verify"

README_NAMES = ("README.md", "README.rst", "README.txt", "readme.md", "Readme.md")

# Число рядом с единицей, которую можно посчитать. Список намеренно короткий: лучше меньше
# классов и честнее доля, чем широкий охват с ложными срабатываниями.
UNITS = (
    "тест", "теста", "тестов", "test", "tests", "проб", "gates", "gate",
    "звезд", "звёзд", "stars", "скачиван", "downloads", "загруз", "польз", "users",
    "строк", "lines", "мс", "ms", "сек", "seconds", "байт", "bytes", "kb", "mb", "гб",
    "%", "x", "×", "раз", "раза", "коммит", "commits", "релиз", "releases",
)
NUMBER = re.compile(r"(?<![\w.])(\d{1,4}(?:[.,]\d+)?\s*(?:k|K|M|млн|тыс|%|x|×)?)(?![\w.])")
COMMAND = re.compile(
    r"(`[^`]*`"                       # инлайн-команда
    r"|\b(?:python3?|pip|npm|npx|make|cargo|go|bash|sh|docker|curl|pytest|gh|just)\s+\S+"
    r"|(?:^|\s)\$\s+\S+)"
)
FLAT_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
URL = re.compile(r"https?://\S+")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def pick_readme(base: Path) -> Path | None:
    for name in README_NAMES:
        candidate = base / name
        if candidate.exists():
            return candidate
    found = sorted(base.glob("README*"))
    return found[0] if found else None


def fetch(target: str, workdir: Path) -> tuple[Path, str | None]:
    """Локальный каталог или клон. Возвращает (путь, ошибка)."""
    if re.match(r"^https?://", target):
        if shutil.which("git") is None:
            return Path(target), "нет git: клонировать нечем"
        dest = workdir / "repo"
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", target, str(dest)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
        )
        if result.returncode != 0:
            return dest, f"клон не удался: {(result.stderr or '').strip()[:160]}"
        return dest, None
    path = Path(target).expanduser()
    if not path.is_dir():
        return path, f"нет каталога: {path}"
    return path, None


def is_number_claim(text: str) -> bool:
    if not NUMBER.search(text):
        return False
    lowered = text.lower()
    return any(unit in lowered for unit in UNITS)


def has_command(text: str, neighbours: list[str]) -> bool:
    if COMMAND.search(text):
        return True
    return any(COMMAND.search(item) for item in neighbours)


def clean(text: str, limit: int = 200) -> str:
    flat = FLAT_LINK.sub(r"\1", text.strip())
    if flat.startswith("|"):
        cells = [cell.strip() for cell in flat.strip("|").split("|")]
        flat = " · ".join(cell for cell in cells if cell)
    return flat[:limit]


def analyse(base: Path) -> dict:
    readme = pick_readme(base)
    if readme is None:
        return {"error": "нет README"}

    lines = _read(readme).splitlines()
    claims: list[dict] = []
    broad: list[dict] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!", "[", "|", "```", "<", "![")):
            # заголовки, таблицы, код и бейджи не судим: там число часто не утверждение
            continue
        # Числа и единицы ищутся в тексте без ссылок и URL: иначе «%3A» в адресе
        # становится процентом, а номер issue — числом утверждения.
        scan_text = URL.sub("", FLAT_LINK.sub(r"\1", stripped))
        if not NUMBER.search(scan_text):
            continue
        neighbours = [n.strip() for n in lines[max(0, index - 2):index] + lines[index + 1:index + 3]]
        item = {
            "line": index + 1,
            "text": clean(stripped),
            "has_command": has_command(stripped, neighbours),
        }
        broad.append(item)
        if is_number_claim(scan_text):
            claims.append(dict(item))

    total = len(claims)
    with_command = sum(1 for item in claims if item["has_command"])
    return {
        "readme": readme.name,
        "total": total,
        "with_command": with_command,
        "share": round(with_command / total, 3) if total else None,
        "broad_total": len(broad),
        "broad_with_command": sum(1 for item in broad if item["has_command"]),
        "claims": claims,
        "broad_without_command": [item for item in broad if not item["has_command"]],
    }


def render_markdown(name: str, data: dict, digest: str, when: str) -> str:
    if "error" in data:
        return f"# verify: {name}\n\nНе удалось: {data['error']}\n"
    total = data["total"]
    share = data["share"]
    head = (
        f"# verify: {name}\n\n"
        f"README: `{data['readme']}`\n\n"
        f"- строк с числами (широкий счёт): **{data.get('broad_total', 0)}**, из них с командой рядом: "
        f"**{data.get('broad_with_command', 0)}**\n"
        f"- чисел с единицей измерения (строгий счёт): **{total}**, из них с командой: "
        f"**{data['with_command']}**, доля проверяемых: **{'—' if share is None else share}**\n"
        f"Квитанция: вход `{digest[:16]}…` · инструмент `verify_repo {VERSION}` · {when}\n\n"
        "Строгий счёт — только строки, где рядом с числом есть единица, которую можно посчитать "
        "(тесты, звёзды, загрузки, мс, проценты). Широкий — любая строка с числом. Команда ищется "
        "в тексте той же строки и в соседних двух строках.\n\n"
    )
    if total == 0 and not data.get("broad_total"):
        return head + "чисел в тексте не найдено: измерять нечего (это не «100 % проверяемо»).\n"
    rows = ["| строка | число в тексте | команда рядом |", "|---|---|---|"]
    for item in data["claims"][:40]:
        rows.append(f"| {item['line']} | {item['text'].replace('|', '\\\\|')} | "
                    f"{'да' if item['has_command'] else '**нет**'} |")
    wide = data.get("broad_without_command", [])[:20]
    wide_block = ""
    if wide:
        wide_block = "\n## Числа без команды (широкий счёт, первые 20)\n\n" + "\n".join(
            f"- строка {item['line']}: {item['text']}" for item in wide
        ) + "\n"
    tail = (
        "\n## Что это не доказывает\n\n"
        "- Число без команды не значит «ложь»: оно значит «его нельзя воспроизвести из репозитория».\n"
        "- Наличие команды не значит, что она проверяет именно это число.\n"
        "- Отчёт читает только README: `docs/`, `CLAIMS.md`, бенчмарки и CI не разбираются.\n"
        "- Строгий счёт неполон по устройству: формулировки без единицы в него не попадают.\n"
    )
    return head + "\n".join(rows) + "\n" + wide_block + tail


def receipt(name: str, data: dict, digest: str, when: str) -> str:
    body = {
        "tool": f"verify_repo {VERSION}",
        "target": name,
        "input_sha256": digest,
        "generated_at": when,
        "total": data.get("total"),
        "with_command": data.get("with_command"),
        "share": data.get("share"),
        "broad_total": data.get("broad_total"),
        "broad_with_command": data.get("broad_with_command"),
        "how_to_check": "python bin/verify_repo.py <тот же вход> — json должен совпасть, кроме generated_at",
    }
    return json.dumps(body, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="сколько чисел README можно воспроизвести")
    parser.add_argument("target", help="путь к репозиторию или URL")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="куда положить отчёт")
    parser.add_argument("--json", action="store_true", help="json в stdout вместо файлов")
    parser.add_argument("--fail-under", type=float, default=None,
                        help="rc=1, если доля проверяемых ниже порога")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    when = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    with tempfile.TemporaryDirectory() as tmp:
        base, error = fetch(args.target, Path(tmp))
        if error:
            print(f"[FAIL] {error}", file=sys.stderr)
            return 2
        data = analyse(base)
        if "error" in data:
            print(f"[FAIL] {data['error']}: {args.target}", file=sys.stderr)
            return 2
        readme = pick_readme(base)
        digest = hashlib.sha256(readme.read_bytes() if readme else b"").hexdigest()
        name = Path(args.target.rstrip("/")).name or args.target
        report = {"tool": f"verify_repo {VERSION}", "target": name,
                  "input_sha256": digest, "generated_at": when, **data}

        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=1))
        else:
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{name}.md").write_text(render_markdown(name, data, digest, when), encoding="utf-8")
            (out / f"{name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                              encoding="utf-8")
            (out / f"{name}.receipt.json").write_text(receipt(name, data, digest, when), encoding="utf-8")
            share = "—" if data["share"] is None else f"{data['share']:.2f}"
            print(f"{name}: чисел {data['total']}, с командой {data['with_command']}, доля {share}")

    if args.fail_under is not None:
        share = data.get("share")
        if share is None or share < args.fail_under:
            print(f"[FAIL] доля {share} ниже порога {args.fail_under}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
