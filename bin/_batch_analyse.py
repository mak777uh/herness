"""Разбор батча: ответы против факта, журналы проблемных прогонов."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\111\herness")
rows = json.loads((ROOT / "lab" / "journal-batch" / "results.json").read_text(encoding="utf-8"))

print("=== ответы и факты ===")
for row in rows:
    print(f"\n### {row['id']} ({row['status']}, {row['steps']} шагов, {row['seconds']} с)")
    print("вызовы:", " → ".join(row["tool_sequence"]) or "нет")
    if row["duplicate_calls"]:
        print("повторы:", row["duplicate_calls"])
    print("ответ:", " ".join(row["final"].split())[:600])

# факты считаем сами
print("\n=== факты ===")
bin_files = sorted((ROOT / "bin").glob("*.py"))
with_main = [f for f in bin_files if "def main" in f.read_text(encoding="utf-8", errors="replace")]
print(f"bin/*.py: {len(bin_files)}, с 'def main': {len(with_main)}")

claims = [line for line in (ROOT / "CLAIMS.md").read_text(encoding="utf-8").splitlines()
          if line.startswith("| C-")]
with_expect = [line for line in claims if line.strip().strip("|").split("|")[6].strip().strip("`").strip()]
print(f"утверждений: {len(claims)}, с ожиданием: {len(with_expect)}")

anchor_tests = len([line for line in (ROOT / "tests" / "test_anchor.py").read_text(encoding="utf-8").splitlines()
                    if line.startswith("@case(")])
print(f"случаев в test_anchor.py: {anchor_tests}")

gates = subprocess.run([sys.executable, "bin/hs.py", "gates"], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
names = [line.split("]")[1].split(":")[0].strip() for line in gates.stdout.splitlines() if line.startswith("[ok]")]
print(f"гейтов: {len(names)} — {', '.join(names)}")

print("\n=== журналы провалов ===")
for row in rows:
    if row["status"] != "budget":
        continue
    events = (ROOT / row["run_dir"] / "events.jsonl").read_text(encoding="utf-8").splitlines()
    calls = []
    for line in events:
        event = json.loads(line)
        if event["type"] == "tool/call":
            payload = event["payload"]
            calls.append(f"{payload.get('name')}({json.dumps(payload.get('arguments'), ensure_ascii=False)[:80]})")
    print(f"\n{row['id']}: {len(calls)} вызовов")
    for call in calls:
        print("  ", call)
