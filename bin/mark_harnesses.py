"""mark_harnesses — разметка харнессов по фактическим путям в репозитории.

Метод (дешевле и надёжнее описаний):
1. блоблесс-клон `--depth 1 --filter=blob:none` — приходят только деревья, место почти не тратится;
2. `git ls-files` — список путей;
3. считаем сигналы под конкретные проблемы;
4. клон удаляем, результат пишем в harnesses.json сразу.

Важно: сигналы по путям — это **признак**, а не доказательство. Поэтому значение пишется как
«есть (N)» / «нет (0)» с пометкой метода, а не как «точно работает».
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(r"C:\111\probe-tmp")
GH = Path(r"C:\Program Files\GitHub CLI\gh.exe")

SIGNALS = {
    "P4": {  # среда: контейнеры/изоляция
        "pattern": r"dockerfile|docker-compose|containerfile|devcontainer|/sandbox/|seatbelt|firecracker|firejail|nsjail",
        "label": "изоляция",
    },
    "P5": {  # дописывание себя
        "pattern": r"(^|/)(plugins?|extensions?|skills?)/|plugin\.(py|ts|js|toml)$|cordis",
        "label": "плагины/навыки",
    },
    "P9": {  # параллельность
        "pattern": r"worktree|concurren|/queue/|scheduler|/workers?/",
        "label": "параллельность",
    },
    "P11": {  # интерфейс
        "pattern": r"(^|/)(ui|web|webui|frontend|desktop|tui|client)/",
        "label": "интерфейс",
    },
    "P10": {  # кодинг как домен
        "pattern": r"lsp|tree-?sitter|repo_?map|/patch|edit_?format|difflib",
        "label": "кодовые приёмы",
    },
    "P7b": {  # память/журнал (уточнение)
        "pattern": r"checkpoint|resume|/memory/|persist|event_?log|journal",
        "label": "память/восстановление",
    },
}


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                          timeout=180, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def token() -> str:
    import os

    return os.environ.get("GITHUB_TOKEN", "")


def mark(item: dict, tok: str) -> dict | None:
    TMP.mkdir(parents=True, exist_ok=True)
    target = TMP / item["id"]
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    url = f"https://x-access-token:{tok}@github.com/{item['repo']}.git"
    code, _ = run(["git", "-c", "http.proxy=", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout", "-q", url, str(target)])
    if code != 0:
        return None
    code, files = run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=target)
    shutil.rmtree(target, ignore_errors=True)
    if code != 0:
        return None
    import re

    paths = [line.lower() for line in files.splitlines() if line.strip()]
    signals = {}
    for key, spec in SIGNALS.items():
        regex = re.compile(spec["pattern"])
        hits = sum(1 for path in paths if regex.search(path))
        signals[key] = {"label": spec["label"], "hits": hits}
    return {"files": len(paths), "signals": signals}


def main(argv: list[str]) -> int:
    path = ROOT / "harnesses.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    tok = token()
    if not tok:
        print("нет токена GitHub", file=sys.stderr)
        return 2

    only = set(argv) if argv else None
    done = 0
    for item in data["items"]:
        if only and item["id"] not in only:
            continue
        if item.get("marked_from") and not only:
            continue
        result = mark(item, tok)
        if result is None:
            print(f"{item['id']:<18} клон не удался — пропуск")
            continue
        item["signals"] = {key: value["hits"] for key, value in result["signals"].items()}
        item["marked_from"] = f"git ls-files, {result['files']} файлов, 2026-10-30"
        # заполняем проблемы только там, где сигнал однозначен
        item["problems"] = dict(item.get("problems") or {})
        item["problems"]["P4"] = "есть" if item["signals"]["P4"] >= 3 else ("частично" if item["signals"]["P4"] else "нет")
        item["problems"]["P5"] = "есть" if item["signals"]["P5"] >= 5 else ("частично" if item["signals"]["P5"] else "нет")
        item["problems"]["P9"] = "есть" if item["signals"]["P9"] >= 3 else ("частично" if item["signals"]["P9"] else "нет")
        item["problems"]["P11"] = "есть" if item["signals"]["P11"] >= 3 else ("частично" if item["signals"]["P11"] else "нет")
        item["problems"]["P10"] = "частично" if item["signals"]["P10"] else "нет"
        done += 1
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{item['id']:<18} файлов {result['files']:>5} | "
              + " ".join(f"{k}={v['hits']}" for k, v in result["signals"].items()))
    print(f"\nразмечено сейчас: {done}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


