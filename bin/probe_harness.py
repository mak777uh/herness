"""probe_harness — заполняет пустые измерения по фактам из репозитория.

Проверяем наличие известных файлов и топиков, а не описания: Dockerfile → контейнерная изоляция,
ui/web-каталог → есть интерфейс, работа-деревья → параллельность, «mcp» в топиках → протокол.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com"


def get(url: str) -> dict | list | None:
    request = urllib.request.Request(url, headers={"User-Agent": "herness", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except Exception:
        return None


def facts(repo: str) -> dict:
    info = get(f"{API}/repos/{repo}") or {}
    topics = {t.lower() for t in info.get("topics", [])}
    contents = get(f"{API}/repos/{repo}/contents/") or []
    names = {item.get("name", "").lower() for item in contents if isinstance(item, dict)}

    container = bool({"dockerfile", "docker-compose.yml", "docker-compose.yaml", ".devcontainer"} & names)
    has_ui = bool({"ui", "web", "webui", "frontend", "app", "desktop", "tui"} & names)
    mcp = "mcp" in topics or any("mcp" in name for name in names)

    return {
        "container": container,
        "has_ui": has_ui,
        "mcp_topic": mcp,
        "topics": sorted(topics)[:8],
        "root_sample": sorted(names)[:14],
    }


def main(argv: list[str]) -> int:
    path = ROOT / "harnesses.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    wanted = set(argv) if argv else None
    results = {}
    for item in data["items"]:
        if wanted and item["id"] not in wanted:
            continue
        results[item["id"]] = facts(item["repo"])
        found = results[item["id"]]
        print(f"{item['id']:<18} контейнер={found['container']} ui={found['has_ui']} mcp={found['mcp_topic']}")
    (ROOT / "research" / "harness-probe.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nзаписано: research/harness-probe.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
