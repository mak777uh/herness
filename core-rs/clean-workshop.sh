#!/usr/bin/env bash
# Чистка мастерской: кэши, артефакты сборки. Сам toolchain и qemu остаются.
set -u
before=$(df -k / | awk 'NR==2 {print $3}')
apt-get clean
rm -rf /var/cache/apt/archives/*.deb 2>/dev/null
su - ilya -c 'cd /home/ilya/work/herness/core-rs && ~/.cargo/bin/cargo clean 2>/dev/null; rm -rf /home/ilya/work/boot/rootfs' || true
rm -rf /tmp/miniroot /tmp/t.md /tmp/landlock-probe /tmp/landlock-probe.c 2>/dev/null
after=$(df -k / | awk 'NR==2 {print $3}')
echo "занято до: $before КБ, после: $after КБ, освобождено: $(( (before - after) / 1024 )) МБ"
df -h / | tail -1
