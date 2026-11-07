#!/usr/bin/env bash
# Почему не включаются SMEP/SMAP, SLAB_FREELIST_*, RANDOM_KMALLOC_CACHES, PERF_EVENTS_RESTRICT.
cd /root/linux-6.18.60 || exit 2
OUT=/mnt/c/111/herness/work/why2.txt
: > "$OUT"

echo '=== SMEP/SMAP: где определены' >> "$OUT"
grep -rn 'SMEP' arch/x86/ 2>/dev/null | grep -i kconfig | head -5 >> "$OUT"
grep -rn 'SMAP' arch/x86/ 2>/dev/null | grep -i kconfig | head -5 >> "$OUT"

echo '=== SLAB_FREELIST_RANDOM (mm/Kconfig 203-230)' >> "$OUT"
sed -n '203,230p' mm/Kconfig >> "$OUT"

echo '=== RANDOM_KMALLOC_CACHES (mm/Kconfig 261-270)' >> "$OUT"
sed -n '261,270p' mm/Kconfig >> "$OUT"

echo '=== PERF_EVENTS_RESTRICT' >> "$OUT"
grep -rn 'PERF_EVENTS_RESTRICT' --include=Kconfig* . 2>/dev/null | head -3 >> "$OUT"

echo '=== текущий SLAB/SLUB' >> "$OUT"
grep -E '^CONFIG_(SLAB|SLUB|SLOB)=' .config >> "$OUT" || echo 'ни один не задан' >> "$OUT"
echo DONE >> "$OUT"
