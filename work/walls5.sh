#!/usr/bin/env bash
# Что нужно, чтобы закрыть оставшиеся пять стен.
# 1. SMEP/SMAP — проверить, включены ли они на самом деле в собранном ядре (не опцией, а кодом).
# 2. PERF_EVENTS_RESTRICT — sysctl, можно выставить в init.
# 3. LOCK_DOWN — что требует и сколько стоит.
cd /root/linux-6.18.60 || exit 2
OUT=/mnt/c/111/herness/work/walls5.txt
: > "$OUT"

echo '=== 1. SMEP/SMAP: включены ли в сборке' >> "$OUT"
grep -E '^CONFIG_X86_64=' .config >> "$OUT"
grep -rn 'setup_smep' arch/x86/kernel/cpu/common.c | head -2 >> "$OUT"
echo '--- строки, где включается SMEP:' >> "$OUT"
sed -n '360,380p' arch/x86/kernel/cpu/common.c >> "$OUT"

echo '=== 2. PERF_EVENTS_RESTRICT: sysctl по умолчанию' >> "$OUT"
grep -n 'sysctl_perf_event_paranoid' kernel/events/core.c | head -3 >> "$OUT"

echo '=== 3. LOCK_DOWN: что требует' >> "$OUT"
grep -rn -A10 'config SECURITY_LOCKDOWN_LSM' security/Kconfig 2>/dev/null | head -14 >> "$OUT"
grep -rn 'config LOCK_DOWN_KERNEL_FORCE' security/Kconfig 2>/dev/null >> "$OUT"

echo '=== 4. SECURITY_LOCKDOWN_LSM_EARLY' >> "$OUT"
grep -rn 'SECURITY_LOCKDOWN_LSM_EARLY' security/Kconfig 2>/dev/null | head -3 >> "$OUT"
echo DONE >> "$OUT"
