#!/usr/bin/env bash
# Сколько занимают части мастерской: что можно удалить без потери сборки.
set -u
echo "--- крупное ---"
du -sh /home/ilya/.cargo /home/ilya/.rustup /home/ilya/work /home/ilya/work/boot /home/ilya/work/herness 2>/dev/null
echo "--- кэш apt ---"
du -sh /var/cache/apt/archives 2>/dev/null
echo "--- /tmp ---"
du -sh /tmp 2>/dev/null
echo "--- всего в системе ---"
df -h / | tail -1
