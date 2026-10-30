"""Копия cookie из живого профиля, запуск Chrome с CDP и проверка обхода Cloudflare."""

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\111\herness")

from core.mcp_client import MCPClient

SRC = Path.home() / "AppData/Local/Google/Chrome/User Data"
DST = Path(r"C:\111\chrome-cdp")
CHROME = Path(r"C:\Program Files\Google/Chrome/Application/chrome.exe")
CLI = r"C:\111\browser-mcp\node_modules\@playwright\mcp\cli.js"
PORT = 9222

running = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe"], capture_output=True, text=True)
if "chrome.exe" in running.stdout.lower():
    print("ВНИМАНИЕ: Chrome ещё запущен, cookie может быть занят")

DST.mkdir(parents=True, exist_ok=True)
(DST / "Default" / "Network").mkdir(parents=True, exist_ok=True)

copied, failed = [], []
for rel in ("Local State", "Default/Preferences", "Default/Secure Preferences",
            "Default/Network/Cookies", "Default/Cookies", "Default/Login Data", "Default/Web Data"):
    source, target = SRC / rel, DST / rel
    if not source.exists():
        continue
    try:
        shutil.copy2(source, target)
        copied.append(f"{rel} ({source.stat().st_size // 1024} КБ)")
    except Exception as exc:  # noqa: BLE001
        failed.append(f"{rel}: {exc.__class__.__name__}")

print("скопировано:", ", ".join(copied) or "—")
print("не удалось:", ", ".join(failed) or "—")

proc = subprocess.Popen([
    str(CHROME), f"--remote-debugging-port={PORT}", f"--user-data-dir={DST}",
    "--no-first-run", "--no-default-browser-check", "about:blank",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(10)
print("chrome pid", proc.pid)

client = MCPClient(["node", CLI, "--cdp-endpoint", f"http://127.0.0.1:{PORT}"], cwd=r"C:\111\browser-mcp")
try:
    client.initialize()
    query = "nixos 26.05 release notes"
    client.call("browser_navigate", {"url": "https://www.perplexity.ai/search?q=" + query.replace(" ", "+")})
    time.sleep(10)
    result = client.call("browser_evaluate", {"function": "() => document.body.innerText.slice(0, 3000)"})
    text = "".join(item.get("text", "") for item in result.get("content", []) if item.get("type") == "text")
    clean = " ".join(text.split())
    blocked = "проверки безопасности" in clean.lower() or "cloudflare" in clean.lower()
    print(f"\nPerplexity: {len(clean)} зн.; признак блокировки: {blocked}")
    print(clean[:700])
finally:
    client.close()
