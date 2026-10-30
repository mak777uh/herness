"""Перебор поисковиков в живом Chrome через CDP: где есть реальная выдача."""

import sys
import time

sys.path.insert(0, r"C:\111\herness")

from core.mcp_client import MCPClient

CLI = r"C:\111\browser-mcp\node_modules\@playwright\mcp\cli.js"
QUERY = "nixos 26.05 release notes"
Q = QUERY.replace(" ", "+")

TARGETS = [
    ("google", f"https://www.google.com/search?q={Q}"),
    ("duckduckgo", f"https://duckduckgo.com/?q={Q}"),
    ("yandex", f"https://yandex.ru/search/?text={Q}"),
    ("bing", f"https://www.bing.com/search?q={Q}"),
    ("mojeek", f"https://www.mojeek.com/search?q={Q}"),
    ("startpage", f"https://www.startpage.com/sp/search?query={Q}"),
]

client = MCPClient(["node", CLI, "--cdp-endpoint", "http://127.0.0.1:9222"], cwd=r"C:\111\browser-mcp")
try:
    client.initialize()
    for name, url in TARGETS:
        try:
            client.call("browser_navigate", {"url": url})
        except Exception as exc:  # noqa: BLE001
            print(f"{name:<12} навигация: {exc}")
            continue
        time.sleep(7)
        try:
            result = client.call("browser_evaluate", {
                "function": "() => ({text: document.body.innerText.slice(0, 4000), links: Array.from(document.querySelectorAll('a[href^=http]')).slice(0,40).map(a => a.href)})"
            })
        except Exception as exc:  # noqa: BLE001
            print(f"{name:<12} извлечение: {exc}")
            continue
        payload = ""
        for item in result.get("content", []):
            if item.get("type") == "text":
                payload += item.get("text", "")
        low = payload.lower()
        words = [w for w in ("nixos", "26.05", "release", "notes") if w in low]
        blocked = any(marker in low for marker in ("captcha", "подозрительный", "проверки безопасности",
                                                   "not a robot", "unusual traffic", "access denied"))
        print(f"{name:<12} слов {len(words)}/4  блокировка={blocked}  размер={len(payload)}")
finally:
    client.close()
