"""gh_cleanup — удалить репозитории с GitHub, оставив только нужные.

ОСТАВИТЬ: herness, mak777uh (профиль), - (морфогенез), cicada3301.
УДАЛИТЬ: все остальные.

Сначала --plan (показать), потом --run (удалить). Удаление необратимо.

    python bin/gh_cleanup.py --plan
    python bin/gh_cleanup.py --run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "outputs" / "gh-cleanup.txt"

KEEP = {"herness", "mak777uh", "-", "cicada3301"}


def token() -> str:
    value = os.environ.get("GITHUB_TOKEN", "").strip()
    if not value:
        print("нет GITHUB_TOKEN в окружении", file=sys.stderr)
        sys.exit(2)
    return value


def api(method: str, path: str, tok: str) -> tuple[int, object]:
    request = urllib.request.Request(
        f"https://api.github.com{path}", method=method,
        headers={"Authorization": f"token {tok}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(request, timeout=60) as answer:
            body = answer.read().decode("utf-8")
            return answer.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as error:
        return error.code, {"message": error.read().decode("utf-8", "replace")[:200]}


def list_repos(tok: str) -> list[dict]:
    repos, page = [], 1
    while True:
        code, batch = api("GET", f"/user/repos?per_page=100&page={page}&affiliation=owner", tok)
        if code != 200 or not isinstance(batch, list) or not batch:
            break
        repos += batch
        page += 1
    return repos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="очистка GitHub")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    tok = token()
    repos = list_repos(tok)
    keep = [r["name"] for r in repos if r["name"] in KEEP]
    drop = [r["name"] for r in repos if r["name"] not in KEEP]

    lines = ["# Очистка GitHub", ""]
    lines.append(f"оставить ({len(keep)}): {', '.join(sorted(keep))}")
    lines.append(f"удалить ({len(drop)}): {', '.join(sorted(drop))}")
    lines.append("")

    if args.plan:
        lines.append("это план; ничего не удалено")
        text = "\n".join(lines) + "\n"
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
        print(text)
        return 0

    if args.run:
        removed, failed = [], []
        for name in sorted(drop):
            code, answer = api("DELETE", f"/repos/mak777uh/{name}", tok)
            if code in (204, 200):
                removed.append(name)
                print(f"удалён: {name}", flush=True)
            else:
                failed.append(f"{name}: {code} {answer.get('message', '')}")
                print(f"ОШИБКА {name}: {code}", flush=True)
        lines.append(f"удалено: {len(removed)}")
        lines.append(f"ошибок: {len(failed)}")
        for item in failed:
            lines.append(f"  {item}")
        text = "\n".join(lines) + "\n"
        OUT.write_text(text, encoding="utf-8")
        print(text)
        return 0 if not failed else 1

    print("укажи --plan или --run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
