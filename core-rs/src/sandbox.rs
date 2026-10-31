//! Песочница процесса: то, чего Landlock ABI 7 не умеет.
//!
//! Наше ядро 6.18.60 объявляет только `LANDLOCK_ACCESS_NET_BIND_TCP` и `CONNECT_TCP` — прав на UDP
//! нет (UDP появляется в ABI 10, ядро 7.2). Значит «сеть в песочнице» без отдельного правила
//! означала бы неограниченный UDP: дыру, которую нечем закрыть на уровне Landlock.
//!
//! Правило: запрещаем `socket(AF_INET, SOCK_DGRAM, …)`, считая тип с маской `SOCK_TYPE_MASK`.
//! Маска обязательна: `SOCK_CLOEXEC` и `SOCK_NONBLOCK` лежат в том же аргументе, и проверка на
//! точное равенство пропустила бы `SOCK_DGRAM | SOCK_CLOEXEC`.
//!
//! Чего это правило НЕ делает: не мешает использовать уже открытые дескрипторы, переданные
//! процессу, и не запрещает `socketpair`. Это следующий слой (и он должен проверяться отдельно).

#[cfg(all(target_os = "linux", target_arch = "x86_64"))]
mod platform {
    use std::ffi::c_void;

    const BPF_LD_W_ABS: u16 = 0x20;
    const BPF_ALU_AND_K: u16 = 0x54;
    const BPF_JEQ_K: u16 = 0x15;
    const BPF_RET_K: u16 = 0x06;

    const SECCOMP_RET_ALLOW: u32 = 0x7fff_0000;
    const SECCOMP_RET_ERRNO: u32 = 0x0005_0000;
    const AUDIT_ARCH_X86_64: u32 = 0xc000_003e;

    const PR_SET_NO_NEW_PRIVS: libc::c_int = 38;
    const PR_SET_SECCOMP: libc::c_int = 22;
    const SECCOMP_MODE_FILTER: libc::c_ulong = 2;

    const AF_INET: u32 = 2;
    const AF_INET6: u32 = 10;
    const SOCK_DGRAM: u32 = 2;
    const SOCK_RAW: u32 = 3;
    const SOCK_TYPE_MASK: u32 = 0xF;
    const EACCES: u32 = 13;

    /// Собрать программу фильтра: запретить UDP и raw-сокеты для AF_INET/AF_INET6, остальное
    /// разрешить. Two семейства и два типа, потому что «только DGRAM» оставило бы raw-сокет —
    /// а в гостевой системе мы root, и CAP_NET_RAW у нас есть.
    fn program() -> Vec<libc::sock_filter> {
        let ins = |code: u16, jt: u8, jf: u8, k: u32| libc::sock_filter { code, jt, jf, k };
        vec![
            // 0..2: чужой ABI — вежливый ENOSYS, а не тихая дыра
            ins(BPF_LD_W_ABS, 0, 0, 4),
            ins(BPF_JEQ_K, 1, 0, AUDIT_ARCH_X86_64),
            ins(BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO | 38),
            // 3..4: интересует только socket(2)
            ins(BPF_LD_W_ABS, 0, 0, 0),
            ins(BPF_JEQ_K, 0, 9, libc::SYS_socket as u32),
            // 5..7: семейство AF_INET или AF_INET6
            ins(BPF_LD_W_ABS, 0, 0, 16),
            ins(BPF_JEQ_K, 1, 0, AF_INET),
            ins(BPF_JEQ_K, 0, 6, AF_INET6),
            // 8..10: маска типа (SOCK_CLOEXEC живёт в том же аргументе)
            ins(BPF_LD_W_ABS, 0, 0, 24),
            ins(BPF_ALU_AND_K, 0, 0, SOCK_TYPE_MASK),
            ins(BPF_JEQ_K, 0, 1, SOCK_DGRAM),
            ins(BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO | EACCES),
            // 12..14: raw-сокеты тоже закрыты
            ins(BPF_JEQ_K, 0, 1, SOCK_RAW),
            ins(BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO | EACCES),
            ins(BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW),
        ]
    }

    /// Установить фильтр на текущий процесс и всех его потомков.
    pub fn deny_udp() -> Result<(), String> {
        let mut filters = program();
        let prog = libc::sock_fprog {
            len: filters.len() as u16,
            filter: filters.as_mut_ptr(),
        };
        // SAFETY: prctl получает валидные указатели; фильтр и его буфер живут до конца вызова.
        unsafe {
            if libc::prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 {
                return Err(format!("no_new_privs: {}", std::io::Error::last_os_error()));
            }
            let rc = libc::prctl(
                PR_SET_SECCOMP,
                SECCOMP_MODE_FILTER,
                &prog as *const libc::sock_fprog as *const c_void,
                0,
                0,
            );
            if rc != 0 {
                return Err(format!("seccomp: {}", std::io::Error::last_os_error()));
            }
        }
        Ok(())
    }

/// Проба: установить правило и проверить, что UDP (IPv4/IPv6), UDP с флагом `SOCK_CLOEXEC` и
/// raw-сокеты закрыты, а TCP остаётся рабочим.
    pub fn probe() -> Result<[(&'static str, bool); 5], String> {
    deny_udp()?;
        let open = |domain: i32, kind: i32| -> bool {
        // SAFETY: вызов socket без указателей; дескриптор закрывается сразу.
        let fd = unsafe { libc::socket(domain, kind, 0) };
        if fd >= 0 {
            unsafe { libc::close(fd) };
            true
        } else {
            false
        }
    };
    Ok([
        ("udp4 закрыт", !open(libc::AF_INET, libc::SOCK_DGRAM)),
        ("udp6 закрыт", !open(libc::AF_INET6, libc::SOCK_DGRAM)),
        (
            "udp с CLOEXEC закрыт",
            !open(libc::AF_INET, libc::SOCK_DGRAM | libc::SOCK_CLOEXEC),
        ),
        ("raw закрыт", !open(libc::AF_INET, libc::SOCK_RAW)),
        ("tcp открыт", open(libc::AF_INET, libc::SOCK_STREAM)),
    ])
}
}

/// Ядро не умеет фильтровать системные вызовы — это не ошибка нашего кода.
pub fn unsupported(error: &str) -> bool {
    ["Function not implemented", "Invalid argument", "Operation not supported"]
        .iter()
        .any(|marker| error.contains(marker))
}

/// Применить правило к дочернему процессу ДО exec.
///
/// Внимание: в нашем ядре этот путь не работает (F-0024). `Command::pre_exec` уводит spawn на
/// путь fork+exec, и spawn возвращает `ENOSYS` ещё до того, как замыкание выполнится (метки,
/// поставленные изнутри замыкания, не появляются). Причина расхождения с рабочим `fork()` не
/// установлена, поэтому инструменты переводятся на `harden_self()`: ребёнок ставит фильтр сам
/// первой строкой. Функция оставлена для проверки на другой системе, но в цикле не используется.
pub fn harden_command(command: &mut std::process::Command) {
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        // SAFETY: в pre_exec разрешены только вызовы, безопасные после fork: prctl и запись errno.
        unsafe {
            command.pre_exec(|| {
                deny_udp().map_err(|error| std::io::Error::new(std::io::ErrorKind::Other, error))
            });
        }
    }
    #[cfg(not(unix))]
    {
        let _ = command;
    }
}

/// Поставить правило на самого себя: то, что делает процесс инструмента первой строкой.
///
/// Так фильтр гарантированно действует до того, как инструмент прочитает первый файл, и не
/// зависит от `pre_exec`. Цена: между `exec` и установкой фильтра есть несколько инструкций
/// кода, который мы сами же и написали (не чужого).
pub fn harden_self() -> Result<(), String> {
    deny_udp()
}

#[cfg(not(all(target_os = "linux", target_arch = "x86_64")))]
mod platform {
    pub fn deny_udp() -> Result<(), String> {
        Err("seccomp-правило есть только для linux/x86_64".to_string())
    }

    pub fn probe() -> Result<[(&'static str, bool); 5], String> {
        Err("проба песочницы есть только для linux/x86_64".to_string())
    }
}

pub use platform::{deny_udp, probe};


