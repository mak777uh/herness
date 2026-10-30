"""Перебор бесплатных движков плагина напрямую: кто отвечает и насколько релевантно."""

import json
import subprocess
import sys
from pathlib import Path

PROFILE = Path.home() / ".dsh" / "profiles" / "desktop"
QUERY = "nixos 26.05 release notes"

SCRIPT = """
const m = await import('dsh-free-search');
const names = Object.keys(m).filter(k => k.startsWith('search') && typeof m[k] === 'function');
const out = [];
for (const name of names) {
  const t0 = Date.now();
  try {
    const r = await m[name](%s, { maxResults: 5 });
    const items = Array.isArray(r) ? r : (r?.results ?? r?.items ?? []);
    const titles = items.slice(0, 5).map(i => String(i.title || i.name || ''));
    out.push({ name, ok: true, n: items.length, ms: Date.now() - t0, titles });
  } catch (e) {
    out.push({ name, ok: false, error: String(e.message).slice(0, 80) });
  }
}
console.log(JSON.stringify(out));
""" % json.dumps(QUERY)

completed = subprocess.run(
    ["node", "--input-type=module", "-e", SCRIPT],
    cwd=str(PROFILE), capture_output=True, text=True, timeout=600,
    encoding="utf-8", errors="replace",
)
line = [ln for ln in completed.stdout.splitlines() if ln.startswith("[")]
if not line:
    print("нет вывода:", completed.stdout[-300:], completed.stderr[-300:])
    sys.exit(1)

rows = json.loads(line[-1])
words = ["nixos", "26.05", "release", "notes"]
print(f"движков проверено: {len(rows)}\n")
for row in sorted(rows, key=lambda r: (not r["ok"], -r.get("n", 0))):
    if row["ok"]:
        joined = " ".join(row["titles"]).lower()
        score = sum(1 for w in words if w in joined) / len(words)
        print(f"{row['name']:<22} результатов={row['n']:<2} релевантность={score:.2f} {row['ms']:>5} мс")
    else:
        print(f"{row['name']:<22} ошибка: {row['error']}")
