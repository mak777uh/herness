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

fn yes(value: bool) -> &'static str {
    if value {
        "ok"
    } else {
        "нет"
    }
}

/// Проба способностей: каждая строка — механизм, а не опция конфига.
///
/// Зачем: отсутствие опции иначе всплывает через неделю как загадочный `EPERM` внутри цикла.
/// Здесь оно видно строкой на загрузке. Про случайность отдельно: `GRND_NONBLOCK` не блокирует,
/// поэтому нехватка энтропии печатается как «нет», а не превращается в зависание.
fn capabilities() {
    let exec = Command::new("/init")
        .arg("seal")
        .arg("/method.md")
        .status()
        .map(|status| status.success())
        .unwrap_or(false);

    let pipe_ok = {
        let mut fds = [0i32; 2];
        // SAFETY: массив из двух дескрипторов — валидный буфер для pipe.
        unsafe { libc::pipe(fds.as_mut_ptr()) == 0 }
    };

    let fsync_ok = match fs::File::create("/cap.tmp") {
        Ok(mut file) => {
            use std::io::Write;
            file.write_all(b"cap").is_ok() && file.sync_all().is_ok()
        }
        Err(_) => false,
    };

    let clock_ok = hs_core::clock::uptime_seconds() > 0.0;

    let mut buffer = [0u8; 32];
    // SAFETY: буфер и его длина передаются согласованно; флаг NONBLOCK исключает зависание.
    let random = unsafe {
        libc::getrandom(
            buffer.as_mut_ptr() as *mut libc::c_void,
            buffer.len(),
            libc::GRND_NONBLOCK,
        )
    };
    let random_text = if random == buffer.len() as isize {
        "ok".to_string()
    } else if random < 0 {
        format!("нет ({})", std::io::Error::last_os_error())
    } else {
        format!("частично {random}")
    };

    // SAFETY: вызовы создания дескрипторов без аргументов-указателей.
    let epoll_ok = unsafe { libc::epoll_create1(0) } >= 0;
    let eventfd_ok = unsafe { libc::eventfd(0, 0) } >= 0;
    let memfd_ok = unsafe { libc::memfd_create(b"cap\0".as_ptr() as *const libc::c_char, 0) } >= 0;

    println!(
        "способы: exec {}, pipe {}, fsync {}, часы {}, случайность {}, epoll {}, eventfd {}, memfd {}",
        yes(exec),
        yes(pipe_ok),
        yes(fsync_ok),
        yes(clock_ok),
        random_text,
        yes(epoll_ok),
        yes(eventfd_ok),
        yes(memfd_ok)
    );
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

    // Скорость: ограниченное число записей, печатаем записей/с.
    if mode_text == "bench-write" || mode_text == "bench-batch" {
        let Ok(mut journal) = hs_core::journal::Journal::open(path) else {
            println!("журнал: не открыть");
            return;
        };
        let batch_policy = mode_text == "bench-batch";
        let limit = 2000u64;
        let started = hs_core::clock::uptime_seconds();
        let mut records = 0u64;
        for index in 0..limit {
            if journal.append(format!("event-{index}").as_bytes(), hs_core::journal::Kind::Data).is_err() {
                break;
            }
            records += 1;
            if records % 10 == 0 {
                let _ = journal.append(b"commit", hs_core::journal::Kind::Commit);
                if !batch_policy && journal.sync().is_err() {
                    break;
                }
            }
            if batch_policy && records % 32 == 0 && journal.sync().is_err() {
                break;
            }
        }
        let _ = journal.sync();
        let elapsed = hs_core::clock::uptime_seconds() - started;
        println!(
            "бенч {mode_text}: записей {records} за {elapsed:.2} с = {:.0} записей/с",
            records as f64 / elapsed.max(0.001)
        );
        return;
    }

    // Обрыв внутри записи: пишем валидный префикс, затем половину заголовка и ждём убийства.
    if mode_text == "tear" {
        let Ok(mut journal) = hs_core::journal::Journal::open(path) else {
            println!("журнал: не открыть");
            return;
        };
        for index in 0..5 {
            let _ = journal.append(format!("event-{index}").as_bytes(), hs_core::journal::Kind::Data);
        }
        let _ = journal.append(b"commit", hs_core::journal::Kind::Commit);
        let _ = journal.sync();
        // Половина заголовка следующей записи: len=30, seq=next — и ни байта тела.
        let mut partial = Vec::new();
        partial.extend_from_slice(&30u32.to_le_bytes());
        partial.extend_from_slice(&7u64.to_le_bytes());
        if let Ok(mut file) = std::fs::OpenOptions::new().append(true).open(path) {
            let _ = std::io::Write::write_all(&mut file, &partial[..10]);
            let _ = file.sync_all();
        }
        println!("tear: записано 5 записей + коммит, затем половина заголовка");
        println!("tear-ready: жду убийства");
        return;
    }

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
                Ok(report) => {
                    println!(
                        "журнал на диске: записей {}, коммитов {}, хвост {} байт, статус {}",
                        report.records, report.committed, report.tail_bytes, report.status
                    );
                    match hs_core::journal::quarantine(path) {
                        Ok(Some(target)) => println!("карантин: {}", target.display()),
                        Ok(None) => println!("карантин: не нужен"),
                        Err(error) => println!("карантин: ошибка {error}"),
                    }
                }
                Err(error) => println!("журнал: ошибка отчёта {error}"),
            },
            Err(error) => println!("журнал: не открыть {error}"),
        }
    }
}

fn report_loop(outcome: &hs_core::loopmod::Outcome) {
    println!(
        "цикл: шагов {}, вызовов {}, событий {}, журнал {} записей, коммитов {}, статус {}, порядок {}",
        outcome.steps,
        outcome.calls,
        outcome.events,
        outcome.records,
        outcome.commits,
        outcome.status,
        if outcome.order_ok() { "ok" } else { "НАРУШЕН" }
    );
    for problem in &outcome.problems {
        println!("  [!] порядок: {problem}");
    }
}

fn init_mode() -> ExitCode {
    println!("hs-core: я инициализировал систему сам, PID 1");
    println!("ядро: {}", kernel_release());
    println!("landlock ABI: {}", landlock_abi());
    println!("время до init: {:.2} с", hs_core::clock::uptime_seconds());
    let method = fs::read_to_string("/method.md").unwrap_or_default();
    println!("печать /method.md: {}", hs_core::seal_hash(&method));
    capabilities();
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

    // Цикл: в режиме loop прогоняем скелет цикла, иначе — синтетическую проверку журнала.
    let mode_text = fs::read_to_string("/mode").unwrap_or_default().trim().to_string();
    if mode_text == "loop" {
        let mut provider = hs_core::loopmod::Scripted::seal_method("/method.md");
        match hs_core::loopmod::run(
            std::path::Path::new("/journal.bin"),
            std::path::Path::new("/method.md"),
            &mut provider,
        ) {
            Ok(outcome) => report_loop(&outcome),
            Err(error) => println!("цикл: не запустился ({error})"),
        }
    } else if let Ok(mut journal) = hs_core::journal::Journal::open("/journal.bin") {
        // Проверка журнала в этой системе: три записи и коммит, затем чтение.
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
        Some("loop") => {
            // Цикл вне init: нужен, чтобы его можно было прогнать на обычной Linux-машине
            // (например, в WSL) и увидеть порядок событий без загрузки ядра.
            let journal = args.get(1).map(String::as_str).unwrap_or("/journal.bin");
            let method = args.get(2).map(String::as_str).unwrap_or("/method.md");
            let mut provider = hs_core::loopmod::Scripted::seal_method(method);
            match hs_core::loopmod::run(
                std::path::Path::new(journal),
                std::path::Path::new(method),
                &mut provider,
            ) {
                Ok(outcome) => {
                    report_loop(&outcome);
                    if outcome.order_ok() {
                        ExitCode::SUCCESS
                    } else {
                        ExitCode::FAILURE
                    }
                }
                Err(error) => {
                    eprintln!("цикл: {error}");
                    ExitCode::FAILURE
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
