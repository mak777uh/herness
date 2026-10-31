//! Минимальный CLI ядра: печать файла, проверка цепочки журнала и режим init.
//! Без аргументов (как PID 1) работает инициализатором: проверяет песочницу и меряет порождение
//! процессов — чтобы решение «VM или голое железо» опиралось на числа, а не на вкус.

use std::env;
use std::ffi::CStr;
use std::fs;
use std::process::{Command, ExitCode};
use std::thread;
use std::time::Duration;

fn kernel_release() -> String {
    // SAFETY: utsname заполняется ядром.
    unsafe {
        let mut name: libc::utsname = std::mem::zeroed();
        if libc::uname(&mut name) != 0 {
            return "неизвестно".to_string();
        }
        CStr::from_ptr(name.release.as_ptr()).to_string_lossy().into_owned()
    }
}

fn landlock_abi() -> i64 {
    const SYS_LANDLOCK_CREATE_RULESET: libc::c_long = 444;
    const VERSION_FLAG: libc::c_uint = 1;
    // SAFETY: запрос версии не создаёт объектов.
    unsafe {
        let result = libc::syscall(
            SYS_LANDLOCK_CREATE_RULESET,
            std::ptr::null::<libc::c_void>(),
            0usize,
            VERSION_FLAG,
        );
        if result < 0 { 0 } else { result as i64 }
    }
}

/// Проверяем не опцию в конфиге, а работу механизма.
fn unshare_works(flag: libc::c_int) -> bool {
    // SAFETY: unshare сообщает результат кодом возврата.
    unsafe { libc::unshare(flag) == 0 }
}

/// Цена порождения процесса: fork+exec себя же с короткой командой.
fn spawn_cost(iterations: u32) {
    let started = hs_core::clock::uptime_seconds();
    let mut ok = 0u32;
    for _ in 0..iterations {
        if let Ok(status) = Command::new("/init").arg("seal").arg("/method.md").status() {
            if status.success() {
                ok += 1;
            }
        }
    }
    let elapsed = hs_core::clock::uptime_seconds() - started;
    println!(
        "порождение процесса: {ok}/{iterations} за {elapsed:.2} с = {:.1} мс на запуск",
        elapsed * 1000.0 / iterations as f64
    );
}


/// Смонтировать /dev/vda как ext4 в /mnt. Возвращает true при успехе.
fn mount_filesystem(source: &str, target: &str, fstype: &str) -> std::io::Result<()> {
    let source_c = std::ffi::CString::new(source).unwrap();
    let target_c = std::ffi::CString::new(target).unwrap();
    let fstype_c = std::ffi::CString::new(fstype).unwrap();
    // SAFETY: указатели на валидные C-строки живут до конца вызова.
    let rc = unsafe {
        libc::mount(source_c.as_ptr(), target_c.as_ptr(), fstype_c.as_ptr(), 0, std::ptr::null())
    };
    if rc == 0 {
        Ok(())
    } else {
        Err(std::io::Error::last_os_error())
    }
}

fn mount_disk() -> bool {
    // Сначала devtmpfs: без /dev узел диска не существует.
    match mount_filesystem("devtmpfs", "/dev", "devtmpfs") {
        Ok(()) => println!("dev: devtmpfs смонтирован"),
        Err(error) => println!("dev: devtmpfs не смонтирован ({error})"),
    }
    match mount_filesystem("/dev/vda", "/mnt", "ext4") {
        Ok(()) => true,
        Err(error) => {
            println!("mount /dev/vda -> /mnt: {error}");
            false
        }
    }
}

/// Режим из /mode: write — писать журнал на диск, check — читать и отчитываться.
fn journal_durability() {
    let mode = fs::read_to_string("/mode").unwrap_or_default();
    if !mount_disk() {
        println!("диск: не смонтировать /dev/vda");
        return;
    }
    println!("диск: ext4 смонтирован в /mnt");
    let path = "/mnt/journal.bin";
    let mode_text = mode.trim().to_string();
    if mode_text == "write" || mode_text == "batch" {
        let Ok(mut journal) = hs_core::journal::Journal::open(path) else {
            println!("журнал: не открыть");
            return;
        };
        let batch_policy = mode_text == "batch";
        let started = hs_core::clock::uptime_seconds();
        let mut records = 0u64;
        let mut commits = 0u64;
        for index in 0..200_000u64 {
            if journal.append(format!("event-{index}").as_bytes(), hs_core::journal::Kind::Data).is_err() {
                break;
            }
            records += 1;
            // коммит каждые 10 записей — граница «подтверждено»
            if records % 10 == 0 {
                if journal.append(b"commit", hs_core::journal::Kind::Commit).is_err() {
                    break;
                }
                if !batch_policy && journal.sync().is_err() {
                    break;
                }
                commits += 1;
                if commits % 5 == 0 {
                    println!("подтверждено: commit-{commits} при {records} записях");
                }
            }
            // пакетная политика: fsync не чаще, чем раз в 32 записи
            if batch_policy && records % 32 == 0 && journal.sync().is_err() {
                break;
            }
        }
        if journal.sync().is_ok() {
            println!("финал: sync выполнен");
        }
        let elapsed = hs_core::clock::uptime_seconds() - started;
        println!(
            "записано: записей {records}, коммитов {commits} за {elapsed:.2} с = {:.0} записей/с",
            records as f64 / elapsed.max(0.001)
        );
    } else {
        match hs_core::journal::Journal::open(path) {
            Ok(journal) => match journal.report() {
                Ok(report) => println!(
                    "журнал на диске: записей {}, коммитов {}, хвост {} байт, статус {}",
                    report.records, report.committed, report.tail_bytes, report.status
                ),
                Err(error) => println!("журнал: ошибка отчёта {error}"),
            },
            Err(error) => println!("журнал: не открыть {error}"),
        }
    }
}

fn init_mode() -> ExitCode {
    println!("hs-core: я инициализировал систему сам, PID 1");
    println!("ядро: {}", kernel_release());
    println!("landlock ABI: {}", landlock_abi());
    println!("время до init: {:.2} с", hs_core::clock::uptime_seconds());
    let method = fs::read_to_string("/method.md").unwrap_or_default();
    println!("печать /method.md: {}", hs_core::seal_hash(&method));
    spawn_cost(20);
    journal_durability();
    // Проба namespaces идёт последней: unshare(CLONE_NEWUSER) лишает прав на mount.
    let mount_ns = unshare_works(libc::CLONE_NEWNS);
    let user_ns = unshare_works(libc::CLONE_NEWUSER);
    println!(
        "namespaces: mount {}, user {}",
        if mount_ns { "ok" } else { "нет" },
        if user_ns { "ok" } else { "нет" }
    );

    // Проверка журнала в этой системе: три записи и коммит, затем чтение.
    if let Ok(mut journal) = hs_core::journal::Journal::open("/journal.bin") {
        for index in 0..3 {
            let _ = journal.append(format!("event-{index}").as_bytes(), hs_core::journal::Kind::Data);
        }
        let _ = journal.append(b"commit", hs_core::journal::Kind::Commit);
        let _ = journal.sync();
        if let Ok(report) = journal.report() {
            println!(
                "журнал: записей {}, коммитов {}, хвост {} байт, статус {}",
                report.records, report.committed, report.tail_bytes, report.status
            );
        }
    }
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
        Some("journal") => {
            let Some(path) = args.get(1) else {
                eprintln!("usage: hs-core journal <файл> [payload]");
                return ExitCode::from(2);
            };
            match hs_core::journal::Journal::open(path) {
                Ok(mut journal) => {
                    if let Some(payload) = args.get(2) {
                        let _ = journal.append(payload.as_bytes(), hs_core::journal::Kind::Data);
                        let _ = journal.append(b"commit", hs_core::journal::Kind::Commit);
                        let _ = journal.sync();
                    }
                    match journal.report() {
                        Ok(report) => {
                            println!(
                                "записей: {}, коммитов: {}, хвост: {} байт, статус: {}",
                                report.records, report.committed, report.tail_bytes, report.status
                            );
                            ExitCode::SUCCESS
                        }
                        Err(error) => {
                            eprintln!("не проверить журнал: {error}");
                            ExitCode::from(3)
                        }
                    }
                }
                Err(error) => {
                    eprintln!("не открыть журнал: {error}");
                    ExitCode::from(3)
                }
            }
        }
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
