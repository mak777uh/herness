"""Живой поиск через браузер: заходим и забираем текст выдачи."""

import sys
import time

sys.path.insert(0, r"C:\111\herness")

from core.mcp_client import MCPClient

CLI = r"C:\111\browser-mcp\node_modules\@playwright\mcp\cli.js"
QUERY = "nixos 26.05 release notes"

TARGETS = [
    ("perplexity", f"https://www.perplexity.ai/search?q={QUERY.replace(' ', '+')}"),
    ("google", f"https://www.google.com/search?q={QUERY.replace(' ', '+')}"),
]

client = MCPClient(["node", CLI, "--browser", "chrome", "--headless"], cwd=r"C:\111\browser-mcp")
try:
    client.initialize()
    for name, url in TARGETS:
        try:
            client.call("browser_navigate", {"url": url})
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: навигация не удалась — {exc}")
            continue
        time.sleep(6)
        result = client.call("browser_evaluate", {"function": "() => document.body.innerText.slice(0, 3000)"})
        text = ""
        for item in result.get("content", []):
            if item.get("type") == "text":
                text += item.get("text", "")
        clean = " ".join(text.split())
        words = [w for w in ("nixos", "26.05", "release", "notes") if w in clean.lower()]
        print(f"\n=== {name} ===")
        print(f"длина текста: {len(clean)}; слов запроса: {len(words)}/4")
        print(clean[:400] if clean else "пусто")
finally:
    client.close()
