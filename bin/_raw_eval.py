"""Смотрим сырой формат ответа browser_evaluate."""

import sys
import time

sys.path.insert(0, r"C:\111\herness")

from core.mcp_client import MCPClient

FUNC = ("() => JSON.stringify(Array.from(document.querySelectorAll('a[href]')).slice(0, 8)"
        ".map(a => ({h: a.href, t: (a.innerText || '').slice(0, 60)})))")

client = MCPClient(["node", r"C:\111\browser-mcp\node_modules\@playwright\mcp\cli.js",
                    "--cdp-endpoint", "http://127.0.0.1:9222"], cwd=r"C:\111\browser-mcp")
client.initialize()
client.call("browser_navigate", {"url": "https://duckduckgo.com/?q=nixos+26.05+release+notes"})
time.sleep(6)
result = client.call("browser_evaluate", {"function": FUNC})
print("ключи ответа:", list(result.keys()))
for item in result.get("content", []):
    if item.get("type") == "text":
        print("СЫРОЙ ТЕКСТ:", repr(item["text"][:500]))
client.close()
