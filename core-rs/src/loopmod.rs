//! Цикл: шаг → вызов инструмента → запись в журнал → отчёт.
//!
//! Зачем это в ядре: харнесс живёт там, где живут свидетельства. Пока цикл на Python, «своя
//! система» — песочница для инструментов, а не харнесс. Здесь — скелет, который запускается как
//! PID 1 и проверяется тем же прогоном, что и загрузка.
//!
//! Что именно проверяется: не «модель отвечает», а **порядок событий**. Провайдер здесь
//! скриптовый (сети в конфиге C нет), инструмент — внешний процесс (сам бинарь, режим `seal`).
//! Значит честное утверждение звучит так: «события легли в журнал в том порядке, в каком они
//! обязаны лежать, и порядок проверен машинно» — а не «цикл работает».
//!
//! Порядок: `run/start → tool/call → tool/result → step → … → run/end`, затем отдельный маркер
//! коммита. Результат без предшествующего вызова — дефект, а не мелочь: именно так в журналах
//! появляются события, которых не было.

use std::path::Path;
use std::process::Command;

use crate::journal::{Journal, Kind};

/// Больше шагов, чем это, скриптовый провайдер не делает: предохранитель от вечного цикла.
pub const MAX_STEPS: usize = 64;

use crate::model::{ModelLink, Reply};

/// Бюджет прогона: шаги, время и деньги. Три предела, потому что прогон может упереться в любой.
#[derive(Debug, Clone, Copy)]
pub struct Budget {
    pub steps: usize,
    pub seconds: f64,
    /// Предел в тех же единицах, что `usage.allowance` провайдера.
    pub allowance: f64,
}

impl Default for Budget {
    fn default() -> Self {
        Budget { steps: MAX_STEPS, seconds: 300.0, allowance: 0.05 }
    }
}

/// Шаг, разобранный из ответа модели.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Step {
    Tool { name: String, arg: String },
    Done { text: String },
}

/// Разобрать ответ провайдера в шаг. Ошибка — это результат, а не пустая строка.
pub fn parse_step(reply: &str) -> Result<Step, String> {
    if reply.len() > crate::model::MAX_REPLY {
        return Err(format!("ответ длиннее {} байт", crate::model::MAX_REPLY));
    }
    let line = reply
        .lines()
        .map(str::trim)
        .find(|line| !line.is_empty())
        .unwrap_or_default();
    if line.is_empty() {
        return Err("пустой ответ провайдера".to_string());
    }
    if let Some(rest) = line.strip_prefix("TOOL ") {
        let mut parts = rest.splitn(2, ' ');
        let name = parts.next().unwrap_or_default().trim().to_string();
        let arg = parts.next().unwrap_or_default().trim().to_string();
        if name.is_empty() {
            return Err("TOOL без имени инструмента".to_string());
        }
        return Ok(Step::Tool { name, arg });
    }
    if let Some(rest) = line.strip_prefix("DONE") {
        return Ok(Step::Done { text: rest.trim().to_string() });
    }
    Err(format!(
        "не понял шаг: {}",
        line.chars().take(60).collect::<String>()
    ))
}


#[derive(Debug, Clone)]
pub struct Event {
    pub kind: &'static str,
    pub detail: String,
}

pub struct Outcome {
    pub steps: usize,
    pub calls: usize,
    pub events: usize,
    pub records: usize,
    pub commits: usize,
    pub status: &'static str,
    pub problems: Vec<String>,
    /// Чем подтверждено финальное утверждение: элемент, найденный и в ответе, и в журнале.
    pub anchor: Option<String>,
}

impl Outcome {
    pub fn order_ok(&self) -> bool {
        self.problems.is_empty()
    }
}

fn record(
    journal: &mut Journal,
    events: &mut Vec<Event>,
    kind: &'static str,
    detail: String,
) -> std::io::Result<()> {
    journal.append(format!("{kind} {detail}").as_bytes(), Kind::Data)?;
    events.push(Event { kind, detail });
    Ok(())
}

/// Инструмент `seal`: запечатать файл, переиспользовав себя же (режим `seal`).
/// Признак «мы уже внутри цикла». Ставится дочерним процессам, чтобы они не запускали второй.
pub const LOOP_GUARD: &str = "HS_LOOP_ACTIVE";

fn tool_seal(arg: &str) -> Result<String, String> {
    let exe = std::env::current_exe().map_err(|error| format!("нет своего пути: {error}"))?;
    let mut command = Command::new(exe);
    command.arg("seal").arg(arg).env(LOOP_GUARD, "1");
    // Правило песочницы ставится до exec и наследуется потомками инструмента.
    crate::sandbox::harden_command(&mut command);
    let output = command
        .output()
        .map_err(|error| format!("не запустить инструмент: {error}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if output.status.success() {
        Ok(stdout)
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        Err(format!("код {:?}: {stdout}{stderr}", output.status.code()))
    }
}

/// Диагностический инструмент: проверить, что правило песочницы унаследовано процессом.
fn tool_netprobe(_arg: &str) -> Result<String, String> {
    let exe = std::env::current_exe().map_err(|error| format!("нет своего пути: {error}"))?;
    let shown = exe.display().to_string();
    let mut command = Command::new(&exe);
    command.arg("sandbox-probe").env(LOOP_GUARD, "1");
    crate::sandbox::harden_command(&mut command);
    let output = command
        .output()
        .map_err(|error| {
            let meta = std::fs::metadata(&shown)
                .map(|m| format!("{} байт", m.len()))
                .unwrap_or_else(|e| format!("метаданных нет: {e}"));
            format!("не запустить пробу {shown} ({meta}): {error}")
        })?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let line = stdout
        .lines()
        .find(|line| line.starts_with("sandbox:"))
        .unwrap_or("sandbox: (нет строки)")
        .to_string();
    if output.status.success() {
        Ok(line)
    } else {
        Err(format!("проба вернула {:?}: {line}", output.status.code()))
    }
}

/// Пределы инструментов: лучше честный обрезанный ответ, чем съеденная память.
pub const MAX_FILES: usize = 500;
pub const MAX_DEPTH: usize = 4;
pub const MAX_FILE: u64 = 1024 * 1024;
pub const MAX_MATCHES: usize = 40;
pub const MAX_READ: usize = 8 * 1024;

fn skip_dir(name: &str) -> bool {
    matches!(name, ".git" | "target" | "node_modules" | "__pycache__" | ".venv")
}

fn collect_files(dir: &Path, depth: usize, out: &mut Vec<std::path::PathBuf>) {
    if depth > MAX_DEPTH || out.len() >= MAX_FILES {
        return;
    }
    let Ok(entries) = std::fs::read_dir(dir) else { return };
    let mut items: Vec<_> = entries.flatten().collect();
    items.sort_by_key(|entry| entry.file_name());
    for entry in items {
        if out.len() >= MAX_FILES {
            return;
        }
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        match entry.file_type() {
            Ok(kind) if kind.is_dir() => {
                if !skip_dir(&name) {
                    collect_files(&path, depth + 1, out);
                }
            }
            Ok(kind) if kind.is_file() => out.push(path),
            _ => {}
        }
    }
}

/// `search <каталог> <подстрока>`: искать по содержимому, без shell и без внешних программ.
///
/// Зачем своей реализацией, а не через `grep`: в комнате нет ни shell, ни coreutils, а тащить
/// busybox — это +2,12 МБ (C-0140). Поиск — примитив, его дешевле держать внутри цикла.
fn tool_search(arg: &str) -> Result<String, String> {
    let (dir, needle) = arg
        .split_once(' ')
        .ok_or_else(|| "нужно: search <каталог> <подстрока>".to_string())?;
    let needle = needle.trim();
    if needle.chars().count() < 2 {
        return Err("подстрока короче двух символов: слишком много совпадений".to_string());
    }
    let root = Path::new(dir.trim());
    if !root.is_dir() {
        return Err(format!("не каталог: {}", root.display()));
    }
    let mut files = Vec::new();
    collect_files(root, 0, &mut files);
    let scanned = files.len();
    let mut matches: Vec<String> = Vec::new();
    let mut truncated = false;
    for path in files {
        let Ok(meta) = std::fs::metadata(&path) else { continue };
        if meta.len() > MAX_FILE {
            continue;
        }
        let Ok(text) = std::fs::read_to_string(&path) else { continue };
        for (index, line) in text.lines().enumerate() {
            if line.contains(needle) {
                matches.push(format!(
                    "{}:{}: {}",
                    path.display(),
                    index + 1,
                    line.trim().chars().take(160).collect::<String>()
                ));
                if matches.len() >= MAX_MATCHES {
                    truncated = true;
                    break;
                }
            }
        }
        if truncated {
            break;
        }
    }
    if matches.is_empty() {
        return Ok(format!("найдено 0 в {scanned} файлах"));
    }
    let mut out = format!(
        "найдено {} в {scanned} файлах{}:",
        matches.len(),
        if truncated { " (обрезано)" } else { "" }
    );
    for line in matches {
        out.push('\n');
        out.push_str(&line);
    }
    Ok(out)
}

/// `list <каталог>`: имена и размеры, без рекурсии.
fn tool_list(arg: &str) -> Result<String, String> {
    let root = Path::new(arg.trim());
    let entries = std::fs::read_dir(root).map_err(|error| format!("не прочитать {}: {error}", root.display()))?;
    let mut items: Vec<String> = Vec::new();
    for entry in entries.flatten() {
        let meta = entry.metadata().ok();
        let kind = match entry.file_type() {
            Ok(kind) if kind.is_dir() => "каталог",
            _ => "файл",
        };
        items.push(format!(
            "{}\t{}\t{}",
            entry.file_name().to_string_lossy(),
            kind,
            meta.map(|m| m.len()).unwrap_or(0)
        ));
        if items.len() >= 200 {
            items.push("… (обрезано)".to_string());
            break;
        }
    }
    items.sort();
    Ok(items.join("\n"))
}

/// `read <файл>`: текст до 8 КиБ, с номерами строк — чтобы модель могла ссылаться на место.
fn tool_read(arg: &str) -> Result<String, String> {
    let path = Path::new(arg.trim());
    let meta = std::fs::metadata(path).map_err(|error| format!("нет файла: {error}"))?;
    if meta.len() > MAX_FILE {
        return Err(format!("файл больше {MAX_FILE} байт"));
    }
    let text = std::fs::read_to_string(path).map_err(|error| format!("не прочитать: {error}"))?;
    let mut out = String::new();
    for (index, line) in text.lines().enumerate() {
        if out.len() >= MAX_READ {
            out.push_str("… (обрезано)");
            break;
        }
        out.push_str(&format!("{}: {}\n", index + 1, line));
    }
    Ok(out)
}

/// Корень, внутри которого разрешена запись. Всё остальное — отказ, а не «попробуем».
///
/// Почему так: запись — единственный инструмент, который меняет мир. Пока он пишет куда угодно,
/// песочница бессмысленна: файл можно положить в /init и получить исполнение при следующей загрузке.
fn workspace_root() -> std::path::PathBuf {
    std::env::var("HS_WORKSPACE")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from("/mnt"))
}

/// `write <путь> <текст>`: записать файл внутри рабочего каталога.
pub fn tool_write_in(arg: &str, root: &Path) -> Result<String, String> {
    let (path, text) = arg
        .split_once(' ')
        .ok_or_else(|| "нужно: write <путь> <текст>".to_string())?;
    let target = Path::new(path.trim());
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let parent = target
        .parent()
        .ok_or_else(|| "у пути нет родителя".to_string())?
        .canonicalize()
        .map_err(|error| format!("нет такого каталога: {error}"))?;
    if !parent.starts_with(&root) {
        return Err(format!(
            "запись только внутри {}: {} вне его",
            root.display(),
            target.display()
        ));
    }
    let bytes = text.as_bytes().len();
    std::fs::write(target, text).map_err(|error| format!("не записать: {error}"))?;
    Ok(format!("записано {bytes} байт в {}", target.display()))
}

fn tool_write(arg: &str) -> Result<String, String> {
    let root = workspace_root();
    tool_write_in(arg, &root)
}

fn run_tool(name: &str, arg: &str) -> Result<String, String> {
    match name {
        "seal" => tool_seal(arg),
        "netprobe" => tool_netprobe(arg),
        "search" => tool_search(arg),
        "list" => tool_list(arg),
        "read" => tool_read(arg),
        "write" => tool_write(arg),
        other => Err(format!("неизвестный инструмент: {other}")),
    }
}

/// Опора утверждения: минимальная механическая проверка «сказанное взялось из журнала».
///
/// Что это ловит: модель закончила работу, ничего не выполнив, или придумала путь/число, которого
/// инструменты не возвращали. Что это НЕ делает: не проверяет истинность утверждения — только то,
/// что в нём есть хотя бы один элемент, действительно пришедший из результата инструмента.
pub fn claim_anchor(final_text: &str, tool_results: &[String]) -> Option<String> {
    let tokens = |text: &str| -> Vec<String> {
        text.split(|c: char| !(c.is_alphanumeric() || c == '/' || c == '.' || c == '_' || c == '-'))
            .filter(|part| part.chars().count() >= 4)
            .map(|part| part.to_string())
            .collect()
    };
    let haystack: Vec<String> = tool_results.iter().flat_map(|r| tokens(r)).collect();
    for token in tokens(final_text) {
        if haystack.contains(&token) {
            return Some(token);
        }
    }
    None
}

/// Проверка порядка событий — чистая функция, чтобы её можно было проверить тестом.
pub fn verify_order(events: &[Event]) -> Vec<String> {
    let mut problems = Vec::new();
    let Some(first) = events.first() else {
        return vec!["событий нет".to_string()];
    };
    if first.kind != "run/start" {
        problems.push(format!("первое событие {}, а не run/start", first.kind));
    }
    let Some(last) = events.last() else {
        return problems;
    };
    if last.kind != "run/end" {
        problems.push(format!("последнее событие {}, а не run/end", last.kind));
    }

    let mut open_calls = 0i64;
    let mut calls = 0usize;
    let mut steps = 0usize;
    for event in events {
        match event.kind {
            "tool/call" => {
                open_calls += 1;
                calls += 1;
            }
            "tool/result" => {
                if open_calls == 0 {
                    problems.push("tool/result без предшествующего tool/call".to_string());
                } else {
                    open_calls -= 1;
                }
            }
            "step" => steps += 1,
            _ => {}
        }
    }
    if open_calls != 0 {
        problems.push(format!("вызовов без результата: {open_calls}"));
    }
    if steps != calls {
        problems.push(format!("шагов {steps}, вызовов {calls}"));
    }
    problems
}

/// Прогон цикла в журнал по пути `journal_path`.
pub fn run(
    journal_path: &Path,
    method_path: &Path,
    link: &mut dyn ModelLink,
) -> std::io::Result<Outcome> {
    let task = format!("запечатать {}", method_path.display());
    run_task(journal_path, &task, link)
}

/// Прогон с произвольной задачей: нужен, когда задача не «запечатать файл», а, например,
/// «найти строку в каталоге». Задача — параметр, а не зашитая строка.
pub fn run_task(
    journal_path: &Path,
    task: &str,
    link: &mut dyn ModelLink,
) -> std::io::Result<Outcome> {
    run_task_with_budget(journal_path, task, link, Budget::default())
}

/// То же, но с явным бюджетом. Проверка бюджета — часть прогона, а не пожелание снаружи.
pub fn run_task_with_budget(
    journal_path: &Path,
    task: &str,
    link: &mut dyn ModelLink,
    budget: Budget,
) -> std::io::Result<Outcome> {
    let mut journal = Journal::open(journal_path)?;
    let mut events: Vec<Event> = Vec::new();
    let mut steps = 0usize;
    let mut calls = 0usize;
    let mut attempts = 0usize;
    let mut spent: f64 = 0.0;
    let mut anchor: Option<String> = None;
    let started = std::time::Instant::now();
    let mut status: &'static str = "no-done";

    record(&mut journal, &mut events, "run/start", format!("task: {task}"))?;
    let mut prompt = task.to_string();

    while attempts < budget.steps && steps < budget.steps {
        if started.elapsed().as_secs_f64() > budget.seconds {
            record(&mut journal, &mut events, "step/error",
                   format!("бюджет времени исчерпан: {:.0} с", budget.seconds))?;
            status = "budget-time";
            break;
        }
        attempts += 1;
        let reply = link.complete(&prompt);
        if let Some(usage) = link.last_usage() {
            spent += usage.allowance;
        }
        let reply = match reply {
            Reply::Text(text) => text,
            Reply::End => break,
            Reply::Error(error) => {
                record(&mut journal, &mut events, "step/error", error.clone())?;
                status = "model-error";
                prompt = format!("мост вернул ошибку: {error}");
                break;
            }
            Reply::Truncated(reason) => {
                record(&mut journal, &mut events, "step/error", reason.clone())?;
                status = "truncated";
                break;
            }
        };
        // Сырой ответ в журнал не кладём: кладём длину и начало — этого хватает, чтобы отличить
        // пустой ответ от содержательного, и не хватает, чтобы утечь секретом.
        let preview = reply
            .lines()
            .map(str::trim)
            .find(|line| !line.is_empty())
            .unwrap_or_default();
        record(
            &mut journal,
            &mut events,
            "model/reply",
            format!(
                "{} байт, начало: {}",
                reply.len(),
                preview.chars().take(40).collect::<String>()
            ),
        )?;

        let step = match parse_step(&reply) {
            Ok(step) => step,
            Err(error) => {
                record(&mut journal, &mut events, "step/error", error.clone())?;
                status = "bad-step";
                prompt = format!(
                    "{error}. Ответь одной строкой: TOOL <имя> <аргумент> или DONE <итог>."
                );
                continue;
            }
        };

        match step {
            Step::Tool { name, arg } => {
                steps += 1;
                record(&mut journal, &mut events, "tool/call", format!("{name} {arg}"))?;
                let result = run_tool(&name, &arg);
                calls += 1;
                match result {
                    Ok(text) => {
                        record(&mut journal, &mut events, "tool/result", format!("ok {text}"))?;
                        prompt = format!("{name}: ok {text}");
                    }
                    Err(error) => {
                        record(&mut journal, &mut events, "tool/result", format!("err {error}"))?;
                        prompt = format!("{name}: ошибка {error}");
                    }
                }
                record(&mut journal, &mut events, "step",
                       format!("{steps}, потрачено {spent:.8}"))?;
                if spent > budget.allowance {
                    record(&mut journal, &mut events, "step/error",
                           format!("бюджет денег исчерпан: {spent:.8} > {:.8}", budget.allowance))?;
                    status = "budget-money";
                    record(&mut journal, &mut events, "run/end", "остановлен бюджетом".to_string())?;
                    break;
                }
            }
            Step::Done { text } => {
                // Опора проверяется до закрытия прогона: утверждение — часть результата, а не
                // событие после него. Иначе порядок «… → run/end» перестаёт быть последним.
                let results: Vec<String> = events
                    .iter()
                    .filter(|event| event.kind == "tool/result")
                    .map(|event| event.detail.clone())
                    .collect();
                anchor = claim_anchor(&text, &results);
                match &anchor {
                    Some(found) => {
                        record(&mut journal, &mut events, "claim/anchored", found.clone())?
                    }
                    None => record(
                        &mut journal,
                        &mut events,
                        "claim/unverified",
                        "в ответе нет ни одного элемента из результатов инструментов".to_string(),
                    )?,
                }
                status = if anchor.is_some() { "done" } else { "unverified" };
                record(&mut journal, &mut events, "run/end", text)?;
                break;
            }
        }
    }

    if status != "done" {
        let reason = if status == "bad-step" {
            format!("провайдер не дал разбираемого шага за {attempts} попыток")
        } else {
            format!("шаги кончились без сигнала завершения (попыток {attempts})")
        };
        record(&mut journal, &mut events, "run/end", reason)?;
    }

    // Маркер коммита — граница: всё до него считается завершённым набором событий.
    journal.append(b"commit", Kind::Commit)?;
    journal.sync()?;
    let report = journal.report()?;
    let problems = verify_order(&events);

    Ok(Outcome {
        steps,
        calls,
        events: events.len(),
        records: report.records,
        commits: report.committed,
        status,
        problems,
        anchor,
    })
}

/// Проверка порядка событий **по файлу** журнала, а не по памяти процесса.
///
/// Зачем: после обрыва остаётся только файл. Если порядок проверяется лишь в памяти, то
/// утверждение «события легли в правильном порядке» верно ровно до падения — а проверять его
/// нужно как раз после.
pub fn order_from_journal(journal_path: &Path) -> std::io::Result<Vec<String>> {
    let bytes = std::fs::read(journal_path)?;
    let walked = match crate::journal::walk(&bytes) {
        Ok(walked) => walked,
        Err(status) => return Ok(vec![format!("журнал не читается: {status}")]),
    };

    let mut problems = Vec::new();
    if walked.tail_bytes > 0 {
        problems.push(format!(
            "оборванный хвост {} байт: последняя запись не подтверждена",
            walked.tail_bytes
        ));
    }

    let mut events: Vec<Event> = Vec::new();
    let mut ends_with_commit = false;
    for entry in &walked.entries {
        if entry.kind == crate::journal::Kind::Commit {
            ends_with_commit = true;
            continue;
        }
        ends_with_commit = false;
        let event = decode_event(&entry.payload);
        if event.kind == "?" {
            problems.push(format!("неизвестное событие в журнале: {}", event.detail));
        }
        events.push(event);
    }

    problems.extend(verify_order(&events));
    if !ends_with_commit {
        problems.push("журнал не заканчивается маркером коммита".to_string());
    }
    Ok(problems)
}

/// Разобрать полезную нагрузку записи в событие. Неизвестный вид — `"?"`, а не догадка.
fn decode_event(payload: &[u8]) -> Event {
    let text = String::from_utf8_lossy(payload);
    let mut parts = text.splitn(2, ' ');
    let raw = parts.next().unwrap_or_default();
    let detail = parts.next().unwrap_or_default().to_string();
    let kind: &'static str = match raw {
        "run/start" => "run/start",
        "model/reply" => "model/reply",
        "tool/call" => "tool/call",
        "tool/result" => "tool/result",
        "step" => "step",
        "step/error" => "step/error",
        "claim/anchored" => "claim/anchored",
        "claim/unverified" => "claim/unverified",
        "run/end" => "run/end",
        _ => "?",
    };
    Event { kind, detail }
}

/// Итог разбора журнала на блоки прогонов (блок заканчивается маркером коммита).
#[derive(Debug, Clone, Default)]
pub struct BlocksReport {
    pub blocks: usize,
    pub complete: usize,
    pub broken: usize,
    pub tail_bytes: usize,
}

/// Проверить журнал как последовательность прогонов: каждый блок обязан иметь свой `run/start`,
/// парный `run/end` и правильный порядок. Неполный последний блок считается битым, а не «почти
/// целым»: после обрыва именно он и вызывает вопросы.
pub fn verify_blocks(bytes: &[u8]) -> Result<BlocksReport, String> {
    let walked = crate::journal::walk(bytes)?;
    let mut events: Vec<Event> = Vec::new();
    let mut blocks = 0usize;
    let mut complete = 0usize;

    for entry in &walked.entries {
        if entry.kind == crate::journal::Kind::Commit {
            blocks += 1;
            if verify_order(&events).is_empty() {
                complete += 1;
            }
            events.clear();
            continue;
        }
        events.push(decode_event(&entry.payload));
    }

    let unclosed = if events.is_empty() { 0 } else { 1 };
    Ok(BlocksReport {
        blocks,
        complete,
        broken: blocks - complete + unclosed,
        tail_bytes: walked.tail_bytes,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn event(kind: &'static str) -> Event {
        Event { kind, detail: String::new() }
    }

    #[test]
    fn правильный_порядок_проходит() {
        let events = vec![
            event("run/start"),
            event("tool/call"),
            event("tool/result"),
            event("step"),
            event("run/end"),
        ];
        assert!(verify_order(&events).is_empty());
    }

    #[test]
    fn результат_без_вызова_это_дефект() {
        let events = vec![event("run/start"), event("tool/result"), event("run/end")];
        let problems = verify_order(&events);
        assert!(problems.iter().any(|p| p.contains("без предшествующего")), "{problems:?}");
    }

    #[test]
    fn вызов_без_результата_это_дефект() {
        let events = vec![event("run/start"), event("tool/call"), event("run/end")];
        let problems = verify_order(&events);
        assert!(problems.iter().any(|p| p.contains("без результата")), "{problems:?}");
    }

    #[test]
    fn run_end_не_последним_это_дефект() {
        let events = vec![event("run/start"), event("run/end"), event("tool/call")];
        let problems = verify_order(&events);
        assert!(problems.iter().any(|p| p.contains("последнее событие")), "{problems:?}");
    }

    #[test]
    fn пустой_журнал_событий_это_дефект() {
        assert!(!verify_order(&[]).is_empty());
    }

    #[test]
    fn разбор_шага_инструмент() {
        assert_eq!(
            parse_step("TOOL seal /method.md").unwrap(),
            Step::Tool { name: "seal".to_string(), arg: "/method.md".to_string() }
        );
    }

    #[test]
    fn разбор_шага_завершение() {
        assert_eq!(
            parse_step("DONE всё готово").unwrap(),
            Step::Done { text: "всё готово".to_string() }
        );
    }

    #[test]
    fn разбор_шага_мусор_это_ошибка_а_не_пропуск() {
        assert!(parse_step("давай сделаем что-нибудь").is_err());
        assert!(parse_step("").is_err());
        assert!(parse_step("TOOL").is_err());
    }

    #[test]
    fn утверждение_с_опорой_считается_подтверждённым() {
        assert_eq!(
            claim_anchor("найдено в /mnt/notes/log.md", &["ok /mnt/notes/log.md:3: МАРКЕР".to_string()]),
            Some("/mnt/notes/log.md".to_string())
        );
        assert_eq!(claim_anchor("всё хорошо", &["ok 42".to_string()]), None);
        assert_eq!(claim_anchor("путь /tmp/x", &[]), None);
    }

    #[test]
    fn мусор_от_провайдера_порядок_остаётся_целым() {
        let dir = std::env::temp_dir().join(format!("hs-loop-bad-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let journal = dir.join("journal.bin");
        let method = dir.join("method.md");
        std::fs::write(&method, "тело\n").unwrap();

        let mut provider = crate::model::Stub::new(vec!["просто текст".to_string()]);
        let outcome = run(&journal, &method, &mut provider).unwrap();
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        assert_eq!(outcome.steps, 0);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn пустой_ответ_модели_это_ошибка_формата() {
        let dir = std::env::temp_dir().join(format!("hs-loop-empty-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let journal = dir.join("journal.bin");
        let method = dir.join("method.md");
        std::fs::write(&method, "тело\n").unwrap();

        let mut provider = crate::model::Stub::new(vec![String::new()]);
        let outcome = run(&journal, &method, &mut provider).unwrap();
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn неизвестный_инструмент_даёт_ошибку_в_результате() {
        let dir = std::env::temp_dir().join(format!("hs-loop-unk-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let journal = dir.join("journal.bin");
        let method = dir.join("method.md");
        std::fs::write(&method, "тело\n").unwrap();

        let mut provider = crate::model::Stub::new(vec![
            "TOOL rm -rf /".to_string(),
            "DONE конец".to_string(),
        ]);
        let outcome = run(&journal, &method, &mut provider).unwrap();
        // Инструмент неизвестен, значит результата нет, значит и опоры в журнале нет.
        assert_eq!(outcome.status, "unverified");
        assert_eq!(outcome.calls, 1);
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn прогон_пишет_журнал_и_соблюдает_порядок() {
        let dir = std::env::temp_dir().join(format!("hs-loop-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let journal = dir.join("journal.bin");
        let method = dir.join("method.md");
        std::fs::write(&method, "тело методологии\n").unwrap();

        let mut provider = crate::model::Stub::seal_method(method.to_str().unwrap());
        let outcome = run(&journal, &method, &mut provider).unwrap();
        // Хеш печати в ответе не назван, значит опоры нет: это unverified, а не done.
        assert_eq!(outcome.status, "unverified");
        assert_eq!(outcome.steps, 1);
        assert_eq!(outcome.calls, 1);
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        // 5 событий: start, call, result, step, end; плюс маркер коммита.
        // 7 событий: start, ответ(TOOL), вызов, результат, шаг, ответ(DONE), конец;
        // плюс маркер коммита.
        assert_eq!(outcome.events, 9);
        assert_eq!(outcome.records, 10);
        assert_eq!(outcome.commits, 1);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn провайдер_без_завершения_даёт_no_done() {
        let dir = std::env::temp_dir().join(format!("hs-loop-nodone-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let journal = dir.join("journal.bin");
        let method = dir.join("method.md");
        std::fs::write(&method, "тело\n").unwrap();

        let mut provider = crate::model::Stub::new(vec![format!("TOOL seal {}", method.display())]);
        let outcome = run(&journal, &method, &mut provider).unwrap();
        assert_eq!(outcome.status, "no-done");
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        std::fs::remove_dir_all(&dir).ok();
    }

    fn fixture(tag: &str) -> std::path::PathBuf {
        // Имя уникально для теста: тесты идут параллельно в одном процессе, общий каталог
        // приводил к тому, что один тест удалял фикстуру другого.
        let dir = std::env::temp_dir().join(format!("hs-tools-{}-{}", std::process::id(), tag));
        std::fs::create_dir_all(dir.join("sub")).unwrap();
        std::fs::write(dir.join("a.md"), "первая строка\nвторая: МАРКЕР\n").unwrap();
        std::fs::write(dir.join("sub/b.md"), "тоже МАРКЕР тут\n").unwrap();
        std::fs::write(dir.join("c.txt"), "без совпадений\n").unwrap();
        dir
    }

    #[test]
    fn поиск_находит_в_файлах_и_подкаталогах() {
        let dir = fixture("search");
        let out = tool_search(&format!("{} МАРКЕР", dir.display())).unwrap();
        assert!(out.contains("найдено 2"), "{out}");
        assert!(out.contains("a.md:2:"), "{out}");
        assert!(out.contains("b.md:1:"), "{out}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn поиск_без_совпадений_говорит_об_этом_числом() {
        let dir = fixture("none");
        let out = tool_search(&format!("{} нетакого", dir.display())).unwrap();
        assert!(out.starts_with("найдено 0"), "{out}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn поиск_отбивает_короткую_иголку_и_не_каталог() {
        let dir = fixture("short");
        assert!(tool_search(&format!("{} и", dir.display())).is_err());
        assert!(tool_search("/нет/такого иго").is_err());
        assert!(tool_search("без_пробела").is_err());
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn чтение_даёт_номера_строк() {
        let dir = fixture("read");
        let out = tool_read(&format!("{}", dir.join("a.md").display())).unwrap();
        assert!(out.starts_with("1: первая строка"), "{out}");
        assert!(out.contains("МАРКЕР"), "{out}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn список_перечисляет_имена_и_типы() {
        let dir = fixture("list");
        let out = tool_list(&format!("{}", dir.display())).unwrap();
        assert!(out.contains("a.md"), "{out}");
        assert!(out.contains("каталог"), "{out}");
        std::fs::remove_dir_all(&dir).ok();
    }

    /// Провайдер, который сообщает расход: нужен, чтобы проверить денежный бюджет.
    struct Metered {
        replies: Vec<String>,
        index: usize,
        usage: crate::model::Usage,
    }

    impl ModelLink for Metered {
        fn complete(&mut self, _prompt: &str) -> Reply {
            match self.replies.get(self.index).cloned() {
                Some(text) => {
                    self.index += 1;
                    Reply::Text(text)
                }
                None => Reply::End,
            }
        }

        fn last_usage(&self) -> Option<crate::model::Usage> {
            Some(self.usage)
        }
    }

    #[test]
    fn денежный_бюджет_останавливает_прогон() {
        let dir = fixture("budget-money");
        let journal = dir.join("journal.bin");
        let mut link = Metered {
            replies: vec![
                "TOOL list /".to_string(),
                "TOOL list /".to_string(),
                "DONE конец".to_string(),
            ],
            index: 0,
            usage: crate::model::Usage { prompt_tokens: 10, completion_tokens: 10, allowance: 0.02 },
        };
        let budget = Budget { steps: 10, seconds: 30.0, allowance: 0.01 };
        let outcome = run_task_with_budget(&journal, "тест", &mut link, budget).unwrap();
        assert_eq!(outcome.status, "budget-money", "{:?}", outcome.problems);
        assert_eq!(outcome.calls, 1, "после первого шага бюджет уже превышен");
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn бюджет_времени_останавливает_до_первого_шага() {
        let dir = fixture("budget-time");
        let journal = dir.join("journal.bin");
        let mut link = crate::model::Stub::seal_method("/method.md");
        let budget = Budget { steps: 10, seconds: 0.0, allowance: 1.0 };
        let outcome = run_task_with_budget(&journal, "тест", &mut link, budget).unwrap();
        assert_eq!(outcome.status, "budget-time");
        assert_eq!(outcome.calls, 0);
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn бюджет_шагов_режет_длинный_сценарий() {
        let dir = fixture("budget-steps");
        let journal = dir.join("journal.bin");
        let mut link = crate::model::Stub::seal_many("/method.md", 5);
        let budget = Budget { steps: 2, seconds: 30.0, allowance: 1.0 };
        let outcome = run_task_with_budget(&journal, "тест", &mut link, budget).unwrap();
        assert_eq!(outcome.calls, 2, "ровно два шага");
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn запись_работает_только_внутри_корня() {
        let dir = fixture("write");
        let inside = format!("{} привет", dir.join("новый.md").display());
        let ok = tool_write_in(&inside, &dir).unwrap();
        assert!(ok.contains("записано"), "{ok}");
        assert_eq!(std::fs::read_to_string(dir.join("новый.md")).unwrap(), "привет");

        let outside = if cfg!(windows) { "C:/Windows/Temp/x.md зло" } else { "/etc/x.md зло" };
        let refused = tool_write_in(outside, &dir);
        assert!(refused.is_err(), "{refused:?}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn порядок_читается_из_файла_после_прогона() {
        let dir = std::env::temp_dir().join(format!("hs-loop-file-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let journal = dir.join("journal.bin");
        let method = dir.join("method.md");
        std::fs::write(&method, "тело\n").unwrap();

        let mut provider = crate::model::Stub::seal_method(method.to_str().unwrap());
        run(&journal, &method, &mut provider).unwrap();

        let problems = order_from_journal(&journal).unwrap();
        assert!(problems.is_empty(), "{problems:?}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn оборванный_хвост_виден_при_чтении_файла() {
        let dir = std::env::temp_dir().join(format!("hs-loop-torn-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let journal = dir.join("journal.bin");
        let method = dir.join("method.md");
        std::fs::write(&method, "тело\n").unwrap();

        let mut provider = crate::model::Stub::seal_method(method.to_str().unwrap());
        run(&journal, &method, &mut provider).unwrap();

        // Обрываем последнюю запись: файл короче на 4 байта, как после падения в момент записи.
        let length = std::fs::metadata(&journal).unwrap().len();
        let file = std::fs::OpenOptions::new().write(true).open(&journal).unwrap();
        file.set_len(length - 4).unwrap();
        drop(file);

        let problems = order_from_journal(&journal).unwrap();
        assert!(
            problems.iter().any(|p| p.contains("оборванный хвост")),
            "{problems:?}"
        );
        std::fs::remove_dir_all(&dir).ok();
    }
}
