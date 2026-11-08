"""room_ui — окно с чатом для реальных задач.

Простой HTTP-сервер на stdlib: страница с полем ввода, историей и вердиктами.
Задача уходит в очередь `intake/`, прогоняется в комнате, ответ появляется в чате.

    python bin/room_ui.py --port 8791
    затем открыть http://127.0.0.1:8791
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTAKE = ROOT / "intake"
DONE = INTAKE / "done"
HISTORY = INTAKE / "history.jsonl"

PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>herness — комната</title>
<style>
  :root { --bg:#0f1115; --panel:#171a21; --line:#262b36; --text:#e6e8ee; --dim:#8b93a7;
          --ok:#3fb950; --bad:#f85149; --unknown:#d29922; --accent:#4c8dff; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--text); height:100vh; display:flex; flex-direction:column; }
  header { padding:14px 20px; border-bottom:1px solid var(--line); display:flex;
           align-items:center; gap:12px; background:var(--panel); }
  header h1 { font-size:16px; margin:0; font-weight:600; }
  header .status { font-size:12px; color:var(--dim); margin-left:auto; }
  #chat { flex:1; overflow-y:auto; padding:20px; display:flex; flex-direction:column; gap:14px; }
  .msg { max-width:min(820px,88%); padding:12px 14px; border-radius:12px; white-space:pre-wrap;
         word-wrap:break-word; }
  .user { align-self:flex-end; background:var(--accent); color:#fff; border-bottom-right-radius:4px; }
  .bot { align-self:flex-start; background:var(--panel); border:1px solid var(--line);
         border-bottom-left-radius:4px; }
  .meta { font-size:12px; color:var(--dim); margin-bottom:6px; }
  .verdict { display:inline-block; font-size:12px; font-weight:600; padding:2px 8px;
             border-radius:999px; margin-left:8px; }
  .PASS { background:rgba(63,185,80,.15); color:var(--ok); }
  .FAIL { background:rgba(248,81,73,.15); color:var(--bad); }
  .UNKNOWN { background:rgba(210,153,34,.15); color:var(--unknown); }
  .thinking { color:var(--dim); font-style:italic; }
  form { display:flex; gap:10px; padding:14px 20px; border-top:1px solid var(--line);
         background:var(--panel); }
  textarea { flex:1; resize:none; height:52px; padding:12px 14px; border-radius:10px;
             border:1px solid var(--line); background:var(--bg); color:var(--text);
             font:inherit; outline:none; }
  textarea:focus { border-color:var(--accent); }
  button { padding:0 22px; border:0; border-radius:10px; background:var(--accent); color:#fff;
           font:inherit; font-weight:600; cursor:pointer; }
  button:disabled { opacity:.5; cursor:default; }
  .empty { color:var(--dim); text-align:center; margin-top:40px; }
</style>
</head>
<body>
<header>
  <h1>herness — комната</h1>
  <span class="status" id="status">готов</span>
</header>
<div id="chat"><div class="empty">Задайте задачу — она выполнится в изолированной комнате.</div></div>
<form id="f">
  <textarea id="q" placeholder="Например: сколько строк в NOT-CLAIMED.md? Ответь только числом."></textarea>
  <button id="send" type="submit">Отправить</button>
</form>
<script>
const chat = document.getElementById('chat');
const q = document.getElementById('q');
const send = document.getElementById('send');
const status = document.getElementById('status');

function bubble(text, cls, verdict, seconds) {
  const d = document.createElement('div');
  d.className = 'msg ' + cls;
  if (verdict) {
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.innerHTML = 'комната · ' + (seconds ? seconds + ' с' : '');
    const v = document.createElement('span');
    v.className = 'verdict ' + verdict;
    v.textContent = verdict;
    meta.appendChild(v);
    d.appendChild(meta);
  }
  const body = document.createElement('div');
  body.textContent = text;
  d.appendChild(body);
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
  return d;
}

q.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); document.getElementById('f').requestSubmit(); }
});

document.getElementById('f').addEventListener('submit', async e => {
  e.preventDefault();
  const task = q.value.trim();
  if (!task) return;
  q.value = '';
  bubble(task, 'user');
  const wait = bubble('выполняю в комнате…', 'bot thinking');
  send.disabled = true;
  status.textContent = 'выполняю';
  try {
    const r = await fetch('/ask', { method:'POST', headers:{'Content-Type':'application/json'},
                                    body: JSON.stringify({ task }) });
    const data = await r.json();
    wait.remove();
    bubble(data.answer || '(пусто)', 'bot', data.verdict, data.seconds);
  } catch (err) {
    wait.remove();
    bubble('ошибка связи: ' + err, 'bot', 'UNKNOWN');
  } finally {
    send.disabled = false;
    status.textContent = 'готов';
    q.focus();
  }
});

async function loadHistory() {
  try {
    const r = await fetch('/history');
    const rows = await r.json();
    if (!rows.length) return;
    chat.innerHTML = '';
    for (const row of rows) {
      bubble(row.task, 'user');
      bubble(row.answer || '(пусто)', 'bot', row.verdict, row.seconds);
    }
  } catch (e) {}
}
loadHistory();
</script>
</body>
</html>
"""


def append_history(row: dict) -> None:
    INTAKE.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_history(limit: int = 50) -> list[dict]:
    if not HISTORY.exists():
        return []
    rows = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def run_task(task: str, timeout: int = 420) -> dict:
    """Задача в очередь, прогон в комнате, ответ обратно."""
    INTAKE.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    name = f"T-{stamp}"
    criteria = {
        "task": task,
        "require_status": "done",
        "max_steps": 24,
        "max_allowance": 0.1,
        "must_not_call": ["write"],
        "tools": ["search", "list", "read"],
    }
    path = INTAKE / f"{name}.json"
    path.write_text(json.dumps(criteria, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    started = time.time()
    proc = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(ROOT / "core-rs" / "accept-run.ps1"),
         "-Mode", "loop-bridge", "-Kernel", "vmlinuz-own-hardened2", "-Net",
         "-TimeoutSec", str(timeout), "-Criteria", str(path.relative_to(ROOT)), "-Task", task],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
    )
    verdict = "UNKNOWN"
    answer = ""
    for line in (proc.stdout or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("итог:"):
            verdict = stripped.split(":", 1)[1].strip()

    # Ответ агента лежит в журнале событием run/end: accept-run печатает вердикт,
    # но не текст ответа. Читаем журнал, иначе в чате будет пусто при PASS.
    journal = ROOT / "runs" / "accept" / "journal.bin"
    if journal.exists():
        raw = journal.read_bytes().decode("utf-8", errors="replace")
        found = re.search(r"run/end ([^\x00\x06\n]+)", raw)
        if found:
            answer = found.group(1).strip()
    seconds = round(time.time() - started, 1)

    (DONE / path.name).write_text(
        json.dumps({**criteria, "verdict": verdict, "answer": answer}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    path.unlink(missing_ok=True)

    row = {"task": task, "answer": answer, "verdict": verdict, "seconds": seconds,
           "at": datetime.now().isoformat(timespec="seconds")}
    append_history(row)
    return row


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # noqa: D401 — тишина в консоли
        return

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/history":
            self._send(200, json.dumps(read_history(), ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/ask":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", "replace")
        try:
            task = json.loads(raw).get("task", "").strip()
        except json.JSONDecodeError:
            task = ""
        if not task:
            self._send(400, json.dumps({"error": "пустая задача"}).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        row = run_task(task)
        self._send(200, json.dumps(row, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="окно с чатом для реальных задач")
    parser.add_argument("--port", type=int, default=8791)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"окно: http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлено")
    return 0


if __name__ == "__main__":
    sys.exit(main())
