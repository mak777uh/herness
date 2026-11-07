#!/usr/bin/env bash
# Закрываем оставшиеся стены:
#   1. SECURITY_LOCKDOWN_LSM + EARLY + LOCK_DOWN_KERNEL_FORCE_INTEGRITY — 173 строки кода;
#   2. PERF_EVENTS_RESTRICT — в 6.18 это sysctl; выставляем paranoid=3 через cmdline ядра.
# SMEP/SMAP включаются кодом по возможностям CPU — проверяем на живой комнате отдельно.
cd /root/linux-6.18.60 || exit 2
OUT=/mnt/c/111/herness/work/walls-close.txt
: > "$OUT"

set_opt() {
  name="$1"; value="$2"
  if grep -q "^CONFIG_${name}=" .config; then
    sed -i "s|^CONFIG_${name}=.*|CONFIG_${name}=${value}|" .config
  elif grep -q "^# CONFIG_${name} is not set" .config; then
    if [ "$value" = "y" ]; then
      sed -i "s|^# CONFIG_${name} is not set|CONFIG_${name}=y|" .config
    fi
  else
    if [ "$value" = "y" ]; then
      echo "CONFIG_${name}=y" >> .config
    fi
  fi
}

set_opt SECURITY_LOCKDOWN_LSM y
set_opt SECURITY_LOCKDOWN_LSM_EARLY y
set_opt LOCK_DOWN_KERNEL_FORCE_INTEGRITY y
set_opt LOCK_DOWN_KERNEL_FORCE_NONE n

# LSM-порядок: lockdown обязан идти первым.
sed -i 's|^CONFIG_LSM=.*|CONFIG_LSM="lockdown,landlock,capability,yama"|' .config
grep -q '^CONFIG_LSM=' .config || echo 'CONFIG_LSM="lockdown,landlock,capability,yama"' >> .config

make -s olddefconfig >> "$OUT" 2>&1
echo '=== после olddefconfig' >> "$OUT"
for o in SECURITY_LOCKDOWN_LSM SECURITY_LOCKDOWN_LSM_EARLY LOCK_DOWN_KERNEL_FORCE_INTEGRITY; do
  printf '%s: ' "$o" >> "$OUT"
  grep -E "^CONFIG_${o}=" .config >> "$OUT" || echo 'НЕТ' >> "$OUT"
done
printf 'LSM: ' >> "$OUT"
grep -E '^CONFIG_LSM=' .config >> "$OUT"
echo DONE >> "$OUT"
