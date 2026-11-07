#!/usr/bin/env bash
# LOCK_DOWN: где определён и что требует. И как проверить SMEP/SMAP на живой комнате.
cd /root/linux-6.18.60 || exit 2
OUT=/mnt/c/111/herness/work/lockdown.txt
: > "$OUT"

echo '=== где определён SECURITY_LOCKDOWN_LSM' >> "$OUT"
grep -rln 'SECURITY_LOCKDOWN_LSM' --include='Kconfig*' . 2>/dev/null | head -3 >> "$OUT"
echo '--- определение:' >> "$OUT"
grep -rn -A12 'config SECURITY_LOCKDOWN_LSM$' --include='Kconfig*' . 2>/dev/null | head -16 >> "$OUT"

echo '=== LOCK_DOWN_KERNEL_FORCE' >> "$OUT"
grep -rn -A10 'config LOCK_DOWN_KERNEL_FORCE' --include='Kconfig*' . 2>/dev/null | head -14 >> "$OUT"

echo '=== размер: сколько кода добавляет lockdown' >> "$OUT"
ls security/lockdown/*.c 2>/dev/null | head -3 >> "$OUT"
wc -l security/lockdown/*.c 2>/dev/null | tail -2 >> "$OUT"
echo DONE >> "$OUT"
