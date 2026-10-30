"""Извлекает реальные ссылки выдачи из живого Chrome и оценивает релевантность."""

import json
import sys
import time

sys.path.insert(0, r"C:\111\herness")

from core.mcp_client import MCPClient

CLI = r"C:\111\browser-mcp\node_modules\@playwright\mcp\cli.js"
QUERY = "nixos 26.05 release notes"
Q = QUERY.replace(" ", "+")

TARGETS = {
    "google": f"https://www.google.com/search?q={Q}",
    "duckduckgo": f"https://duckduckgo.com/?q={Q}",
    "startpage": f"https://www.startpage.com/sp/search?query={Q}",
    "bing": f"https://www.bing.com/search?q={Q}",
}

EXTRACT = """() => Array.from(document.querySelectorAll('a[href^="http"]'))
  .map(a => ({href: a.href, text: (a.innerText || '').trim().slice(0, 120)}))
  .filter(x => x.text.length > 12)
  .slice(0, 25)"""

client = MCPClient(["node", CLI, "--cdp-endpoint", "http://127.0.0.1:9222"], cwd=r"C:\111\browser-mcp")
try:
    client.initialize()
    for name, url in TARGETS.items():
        client.call("browser_navigate", {"url": url})
        time.sleep(7)
        result = client.call("browser_evaluate", {"function": EXTRACT})
        payload = "".join(item.get("text", "") for item in result.get("content", [])
                          if item.get("type") == "text")
        # результат приходит как текст с JSON внутри
        start = payload.find("[")
        items = []
        if start >= 0:
            try:
                items = json.loads(payload[start:payload.rfind("]") + 1])
            except json.JSONDecodeError:
                items = []
        relevant = [i for i in items if any(w in (i["text"] + i["href"]).lower()
                                           for w in ("nixos", "26.05", "release"))]
        print(f"\n=== {name}: ссылок {len(items)}, релевантных {len(relevant)}")
        for item in relevant[:5]:
            print(f"   {item['text'][:64]}")
            print(f"     {item['href'][:80]}")
finally:
    client.close()
