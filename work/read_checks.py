from pathlib import Path

t = Path("bin/hs.py").read_text(encoding="utf-8")
i = t.find('("секреты", gate_secrets)')
print(t[max(0, i - 400):i + 2200])
