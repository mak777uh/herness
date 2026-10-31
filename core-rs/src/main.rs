//! Минимальный CLI ядра: печать файла, проверка цепочки журнала и режим init.
//! Без аргументов (как PID 1) работает инициализатором и проверяет песочницу делом.

use std::env;
use std::ffi::CStr;
use std::fs;
use std::process::ExitCode;
use std::thread;
use std::time::Duration;

fn kernel_release() -> String {
    // SAFETY: utsname — обычная структура, заполняется ядром.
    unsafe {
        let mut name: libc::utsname = std::mem::zeroed();
        if libc::uname(&mut name) != 0 {
            return "неизвестно".to_string();
        }
        CStr::from_ptr(name.release.as_ptr())
            .to_string_lossy()
            .into_owned()
    }
}

fn landlock_abi() -> i64 {
    const SYS_LANDLOCK_CREATE_RULESET: libc::c_long = 444;
    const VERSION_FLAG: libc::c_uint = 1;
    // SAFETY: запрос версии не создаёт объектов и не требует указателя.
    unsafe {
        let result = libc::syscall(
            SYS_LANDLOCK_CREATE_RULESET,
            std::ptr::null::<libc::c_void>(),
            0usize,
            VERSION_FLAG,
        );
        if result < 0 {
            0
        } else {
            result as i64
        }
    }
}

/// Проверяем не опцию в конфиге, а работу механизма.
fn unshare_works(flag: libc::c_int) -> bool {
    // SAFETY: unshare сам сообщает об успехе кодом возврата.
    unsafe { libc::unshare(flag) == 0 }
}

fn init_mode() -> ExitCode {
    println!("hs-core: я инициализировал систему сам, PID 1");
    println!("ядро: {}", kernel_release());
    println!("landlock ABI: {}", landlock_abi());
    println!("время до init: {:.2} с", hs_core::clock::uptime_seconds());
    let mount_ns = unshare_works(libc::CLONE_NEWNS);
    let user_ns = unshare_works(libc::CLONE_NEWUSER);
    println!(
        "namespaces: mount {}, user {}",
        if mount_ns { "ok" } else { "нет" },
        if user_ns { "ok" } else { "нет" }
    );
    let method = fs::read_to_string("/method.md").unwrap_or_default();
    println!("печать /method.md: {}", hs_core::seal_hash(&method));
    println!("hs-core: система жива, жду");
    loop {
        thread::sleep(Duration::from_secs(3600));
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        None => init_mode(),
        Some("init") => init_mode(),
        Some("seal") => {
            let Some(path) = args.get(1) else {
                eprintln!("usage: hs-core seal <файл>");
                return ExitCode::from(2);
            };
            match fs::read_to_string(path) {
                Ok(text) => {
                    println!("{}", hs_core::seal_hash(&text));
                    ExitCode::SUCCESS
                }
                Err(error) => {
                    eprintln!("не прочитать {path}: {error}");
                    ExitCode::from(2)
                }
            }
        }
        Some("chain") => {
            let Some(path) = args.get(1) else {
                eprintln!("usage: hs-core chain <events.jsonl>");
                return ExitCode::from(2);
            };
            let body = match fs::read_to_string(path) {
                Ok(text) => text,
                Err(error) => {
                    eprintln!("не прочитать {path}: {error}");
                    return ExitCode::from(2);
                }
            };
            let mut events = Vec::new();
            for line in body.lines().filter(|line| !line.trim().is_empty()) {
                match serde_json::from_str::<serde_json::Value>(line) {
                    Ok(value) => events.push(value),
                    Err(error) => {
                        eprintln!("битая строка: {error}");
                        return ExitCode::from(3);
                    }
                }
            }
            let (last_prev, last_hash) = hs_core::chain(&events)
                .pop()
                .unwrap_or((String::new(), String::new()));
            println!("событий: {}\nprev: {last_prev}\nhash: {last_hash}", events.len());
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("hs-core: seal <файл> | chain <events.jsonl> | init");
            ExitCode::from(2)
        }
    }
}
