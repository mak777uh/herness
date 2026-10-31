#!/usr/bin/env bash
# Своя сборка ядра 6.18.60: base + ФС/песочница (+ укрепление). y -> --enable, n -> --disable.
set -eu
cd /root/linux-6.18.60

BASE="
CONFIG_64BIT=y
CONFIG_X86_64=y
CONFIG_PRINTK=y
CONFIG_BINFMT_ELF=y
CONFIG_MULTIUSER=y
CONFIG_TTY=y
CONFIG_SERIAL_8250=y
CONFIG_SERIAL_8250_CONSOLE=y
CONFIG_BLK_DEV_INITRD=y
CONFIG_RD_GZIP=y
CONFIG_SECURITY=y
CONFIG_SECURITY_LANDLOCK=y
CONFIG_LSM=landlock,capability,yama
CONFIG_SECCOMP=y
CONFIG_PROC_FS=y
CONFIG_SYSFS=y
CONFIG_SMP=n
CONFIG_MODULES=n
CONFIG_DEBUG_INFO=n
"

FS_NS="
CONFIG_PCI=y
CONFIG_VIRTIO_MENU=y
CONFIG_BLOCK=y
CONFIG_EXT4_FS=y
CONFIG_EXT4_USE_FOR_EXT2=y
CONFIG_TMPFS=y
CONFIG_VIRTIO=y
CONFIG_VIRTIO_PCI=y
CONFIG_VIRTIO_BLK=y
CONFIG_NAMESPACES=y
CONFIG_USER_NS=y
CONFIG_PID_NS=y
CONFIG_NET_NS=y
CONFIG_UTS_NS=y
CONFIG_IPC_NS=y
CONFIG_CGROUPS=y
CONFIG_CGROUP_SCHED=y
CONFIG_DEVTMPFS=y
CONFIG_DEVTMPFS_MOUNT=y
CONFIG_FUTEX=y
CONFIG_EPOLL=y
CONFIG_SIGNALFD=y
CONFIG_TIMERFD=y
CONFIG_EVENTFD=y
CONFIG_SHMEM=y
CONFIG_UNIX=y
"

HARDEN="
CONFIG_STRICT_KERNEL_RWX=y
CONFIG_INIT_ON_ALLOC_DEFAULT_ON=y
CONFIG_INIT_ON_FREE_DEFAULT_ON=y
CONFIG_SLAB_FREELIST_RANDOM=y
CONFIG_SLAB_FREELIST_HARDENED=y
CONFIG_HARDENED_USERCOPY=y
CONFIG_FORTIFY_SOURCE=y
CONFIG_STACKPROTECTOR_STRONG=y
CONFIG_VMAP_STACK=y
CONFIG_RANDOMIZE_BASE=y
CONFIG_RANDOMIZE_MEMORY=y
CONFIG_BUG_ON_DATA_CORRUPTION=y
CONFIG_SHUFFLE_PAGE_ALLOCATOR=y
CONFIG_PAGE_TABLE_ISOLATION=y
CONFIG_X86_SMAP=y
CONFIG_X86_SMEP=y
"

apply() {
  for opt in $1; do
    key="${opt%%=*}"
    value="${opt#*=}"
    case "$value" in
      y) ./scripts/config --enable "$key" ;;
      n) ./scripts/config --disable "$key" ;;
      *) ./scripts/config --set-str "$key" "$value" ;;
    esac
  done
}

build_variant() {
  name="$1"
  extra="$2"
  echo "=== вариант $name ==="
  make -s tinyconfig
  apply "$BASE"
  apply "$extra"
  make -s olddefconfig
  make -s -j"$(nproc)" bzImage 2>&1 | tail -2
  cp arch/x86/boot/bzImage "/mnt/c/111/herness/core-rs/boot/vmlinuz-$name"
  size=$(stat -c %s arch/x86/boot/bzImage)
  yes_count=$(grep -c '=y' .config)
  virtio=$(grep -c '^CONFIG_VIRTIO' .config || true)
  echo "$name: $size байт, =y $yes_count, VIRTIO-опций $virtio"
}

build_variant own-a "$FS_NS"
build_variant own-c "$FS_NS $HARDEN"
cp "/mnt/c/111/herness/core-rs/boot/vmlinuz-own-c" "/mnt/c/111/herness/core-rs/boot/vmlinuz-own"
cp .config /mnt/c/111/herness/core-rs/kernel/config-6.18.60-hardened
echo "готово"
