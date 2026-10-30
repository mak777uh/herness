"""Собирает тексты всех отчётов Proof of Usefulness через живой Chrome (страницы рендерятся JS)."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\111\herness")
sys.path.insert(0, str(ROOT))

from core.browser_search import ensure_chrome
from core.mcp_client import MCPClient

CLI = r"C:\111\browser-mcp\node_modules\@playwright\mcp\cli.js"
OUT = ROOT / "research" / "hn-reports"
OUT.mkdir(parents=True, exist_ok=True)

reports = json.loads((ROOT / "research" / "hackernoon-reports.json").read_text(encoding="utf-8"))
print("отчётов в списке:", len(reports))

alive, note = ensure_chrome()
print("chrome:", alive, "|", note)
if not alive:
    sys.exit(2)

client = MCPClient(["node", CLI, "--cdp-endpoint", "http://127.0.0.1:9222"],
                   cwd=r"C:\111\browser-mcp")
collected = 0
try:
    client.initialize()
    for index, report in enumerate(reports, start=1):
        slug = report["link"].rstrip("/").split("/")[-1][:80]
        target = OUT / f"{index:02d}-{slug}.txt"
        if target.exists() and target.stat().st_size > 2000:
            collected += 1
            continue
        try:
            client.call("browser_navigate", {"url": report["link"]})
            time.sleep(6)
            result = client.call("browser_evaluate", {
                "function": "() => document.body.innerText.slice(0, 20000)"})
            raw = "".join(item.get("text", "") for item in result.get("content", [])
                          if item.get("type") == "text")
            body = re.sub(r"^### Result\s*", "", raw).strip()
            if len(body) > 1500:
                target.write_text(f"TITLE: {report['title']}\nSCORE: {report['score']}\nLINK: {report['link']}\n\n{body}",
                                  encoding="utf-8")
                collected += 1
                print(f"[{index}/{len(reports)}] {slug[:50]} — {len(body)} зн.")
            else:
                print(f"[{index}/{len(reports)}] {slug[:50]} — мало текста ({len(body)})")
        except Exception as exc:  # noqa: BLE001
            print(f"[{index}/{len(reports)}] {slug[:50]} — ошибка {type(exc).__name__}")
finally:
    client.close()

print(f"собрано: {collected} из {len(reports)}")
