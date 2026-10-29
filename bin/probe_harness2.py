"""probe2 — рекурсивное дерево репозитория вместо корневого листинга.

Корневой листинг обманул: у OpenHands каталог контейнеров не в корне. Берём git trees и ищем
признаки по всему дереву.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com"


def get(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "herness", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except Exception:
        return None


def tree(repo: str) -> list[str]:
    info = get(f"{API}/repos/{repo}") or {}
    branch = info.get("default_branch", "main")
    data = get(f"{API}/repos/{repo}/git/trees/{branch}?recursive=1") or {}
    return [item.get("path", "").lower() for item in data.get("tree", []) if item.get("type") == "blob"]


SIGNALS = {
    "container": ("dockerfile", "docker-compose", ".devcontainer", "containerfile"),
    "ui": ("/ui/", "/web/", "webui", "/frontend/", "/desktop/", "/tui/"),
    "mcp": ("mcp",),
    "parallel": ("worktree", "parallel", "concurrency", "queue"),
    "memory": ("memory", "checkpoint", "session"),
    "sandbox": ("sandbox", "seatbelt", "firecracker"),
}


def main(argv: list[str]) -> int:
    data = json.loads((ROOT / "harnesses.json").read_text(encoding="utf-8"))
    wanted = set(argv) if argv else None
    results = {}
    for item in data["items"]:
        if wanted and item["id"] not in wanted:
            continue
        paths = tree(item["repo"])
        if not paths:
            print(f"{item['id']:<18} дерево недоступно")
            continue
        found = {name: sum(1 for path in paths if any(sig in path for sig in sigs))
                 for name, sigs in SIGNALS.items()}
        results[item["id"]] = {"repo": item["repo"], "files": len(paths), **found}
        print(f"{item['id']:<18} файлов {len(paths):>5} | docker={found['container']:>3} ui={found['ui']:>3} "
              f"mcp={found['mcp']:>3} parallel={found['parallel']:>3} sandbox={found['sandbox']:>3}")
    (ROOT / "research" / "harness-probe.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nзаписано: research/harness-probe.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
