"""Копия профиля Chrome + запуск с CDP + поиск через Playwright MCP."""

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\111\herness")

from core.mcp_client import MCPClient

SRC = Path.home() / "AppData/Local/Google/Chrome/User Data"
DST = Path(r"C:\111\chrome-cdp")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
CLI = r"C:\111\browser-mcp\node_modules\@playwright\mcp\cli.js"
PORT = 9222

# 1. копия только того, что нужно для сессий
DST.mkdir(parents=True, exist_ok=True)
(DST / "Default").mkdir(exist_ok=True)
(DST / "Default" / "Network").mkdir(exist_ok=True)
for rel in ("Local State", "Default/Preferences", "Default/Secure Preferences",
            "Default/Network/Cookies", "Default/Cookies", "Default/Login Data",
            "Default/Web Data"):
    source = SRC / rel
    target = DST / rel
    if source.exists():
        try:
            shutil.copy2(source, target)
            print(f"скопировано: {rel} ({source.stat().st_size // 1024} КБ)")
        except Exception as exc:  # noqa: BLE001
            print(f"не скопировано: {rel} — {exc}")
    else:
        print(f"нет файла: {rel}")

# 2. запуск Chrome с CDP на копии профиля
proc = subprocess.Popen([
    str(CHROME), f"--remote-debugging-port={PORT}",
    f"--user-data-dir={DST}", "--no-first-run", "--no-default-browser-check",
    "about:blank",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(8)
print("chrome запущен, pid", proc.pid)

# 3. подключение через MCP
client = MCPClient(["node", CLI, "--cdp-endpoint", f"http://127.0.0.1:{PORT}"],
                   cwd=r"C:\111\browser-mcp")
try:
    client.initialize()
    query = "nixos 26.05 release notes"
    url = "https://www.perplexity.ai/search?q=" + query.replace(" ", "+")
    client.call("browser_navigate", {"url": url})
    time.sleep(8)
    result = client.call("browser_evaluate",
                         {"function": "() => document.body.innerText.slice(0, 2500)"})
    text = "".join(item.get("text", "") for item in result.get("content", []) if item.get("type") == "text")
    clean = " ".join(text.split())
    words = [w for w in ("nixos", "26.05", "release", "notes") if w in clean.lower()]
    print(f"\nPerplexity через живой профиль: текст {len(clean)} зн., слов запроса {len(words)}/4")
    print(clean[:600])
finally:
    client.close()
