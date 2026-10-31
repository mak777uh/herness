# ADR-0038. Конфиг своего ядра: минимальный + ФС + песочница + укрепление

**Статус:** принято по замеру 31.10.2026. Дополняет ADR-0037 (своя сборка 6.18.60): там выбрана
**линия**, здесь — **что включать**.

## Решение

Собираем вариант **C**: `tinyconfig` + обязательное для харнесса + укрепление.

Обязательное:

- запуск и вывод: `64BIT`, `PRINTK`, `BINFMT_ELF`, `TTY`, `SERIAL_8250_CONSOLE`, `BLK_DEV_INITRD`, `RD_GZIP`;
- ФС для журнала: `BLOCK`, `EXT4_FS`, `TMPFS`, `DEVTMPFS`, `VIRTIO`, `VIRTIO_PCI`, `VIRTIO_BLK`;
- песочница: `SECURITY`, `SECURITY_LANDLOCK`, `SECCOMP`, `LSM=landlock,capability,yama`, `NAMESPACES`
  (`USER`, `PID`, `NET`, `UTS`, `IPC`), `CGROUPS`;
- системные вызовы Rust: `FUTEX`, `EPOLL`, `SIGNALFD`, `TIMERFD`, `EVENTFD`, `SHMEM`, `UNIX`.

Укрепление: `STRICT_KERNEL_RWX`, `INIT_ON_ALLOC_DEFAULT_ON`, `INIT_ON_FREE_DEFAULT_ON`,
`SLAB_FREELIST_RANDOM`, `SLAB_FREELIST_HARDENED`, `HARDENED_USERCOPY`, `FORTIFY_SOURCE`,
`STACKPROTECTOR_STRONG`, `VMAP_STACK`, `RANDOMIZE_BASE`, `RANDOMIZE_MEMORY`, `PAGE_TABLE_ISOLATION`,
`X86_SMEP`, `X86_SMAP`, `BUG_ON_DATA_CORRUPTION`, `SHUFFLE_PAGE_ALLOCATOR`.

Выключено осознанно: `SMP` (на этой машине вызывает панику IO-APIC), `MODULES` (0 модулей), сеть,
USB, звук, GPU, отладка.

## Замер

| вариант | размер | до init | ABI | namespaces |
|---|---:|---:|---:|---|
| A: голый | 0,97 МБ | 0,62–1,29 с | 7 | не проверены |
| B: + ФС и песочница | 1,40 МБ | 1,31 с | 7 | mount ok, user ok |
| **C: B + укрепление** | **1,44 МБ** | 1,46 с | 7 | **mount ok, user ok** |

## Следствия

1. Конфиг — в репозитории: `core-rs/kernel/config-6.18.60-hardened`; изменение опций видно в diff.
2. `build.ps1` по умолчанию берёт `vmlinuz-own` (вариант C); `HS_KERNEL` переключает.
3. Появилась возможность следующего шага: журнал на ext4-разделе и правила песочницы — механизмы уже
   есть и проверены.

## Риски

- Укрепление не проверялось эксплуатацией: цена для атакующего не измерена.
- Конфиг минимален по замыслу, но не отревьюен построчно.
- `SMP=n` — осознанное сужение: на многоядерной машине это ограничит параллелизм внутри системы.
