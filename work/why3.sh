#!/usr/bin/env bash
# Причина найдена: SLUB_TINY=y отключает рандомизацию кучи. Смотрим, чем задан SLUB_TINY
# и где SMEP/SMAP в этой версии ядра.
cd /root/linux-6.18.60 || exit 2
OUT=/mnt/c/111/herness/work/why3.txt
: > "$OUT"

echo '=== SLUB_TINY' >> "$OUT"
grep -rn -A8 'config SLUB_TINY' mm/Kconfig* 2>/dev/null >> "$OUT"
printf 'текущее: ' >> "$OUT"
grep -E '^CONFIG_SLUB_TINY=' .config >> "$OUT" || echo 'НЕТ' >> "$OUT"

echo '=== SMEP/SMAP в исходниках (любое упоминание в Kconfig)' >> "$OUT"
grep -rln 'SMEP' --include='Kconfig*' . 2>/dev/null | head -5 >> "$OUT"
grep -rn 'SMEP' arch/x86/Kconfig.cpu 2>/dev/null | head -5 >> "$OUT"

echo '=== PERF_EVENTS_RESTRICT' >> "$OUT"
grep -rln 'PERF_EVENTS_RESTRICT' --include='Kconfig*' . 2>/dev/null | head -3 >> "$OUT"
echo DONE >> "$OUT"
