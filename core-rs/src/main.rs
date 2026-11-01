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

/// Смонтировать общий каталог хоста (9p) в /mnt. Нужен, чтобы комната видела настоящие файлы,
/// а не копию-фикстуру: правки на хосте видны сразу, без пересборки образа.
fn mount_share(tag: &str) -> bool {
    match mount_filesystem(tag, "/mnt", "9p") {
        Ok(()) => {
            println!("share: 9p {tag} смонтирован в /mnt");
            true
        }
        Err(error) => {
            println!("share: 9p {tag} не смонтирован ({error})");
            false
        }
    }
}

fn mount_disk() -> bool {
    // devtmpfs уже смонтирован на старте init; повторный mount вернул бы EBUSY и лишнюю строку.
    if !std::path::Path::new("/dev/null").exists() {
        match mount_filesystem("devtmpfs", "/dev", "devtmpfs") {
            Ok(()) => println!("dev: devtmpfs смонтирован"),
            Err(error) => println!("dev: devtmpfs не смонтирован ({error})"),
        }
    }
    match mount_filesystem("/dev/vda", "/mnt", "ext4") {
        Ok(()) => true,
        Err(error) => {
            println!("mount /dev/vda -> /mnt: {error}");
            false
        }
    }
}

/// Смонтирован ли уже рабочий каталог: /mnt может быть занят проверкой долговечности журнала,
/// и повторный mount вернул бы «resource busy», выглядя как отсутствие диска.
fn workspace_mounted() -> bool {
    fs::read_to_string("/proc/mounts")
        .map(|text| {
            text.lines()
                .any(|line| line.split_whitespace().nth(1) == Some("/mnt"))
        })
        .unwrap_or(false)
}

/// Вынести журнал на диск хоста: приёмка читает его снаружи комнаты (ADR-0049).
///
/// Подделать копию модель не может: журнал пишет наш код, а копия делается после того, как цикл
/// закончился и ни одного хода у модели не осталось. Инструмент записи ограничен /mnt и на итог
/// приёмки не влияет: критерий лежит на хосте.
fn export_journal(source: &str, target: &str) {
    let bytes = match fs::read(source) {
        Ok(bytes) => bytes,
        Err(error) => {
            println!("журнал: не вынести — не читается {source} ({error})");
            return;
        }
    };
    match fs::write(target, &bytes) {
        Ok(()) => {
            // sync без размонтирования — это обещание, а не факт: файловая система может
            // потерять хвост при выключении питания. Поэтому оба шага делаются вместе.
            unsafe { libc::sync() };
            println!("журнал: вынесен в {target}, {} байт", bytes.len());
        }
        Err(error) => println!("журнал: не вынести в {target} ({error})"),
    }
}

fn unmount_workspace() {
    let code = unsafe { libc::umount(c"/mnt".as_ptr()) };
    if code == 0 {
        println!("диск: /mnt размонтирован");
        return;
    }
    let error = std::io::Error::last_os_error();
    // Отложенное размонтирование: каталог может быть ещё занят (у нас открыт /mnt/hs-journal.bin
    // в момент sync). MNT_DETACH снимает точку сразу и отпускает её, когда закроются дескрипторы.
    let detach = unsafe { libc::umount2(c"/mnt".as_ptr(), libc::MNT_DETACH) };
    if detach == 0 {
        println!("диск: /mnt размонтирован отложенно ({error})");
    } else {
        println!(
            "диск: /mnt не размонтирован ({error}; отложенно: {})",
            std::io::Error::last_os_error()
        );
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

/// Бесконечный прогон цикла на диск: убийство ВМ придётся на середину блока, и тогда видно,
/// что именно осталось. Останавливать по счётчику бессмысленно — тогда обрыва не будет.
fn loop_repeat(journal: &str, method: &str) -> ExitCode {
    if !mount_disk() {
        println!("диск: не смонтировать /dev/vda");
        return ExitCode::FAILURE;
    }
    println!("цикл на диске: пишу без остановки в {journal}");
    let mut runs = 0usize;
    let mut good = 0usize;
    loop {
        let mut link = hs_core::model::Stub::seal_many(method, 20);
        match hs_core::loopmod::run(
            std::path::Path::new(journal),
            std::path::Path::new(method),
            &mut link,
        ) {
            Ok(outcome) => {
                runs += 1;
                if outcome.order_ok() {
                    good += 1;
                } else {
                    println!("цикл: порядок нарушен: {:?}", outcome.problems);
                }
            }
            Err(error) => {
                println!("цикл: {error}");
                return ExitCode::FAILURE;
            }
        }
        if runs % 25 == 0 {
            println!("прогонов: {runs}, целых: {good}");
        }
    }
}

/// Разбор журнала на блоки прогонов после обрыва.
fn loop_verify(journal: &str) -> ExitCode {
    if !mount_disk() {
        println!("диск: не смонтировать /dev/vda");
        return ExitCode::FAILURE;
    }
    let bytes = match fs::read(journal) {
        Ok(bytes) => bytes,
        Err(error) => {
            println!("журнал: не прочитать ({error})");
            return ExitCode::FAILURE;
        }
    };
    match hs_core::loopmod::verify_blocks(&bytes) {
        Ok(report) => {
            println!(
                "блоков {}, целых {}, битых {}, хвост {} байт, размер {} байт",
                report.blocks,
                report.complete,
                report.broken,
                report.tail_bytes,
                bytes.len()
            );
            // Допускается ровно один битый блок — тот, что оборван убийством ВМ.
            if report.blocks > 0 && report.complete > 0 && report.broken <= 1 {
                ExitCode::SUCCESS
            } else {
                ExitCode::FAILURE
            }
        }
        Err(status) => {
            println!("журнал: {status}");
            ExitCode::FAILURE
        }
    }
}

/// Напечатать последний ответ модели из журнала: видно, что именно пришло по сети.
fn print_last_model_reply(path: &str) {
    let Ok(bytes) = fs::read(path) else { return };
    let Ok(walked) = hs_core::journal::walk(&bytes) else { return };
    let mut last: Option<String> = None;
    for entry in &walked.entries {
        if entry.kind != hs_core::journal::Kind::Data {
            continue;
        }
        let text = String::from_utf8_lossy(&entry.payload);
        if let Some(rest) = text.strip_prefix("model/reply ") {
            last = Some(rest.to_string());
        }
    }
    if let Some(reply) = last {
        println!("модель: {reply}");
    }
}

/// Напечатать последний результат инструмента из журнала: в консоли видно, что именно вернул
/// процесс, запущенный под правилом песочницы.
fn print_last_tool_result(path: &str) {
    let Ok(bytes) = fs::read(path) else { return };
    let Ok(walked) = hs_core::journal::walk(&bytes) else { return };
    let mut last: Option<String> = None;
    for entry in &walked.entries {
        if entry.kind != hs_core::journal::Kind::Data {
            continue;
        }
        let text = String::from_utf8_lossy(&entry.payload);
        if let Some(rest) = text.strip_prefix("tool/result ") {
            last = Some(rest.to_string());
        }
    }
    if let Some(result) = last {
        println!("инструмент: {result}");
    }
}

/// Проверка порядка по файлу журнала: то, что осталось после обрыва.
fn report_order_from_file(path: &str) {
    match hs_core::loopmod::order_from_journal(std::path::Path::new(path)) {
        Ok(problems) if problems.is_empty() => println!("порядок из файла: ok"),
        Ok(problems) => {
            println!("порядок из файла: НАРУШЕН");
            for problem in problems {
                println!("  [!] {problem}");
            }
        }
        Err(error) => println!("порядок из файла: не прочитать ({error})"),
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
    match &outcome.anchor {
        Some(found) => println!("утверждение: опирается на {found}"),
        None if outcome.status == "done" => println!("утверждение: без опоры (не должно случаться)"),
        None => println!("утверждение: без опоры в журнале"),
    }
}

fn spawn_check() -> ExitCode {
    // Изолирует вопрос: мешает ли pre_exec запуску или дело в чём-то ещё.
    let exe = std::env::current_exe().unwrap_or_else(|_| std::path::PathBuf::from("/init"));
    let mut plain = Command::new(&exe);
    plain.arg("sandbox-probe");
    println!(
        "без песочницы: {}",
        match plain.output() {
            Ok(out) => format!("код {:?}", out.status.code()),
            Err(error) => format!("ошибка {error}"),
        }
    );
    let mut hardened = Command::new(&exe);
    hardened.arg("sandbox-probe");
    hs_core::sandbox::harden_command(&mut hardened);
    println!(
        "с песочницей: {}",
        match hardened.output() {
            Ok(out) => format!("код {:?}", out.status.code()),
            Err(error) => format!("ошибка {error}"),
        }
    );
    // Третий вариант: ровно тот вызов, который делает spawn_cost и который в госте работает.
    let mut literal = Command::new("/init");
    literal.arg("seal").arg("/method.md");
    println!(
        "литеральный /init seal: {}",
        match literal.output() {
            Ok(out) => format!("код {:?}", out.status.code()),
            Err(error) => format!("ошибка {error}"),
        }
    );
    ExitCode::SUCCESS
}

fn dns_probe(sandboxed: bool) -> ExitCode {
    // Вопрос: работает ли резолв имён, когда UDP закрыт нашим же правилом (C-0141).
    if sandboxed {
        if let Err(error) = hs_core::sandbox::deny_udp() {
            println!("dns: правило не установлено ({error})");
            return ExitCode::FAILURE;
        }
    }
    let started = std::time::Instant::now();
    match std::net::ToSocketAddrs::to_socket_addrs(&("example.com", 443u16)) {
        Ok(addrs) => {
            let first = addrs.into_iter().next();
            println!(
                "dns ({}): ok, {} за {:.2} с",
                if sandboxed { "песочница" } else { "без песочницы" },
                match first {
                    Some(addr) => addr.to_string(),
                    None => "пусто".to_string(),
                },
                started.elapsed().as_secs_f64()
            );
            ExitCode::SUCCESS
        }
        Err(error) => {
            println!(
                "dns ({}): ошибка {error} за {:.2} с",
                if sandboxed { "песочница" } else { "без песочницы" },
                started.elapsed().as_secs_f64()
            );
            ExitCode::FAILURE
        }
    }
}

/// Выдача инструментов из файла `/tools` (JSON-массив имён). Нет файла — выданы все.
///
/// Решает хост, а не модель: набор инструментов — это полномочие. Прогону «найди и назови»
/// незачем `write` и `seal`, и объявить это надо до начала работы, а не после.
fn grants() -> Option<Vec<String>> {
    let text = fs::read_to_string("/tools").ok()?;
    let value: serde_json::Value = serde_json::from_str(&text).ok()?;
    let list: Vec<String> = value
        .as_array()?
        .iter()
        .filter_map(|item| item.as_str().map(str::to_string))
        .collect();
    if list.is_empty() {
        return None;
    }
    let known = hs_core::loopmod::KNOWN_TOOLS;
    let unknown: Vec<&String> = list
        .iter()
        .filter(|name| !known.contains(&name.as_str()))
        .collect();
    if !unknown.is_empty() {
        println!("инструменты: неизвестные имена {:?} — отказ по всему списку", unknown);
        return None;
    }
    Some(list)
}

/// Системная подсказка под выданный набор: модель не должна выбирать из того, чего у неё нет.
fn system_for(granted: &[String]) -> String {
    let usage = |name: &str| -> &'static str {
        match name {
            "list" => "list <каталог>",
            "read" => "read <файл> [с_строки]",
            "search" => "search <путь> <подстрока>",
            "seal" => "seal <файл>",
            "netprobe" => "netprobe",
            "write" => "write <путь> <текст>",
            _ => "",
        }
    };
    let list = granted
        .iter()
        .map(|name| usage(name))
        .filter(|text| !text.is_empty())
        .collect::<Vec<_>>()
        .join("; ");
    format!(
        "Ты — цикл харнесса в изолированной системе. Рабочий каталог: /mnt, файлы задачи лежат там; пути можно писать относительно него.\n\
         Отвечай РОВНО одной строкой:\n\
         TOOL <имя> <аргумент>   — выполнить инструмент\n\
         DONE <итог>             — закончить\n\
         В этом прогоне выданы только: {list}. Остального нет, и просить его бессмысленно.\n\
         В DONE приводи конкретное: путь с номером строки или идентификатор вида C-0123. Общие слова опорой не считаются, и прогон получит статус unverified.\n\
         Ничего другого не пиши."
    )
}

fn init_mode() -> ExitCode {
    println!("hs-core: я инициализировал систему сам, PID 1");
    println!("ядро: {}", kernel_release());
    println!("landlock ABI: {}", landlock_abi());
    println!("время до init: {:.2} с", hs_core::clock::uptime_seconds());
    // Режимы с диском: пишем цикл на /mnt и проверяем его после обрыва.
    let mode_text = fs::read_to_string("/mode").unwrap_or_default().trim().to_string();

    // Хостовый прогон: окружение хоста в комнату не переносится, поэтому имя прогона приходит
    // файлом. Если файла нет — прогон локальный, и это не ошибка, а другой уровень свидетельства.
    if let Ok(run) = fs::read_to_string("/host-run") {
        let run = run.trim().to_string();
        if !run.is_empty() {
            std::env::set_var("HS_HOST_RUN", &run);
            println!("хост: прогон объявлен хостовым ({run})");
        }
    }

    // /dev — раньше всего: Rust при spawn открывает /dev/null для stdin, и без него любой запуск
    // падает с ENOENT, выглядя как «нет файла» (найдено прогоном, F-0020).
    match mount_filesystem("devtmpfs", "/dev", "devtmpfs") {
        Ok(()) => println!("dev: devtmpfs смонтирован"),
        Err(error) => println!("dev: devtmpfs не смонтирован ({error})"),
    }

    // /proc и /sys: без них не работает current_exe() и часть проверок. Монтируем до инструментов.
    match mount_filesystem("proc", "/proc", "proc") {
        Ok(()) => println!("proc: смонтирован"),
        Err(error) => println!("proc: не смонтирован ({error})"),
    }
    match mount_filesystem("sysfs", "/sys", "sysfs") {
        Ok(()) => println!("sys: смонтирован"),
        Err(error) => println!("sys: не смонтирован ({error})"),
    }

    if mode_text == "dns-plain" {
        return dns_probe(false);
    }
    if mode_text == "dns-sandbox" {
        return dns_probe(true);
    }
    if mode_text == "spawn-check" {
        return spawn_check();
    }
    if mode_text == "loop-repeat" {
        return loop_repeat("/mnt/journal.bin", "/method.md");
    }
    if mode_text == "loop-verify" {
        return loop_verify("/mnt/journal.bin");
    }

    if mode_text == "loop-bridge" {
        if env::var(hs_core::loopmod::LOOP_GUARD).is_ok() {
            // Рекурсия: цикл запустил сам себя. Это не «ещё один прогон», а утечка памяти.
            println!("цикл: отказ — уже внутри цикла (защита от рекурсии)");
            loop {
                thread::sleep(Duration::from_secs(3600));
            }
        }
        // Первый настоящий круг: цикл в комнате зовёт модель через мост на хосте (plain HTTP,
        // без TLS внутри — ADR-0046). Адрес 10.0.2.2 — это хост в сети QEMU user-mode.
        let token = fs::read_to_string("/bridge-token").unwrap_or_default().trim().to_string();
        let model = fs::read_to_string("/bridge-model")
            .unwrap_or_else(|_| "deepseek-v4.1-flash".to_string())
            .trim()
            .to_string();
        let mut link = hs_core::model::HttpBridge::new("10.0.2.2", 8790, &token, &model);
        // Если задана задача и есть диск — монтируем его: задаче нужны файлы, а не только /method.md.
        let mut mounted = false;
        if fs::read_to_string("/task").is_ok() {
            mounted = mount_share("hostshare") || mount_disk();
            if !mounted {
                println!("диск: не смонтировать /dev/vda — задача будет работать без файлов");
            }
        }
        let task = fs::read_to_string("/task")
            .map(|text| text.trim().to_string())
            .unwrap_or_else(|_| "запечатать /method.md".to_string());
        // Бюджет: по умолчанию 8 шагов, 120 с и 5 центов — прогон не должен жечь allowance молча.
        let mut budget = hs_core::loopmod::Budget {
            steps: 8,
            seconds: 120.0,
            allowance: 0.05,
        };
        if let Ok(text) = fs::read_to_string("/budget") {
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(&text) {
                if let Some(steps) = value.get("steps").and_then(|v| v.as_u64()) {
                    budget.steps = steps as usize;
                }
                if let Some(seconds) = value.get("seconds").and_then(|v| v.as_f64()) {
                    budget.seconds = seconds;
                }
                if let Some(allowance) = value.get("allowance").and_then(|v| v.as_f64()) {
                    budget.allowance = allowance;
                }
            }
        }
        let outcome = hs_core::loopmod::run_task_with_budget(
            std::path::Path::new("/journal.bin"),
            &task,
            &mut link,
            budget,
        );
        match outcome {
            Ok(outcome) => {
                report_loop(&outcome);
                print_last_model_reply("/journal.bin");
                if mounted {
                    export_journal("/journal.bin", "/mnt/hs-journal.bin");
                    unmount_workspace();
                }
                report_order_from_file("/journal.bin");
            }
            Err(error) => println!("цикл: не запустился ({error})"),
        }
    }

    if mode_text == "loop-bridge-resume" {
        // Живой обрыв: журнал лежит на диске, поэтому переживает выключение питания. Второй
        // запуск видит незакрытый журнал и продолжает тот же прогон, а не начинает новый.
        let token = fs::read_to_string("/bridge-token").unwrap_or_default().trim().to_string();
        let model = fs::read_to_string("/bridge-model").unwrap_or_default().trim().to_string();
        let model = if model.is_empty() { "deepseek-v4.1-flash".to_string() } else { model };
        if !mount_disk() {
            println!("диск: не смонтировать /dev/vda — продолжать нечего");
            return ExitCode::FAILURE;
        }
        let task = fs::read_to_string("/task")
            .map(|text| text.trim().to_string())
            .unwrap_or_else(|_| "запечатать /method.md".to_string());
        let mut budget = hs_core::loopmod::Budget { steps: 8, seconds: 120.0, allowance: 0.05 };
        if let Ok(text) = fs::read_to_string("/budget") {
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(&text) {
                if let Some(steps) = value.get("steps").and_then(|v| v.as_u64()) {
                    budget.steps = steps as usize;
                }
                if let Some(seconds) = value.get("seconds").and_then(|v| v.as_f64()) {
                    budget.seconds = seconds;
                }
                if let Some(allowance) = value.get("allowance").and_then(|v| v.as_f64()) {
                    budget.allowance = allowance;
                }
            }
        }
        let mut link = hs_core::model::HttpBridge::new("10.0.2.2", 8790, &token, &model);
        // Выдача инструментов на прогон: файл `/tools` пишет хост (из критерия), а не модель.
        let granted = grants();
        if let Some(list) = &granted {
            println!("инструменты: выданы {}", list.join(", "));
            link.system = system_for(list);
        }
        let journal = std::path::Path::new("/mnt/journal.bin");
        let resumed = matches!(hs_core::loopmod::resume_state(journal), Ok(state) if !state.closed);
        let outcome = if resumed {
            match hs_core::loopmod::resume_state(journal) {
                Ok(state) => println!(
                    "продолжение: шагов {}, вызовов {}, хвост {} байт",
                    state.steps, state.calls, state.torn
                ),
                Err(error) => println!("продолжение: состояние не читается ({error})"),
            }
            hs_core::loopmod::run_task_resume(journal, &mut link, budget, granted.clone())
        } else {
            println!("прогон: свежий журнал на диске");
            // Первый заход пишет долговечно: иначе обрыв питания унесёт журнал целиком и
            // продолжать будет нечего (F-0027).
            hs_core::loopmod::run_task_durable(journal, &task, &mut link, budget, granted)
        };
        match outcome {
            Ok(outcome) => {
                report_loop(&outcome);
                print_last_model_reply("/mnt/journal.bin");
            }
            Err(error) => println!("цикл: не запустился ({error})"),
        }
        report_order_from_file("/mnt/journal.bin");
        match hs_core::loopmod::resume_state(journal) {
            Ok(state) => println!(
                "итог журнала: шагов {}, хвост {} байт, закрыт: {}",
                state.steps, state.torn, if state.closed { "да" } else { "нет" }
            ),
            Err(error) => println!("итог журнала: не читается ({error})"),
        }
        // Копия для приёмки: приёмка читает неподвижный файл, а не тот, что ещё пишется.
        export_journal("/mnt/journal.bin", "/mnt/hs-journal.bin");
        unmount_workspace();
        // Важно: без этого вызова init пошёл бы дальше в проверку долговечности и перезаписал
        // журнал своими тестовыми записями.
        println!("hs-core: система жива, жду");
        loop {
            thread::sleep(Duration::from_secs(3600));
        }
    }

    if mode_text == "loop-resume" {
        // Контроль обрыва: прогон без коммита и с нечитаемым хвостом обязан продолжиться с того
        // места, где остановился, а не начинаться заново (ADR-0051).
        let mut first = hs_core::model::Stub::seal_many("/method.md", 2);
        let budget_first = hs_core::loopmod::Budget { steps: 2, seconds: 20.0, allowance: 0.05 };
        match hs_core::loopmod::run_task_with_budget(
            std::path::Path::new("/journal.bin"),
            "запечатать /method.md",
            &mut first,
            budget_first,
        ) {
            Ok(outcome) => println!("первый заход: шагов {}, коммитов {}", outcome.steps, outcome.commits),
            Err(error) => println!("первый заход: не запустился ({error})"),
        }
        // Обрыв: отрезаем хвост записи коммита, как будто питание пропало посреди записи.
        match fs::OpenOptions::new().write(true).open("/journal.bin") {
            Ok(file) => {
                let length = file.metadata().map(|m| m.len()).unwrap_or(0);
                let _ = file.set_len(length.saturating_sub(4));
                println!("обрыв: журнал оборван на 4 байта");
            }
            Err(error) => println!("обрыв: не открыть журнал ({error})"),
        }
        match hs_core::loopmod::resume_state(std::path::Path::new("/journal.bin")) {
            Ok(state) => {
                println!(
                    "продолжение: шагов {}, вызовов {}, хвост {} байт, закрыт: {}",
                    state.steps, state.calls, state.torn,
                    if state.closed { "да" } else { "нет" }
                );
                println!("продолжение: история {}", state.history.len());
            }
            Err(error) => println!("продолжение: состояние не прочитано ({error})"),
        }
        let mut second = hs_core::model::Stub::new(vec!["DONE продолжение завершено".to_string()]);
        let budget = hs_core::loopmod::Budget { steps: 6, seconds: 30.0, allowance: 0.05 };
        match hs_core::loopmod::run_task_resume(
            std::path::Path::new("/journal.bin"),
            &mut second,
            budget,
            None,
        ) {
            Ok(outcome) => {
                report_loop(&outcome);
                if let Ok(state) = hs_core::loopmod::resume_state(std::path::Path::new("/journal.bin")) {
                    println!(
                        "после продолжения: шагов {}, хвост {} байт, закрыт: {}",
                        state.steps, state.torn,
                        if state.closed { "да" } else { "нет" }
                    );
                }
                report_order_from_file("/journal.bin");
            }
            Err(error) => println!("продолжение: не запустилось ({error})"),
        }
    }

    if mode_text == "loop-net" {
        // Проверка интеграции: инструмент запускается с правилом песочницы и не может открыть UDP.
        let mut link = hs_core::model::Stub::new(vec![
            "TOOL netprobe /".to_string(),
            "DONE проверено".to_string(),
        ]);
        match hs_core::loopmod::run(
            std::path::Path::new("/journal.bin"),
            std::path::Path::new("/method.md"),
            &mut link,
        ) {
            Ok(outcome) => {
                report_loop(&outcome);
                print_last_tool_result("/journal.bin");
                report_order_from_file("/journal.bin");
            }
            Err(error) => println!("цикл: не запустился ({error})"),
        }
    }

    if mode_text == "sandbox" {
        // Проверка правила песочницы в гостевой системе: нужна сеть в ядре, иначе socket(2)
        // возвращает ошибку по другой причине и проверка ничего не значит.
        return match hs_core::sandbox::probe() {
            Ok(checks) => {
                let mut all_ok = true;
                let mut parts: Vec<String> = Vec::new();
                for (name, ok) in checks {
                    if !ok {
                        all_ok = false;
                    }
                    parts.push(format!("{name}: {}", if ok { "да" } else { "НЕТ" }));
                }
                println!("sandbox: {}", parts.join(", "));
                if all_ok { ExitCode::SUCCESS } else { ExitCode::FAILURE }
            }
            Err(error) => {
                println!("sandbox: правило не установлено ({error})");
                ExitCode::FAILURE
            }
        };
    }
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
    if mode_text == "loop" || mode_text == "loop-torn" {
        // Диск монтируем, только если он есть: иначе журнал некуда вынести на приёмку.
        let mounted = std::path::Path::new("/dev/vda").exists()
            && (workspace_mounted() || mount_disk());
        let mut link = hs_core::model::Stub::seal_method("/method.md");
        match hs_core::loopmod::run(
            std::path::Path::new("/journal.bin"),
            std::path::Path::new("/method.md"),
            &mut link,
        ) {
            Ok(outcome) => {
                report_loop(&outcome);
                print_last_tool_result("/journal.bin");
                if mode_text == "loop-torn" {
                    // Контрольный случай: обрываем журнал и убеждаемся, что проверка по файлу
                    // это видит. Гейт, который не умеет падать, ничего не доказывает.
                    match fs::OpenOptions::new().write(true).open("/journal.bin") {
                        Ok(file) => {
                            let length = file.metadata().map(|m| m.len()).unwrap_or(0);
                            let _ = file.set_len(length.saturating_sub(4));
                            println!("журнал: оборван на 4 байта (контрольный случай)");
                        }
                        Err(error) => println!("журнал: не открыть для обрыва ({error})"),
                    }
                }
                // Вынос — после обрыва в контрольном случае: на хосте должен лежать именно тот
                // журнал, который видел гость, иначе приёмка проверяла бы не то.
                if mounted {
                    export_journal("/journal.bin", "/mnt/hs-journal.bin");
                    unmount_workspace();
                }
                report_order_from_file("/journal.bin");
            }
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
            // Первая строка — фильтр на себя: если ядро его не умеет, это сказано, а не забыто.
            // В stderr, а не в stdout: stdout — это результат инструмента (печать файла), и
            // подмешивать туда служебную строку значило бы менять то, что видит модель.
            let as_tool = std::env::var("HS_TOOL").is_ok();
            match hs_core::sandbox::harden_self() {
                Ok(()) if as_tool => eprintln!("sandbox: фильтр UDP поставлен"),
                Ok(()) => {}
                Err(error) if hs_core::sandbox::unsupported(&error) && as_tool => {
                    eprintln!("sandbox: фильтр UDP не поставлен (ядро без seccomp: {error})")
                }
                Err(error) if hs_core::sandbox::unsupported(&error) => {}
                Err(error) => {
                    eprintln!("sandbox: {error}");
                    return ExitCode::from(3);
                }
            }
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
            let mut link = hs_core::model::Stub::seal_method(method);
            match hs_core::loopmod::run(
                std::path::Path::new(journal),
                std::path::Path::new(method),
                &mut link,
            ) {
                Ok(outcome) => {
                    report_loop(&outcome);
                    report_order_from_file(journal);
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
        Some("sandbox-probe") => {
            // Проба правила: UDP (оба семейства) обязан быть закрыт, TCP — остаться рабочим.
            match hs_core::sandbox::probe() {
                Ok(checks) => {
                    let mut all_ok = true;
                    let mut parts: Vec<String> = Vec::new();
                    for (name, ok) in checks {
                        if !ok {
                            all_ok = false;
                        }
                        parts.push(format!("{name}: {}", if ok { "да" } else { "НЕТ" }));
                    }
                    println!("sandbox: {}", parts.join(", "));
                    if all_ok { ExitCode::SUCCESS } else { ExitCode::FAILURE }
                }
                Err(error) => {
                    println!("sandbox: правило не установлено ({error})");
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

