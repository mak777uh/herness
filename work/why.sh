#!/usr/bin/env bash
# Где определены SMEP/SMAP и от чего зависит RELOCATABLE; что говорит olddefconfig.
cd /root/linux-6.18.60 || exit 2
OUT=/mnt/c/111/herness/work/why.txt
: > "$OUT"

echo '=== RELOCATABLE' >> "$OUT"
sed -n '2065,2085p' arch/x86/Kconfig >> "$OUT"

echo '=== SMEP/SMAP (поиск по всем Kconfig)' >> "$OUT"
grep -rn 'X86_SMEP\|X86_SMAP' --include=Kconfig* . 2>/dev/null | head -10 >> "$OUT"

echo '=== текущие значения' >> "$OUT"
for o in RELOCATABLE RANDOMIZE_BASE X86_SMEP X86_SMAP; do
  printf '%s: ' "$o" >> "$OUT"
  grep -E "^CONFIG_${o}=" .config >> "$OUT" || echo 'НЕТ' >> "$OUT"
done

echo '=== olddefconfig предупреждения' >> "$OUT"
make -s olddefconfig 2>&1 | head -20 >> "$OUT"
echo DONE >> "$OUT"
