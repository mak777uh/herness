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

use std::path::{Path, PathBuf};
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
    // Ответ без метки TOOL, но начинающийся с имени известного инструмента, — это тот же шаг.
    // Зачем: в живых прогонах модель несколько раз писала «read /mnt/CLAIMS.md 91» вместо
    // «TOOL read …». Смысл строки однозначен, а отказ стоил шага и сбивал модель; при этом
    // сырой ответ всё равно попадает в журнал (model/reply), так что послабление ничего не прячет.
    let mut words = line.splitn(2, ' ');
    let first = words.next().unwrap_or_default();
    if KNOWN_TOOLS.contains(&first) {
        let arg = words.next().unwrap_or_default().trim().to_string();
        return Ok(Step::Tool { name: first.to_string(), arg });
    }
    Err(format!(
        "не понял шаг: {}",
        line.chars().take(60).collect::<String>()
    ))
}

/// Имена, которые цикл принимает как инструменты. Список нужен и разбору шага, и подсказке.
pub const KNOWN_TOOLS: [&str; 6] = ["seal", "netprobe", "search", "list", "read", "write"];

/// Сколько знаков из результата попадает в строку истории.
const HISTORY_BRIEF: usize = 120;
/// Сколько знаков последнего результата показывается целиком.
const LAST_RESULT: usize = 4000;
/// Сколько шагов истории держим в подсказке.
const HISTORY_MAX: usize = 12;

fn brief(call: &str, text: &str, ok: bool) -> String {
    let head = text.lines().next().unwrap_or_default().trim();
    format!(
        "{call} → {}: {}",
        if ok { "ok" } else { "ошибка" },
        head.chars().take(HISTORY_BRIEF).collect::<String>()
    )
}

/// Собрать подсказку на шаг: задача + что уже сделано + последний результат.
///
/// Почему не только последний результат: модель без истории теряет цель. Это не «щедрость к
/// модели», а условие выполнимости: задача «найди в файле X» требует помнить, что файл уже
/// прочитан до конца.
fn compose_prompt(task: &str, history: &[String], last: Option<&str>) -> String {
    let mut out = format!("Задача: {task}\n");
    if !history.is_empty() {
        out.push_str("\nУже сделано:\n");
        let from = history.len().saturating_sub(HISTORY_MAX);
        for (index, line) in history[from..].iter().enumerate() {
            out.push_str(&format!("{}) {line}\n", from + index + 1));
        }
    }
    if let Some(text) = last {
        out.push_str("\nПоследний результат:\n");
        let cut: String = text.chars().take(LAST_RESULT).collect();
        let truncated = cut.chars().count() < text.chars().count();
        out.push_str(&cut);
        if truncated {
            out.push_str("\n… (обрезано)");
        }
        out.push('\n');
    }
    out.push_str("\nСледующий шаг — одна строка: TOOL <имя> <аргумент> или DONE <итог>.");
    out
}


#[derive(Debug, Clone)]
pub struct Event {
    pub kind: &'static str,
    pub detail: String,
}

#[derive(Debug)]
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

/// Состояние, восстановленное из журнала после обрыва: с него продолжается работа.
///
/// Зачем отдельная структура: продолжение — это не «ещё один прогон», а тот же прогон с уже
/// потраченными шагами и уже прочитанной историей. Если начать с нуля, бюджет удвоится, а модель
/// заново прочитает то, что уже читала.
#[derive(Debug)]
pub struct Resumed {
    pub task: String,
    pub steps: usize,
    pub calls: usize,
    pub spent: f64,
    pub history: Vec<String>,
    pub last: Option<String>,
    /// Результаты инструментов до обрыва: продолжение наследует их как свидетельства.
    pub results: Vec<String>,
    /// Хвост, который не читается (оборванная запись). Его нельзя оставлять: новые записи после
    /// него перестанут читаться вообще.
    pub torn: usize,
    /// Прогон уже закрыт коммитом — продолжать нечего.
    pub closed: bool,
}

/// Прочитать из журнала, что успело произойти до обрыва.
///
/// Правила те же, что у чтения: разбор идёт до первой невалидной записи, хвост не «чинится»,
/// а помечается числом байт. Продолжение разрешено только для незакрытого прогона.
pub fn resume_state(path: &Path) -> Result<Resumed, String> {
    let bytes = std::fs::read(path).map_err(|error| format!("журнал не прочитать: {error}"))?;
    let walked = crate::journal::walk(&bytes)?;
    let mut state = Resumed {
        task: String::new(),
        steps: 0,
        calls: 0,
        spent: 0.0,
        history: Vec::new(),
        last: None,
        results: Vec::new(),
        torn: walked.tail_bytes,
        closed: false,
    };
    let mut pending: Option<String> = None;
    for entry in &walked.entries {
        if entry.kind == crate::journal::Kind::Commit {
            state.closed = true;
            continue;
        }
        let event = decode_event(&entry.payload);
        match event.kind {
            "run/start" => {
                state.task = event
                    .detail
                    .strip_prefix("task: ")
                    .unwrap_or(&event.detail)
                    .to_string();
                // Продолжение уже начатого прогона начинается с начала: предыдущие шаги живут
                // в прежних записях, и повторный run/start не должен их обнулять.
                state.closed = false;
            }
            "tool/call" => pending = Some(event.detail.clone()),
            "tool/result" => {
                let ok = event.detail.starts_with("ok ");
                let text = event
                    .detail
                    .strip_prefix("ok ")
                    .or_else(|| event.detail.strip_prefix("err "))
                    .unwrap_or(&event.detail)
                    .to_string();
                let call = pending.take().unwrap_or_else(|| "?".to_string());
                state.history.push(brief(&call, &text, ok));
                state.results.push(text.clone());
                state.last = Some(text);
            }
            "step" => {
                state.steps += 1;
                if let Some(value) = event.detail.split("потрачено ").nth(1) {
                    if let Ok(spent) = value.trim().parse::<f64>() {
                        state.spent = spent;
                    }
                }
            }
            "claim/anchored" | "claim/unverified" => {}
            _ => {}
        }
    }
    state.calls = state.history.len();
    Ok(state)
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
    // HS_TOOL: только инструмент просит ребёнка сказать вслух про фильтр. Замер стоимости
    // запуска (20 «seal» подряд) идёт без этой переменной, иначе журнал забивается шумом.
    command.env("HS_TOOL", "1");
    // Фильтр ставит сам ребёнок первой строкой (`harden_self`): `pre_exec` в нашем ядре не
    // работает (F-0024), а без фильтра «инструмент в песочнице» был бы только словом.
    let output = command
        .output()
        .map_err(|error| format!("не запустить инструмент: {error}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if output.status.success() {
        // Граница видна в журнале: если фильтр не встал, это часть результата, а не слух.
        let stderr = String::from_utf8_lossy(&output.stderr);
        let note = if stderr.contains("фильтр UDP не поставлен") {
            " [песочница: фильтра нет, ядро без seccomp]"
        } else {
            ""
        };
        Ok(format!("{stdout}{note}"))
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

/// Привести путь инструмента к рабочему каталогу и запретить выход наружу.
///
/// Зачем: первый живой прогон показал, что `list .` в комнате печатает `/` — вместе с
/// `bridge-token`. Токен моста — не «файл рядом», а удостоверение комнаты перед хостом; если
/// модель может его прочитать, ограничение «ключ провайдера вне комнаты» остаётся верным, а
/// «комната не может выдать себя за другую» — уже нет (F-0025).
fn normalize(path: &Path) -> PathBuf {
    use std::path::Component;
    let mut out = PathBuf::new();
    for part in path.components() {
        match part {
            Component::CurDir => {}
            Component::ParentDir => {
                out.pop();
            }
            other => out.push(other.as_os_str()),
        }
    }
    out
}

/// Убрать Windows-префикс `\\?\`: его добавляет `canonicalize`, и без этого сравнение путей
/// «внутри корня» ложно срабатывает даже для файла внутри каталога.
fn plain(path: &Path) -> PathBuf {
    let text = path.to_string_lossy();
    match text.strip_prefix(r"\\?\") {
        Some(rest) => PathBuf::from(rest),
        None => path.to_path_buf(),
    }
}

fn resolve_in(arg: &str, root: &Path) -> Result<PathBuf, String> {
    let root = normalize(&plain(&root.canonicalize().unwrap_or_else(|_| root.to_path_buf())));
    let raw = Path::new(arg.trim());
    let joined = if raw.is_absolute() { raw.to_path_buf() } else { root.join(raw) };
    // Существующий путь приводим к канонической форме (это же ловит симлинк наружу),
    // несуществующий — сравниваем по нормализованной записи.
    let path = match joined.canonicalize() {
        Ok(real) => normalize(&plain(&real)),
        Err(_) => normalize(&joined),
    };
    if !path.starts_with(&root) {
        return Err(format!(
            "путь вне рабочего каталога {}: {}",
            root.display(),
            arg.trim()
        ));
    }
    Ok(path)
}

/// `search <путь> <подстрока>`: искать по содержимому, без shell и без внешних программ.
///
/// Зачем своей реализацией, а не через `grep`: в комнате нет ни shell, ни coreutils, а тащить
/// busybox — это +2,12 МБ (C-0140). Поиск — примитив, его дешевле держать внутри цикла.
///
/// Путь может быть и каталогом, и файлом. Почему и файлом: модель в прогоне 4 написала
/// `search /mnt/CLAIMS.md statistics` — то есть попросила ровно то, что имела в виду, — и
/// получила «не каталог». Отказ инструмента на осмысленном запросе стоит шагов и сбивает модель.
fn tool_search(arg: &str) -> Result<String, String> {
    tool_search_in(arg, &workspace_root())
}

fn tool_search_in(arg: &str, workspace: &Path) -> Result<String, String> {
    let (dir, needle) = arg
        .split_once(' ')
        .ok_or_else(|| "нужно: search <путь> <подстрока>".to_string())?;
    let needle = needle.trim();
    if needle.chars().count() < 2 {
        return Err("подстрока короче двух символов: слишком много совпадений".to_string());
    }
    let root = resolve_in(dir, workspace)?;
    let mut files = Vec::new();
    if root.is_dir() {
        collect_files(&root, 0, &mut files);
    } else if root.is_file() {
        files.push(root.clone());
    } else {
        return Err(format!("нет такого пути: {}", root.display()));
    }
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
    tool_list_in(arg, &workspace_root())
}

fn tool_list_in(arg: &str, workspace: &Path) -> Result<String, String> {
    let root = resolve_in(arg, workspace)?;
    let entries = std::fs::read_dir(&root)
        .map_err(|error| format!("не прочитать {}: {error}", root.display()))?;
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

/// `read <файл> [с_строки]`: текст до 8 КиБ, с номерами строк — чтобы модель могла ссылаться на место.
///
/// Почему второй аргумент обязателен по смыслу, хотя формально необязателен: файл CLAIMS.md —
/// 65 КБ, а окно чтения 8 КБ. Без продолжения модель упирается в «обрезано» и читает файл
/// сначала, теряя шаги (так и случилось в прогоне 2: 8 шагов, ни одного ответа). Обрезка без
/// способа продолжить — это ловушка, а не предел.
fn tool_read(arg: &str) -> Result<String, String> {
    tool_read_in(arg, &workspace_root())
}

fn tool_read_in(arg: &str, workspace: &Path) -> Result<String, String> {
    // Второй аргумент отделяем с конца: путь может содержать пробелы, номер строки — нет.
    let (name, from) = match arg.rsplit_once(' ') {
        Some((left, right)) if right.trim().parse::<usize>().is_ok() => {
            (left.trim(), right.trim().parse::<usize>().unwrap_or(1).max(1))
        }
        _ => (arg.trim(), 1usize),
    };
    if name.is_empty() {
        return Err("нужно: read <файл> [с_строки]".to_string());
    }
    let path = resolve_in(name, workspace)?;
    let meta = std::fs::metadata(&path).map_err(|error| format!("нет файла: {error}"))?;
    if meta.len() > MAX_FILE {
        return Err(format!("файл больше {MAX_FILE} байт"));
    }
    let text = std::fs::read_to_string(&path).map_err(|error| format!("не прочитать: {error}"))?;
    let total = text.lines().count();
    let mut out = String::new();
    let mut next = from;
    for (index, line) in text.lines().enumerate().skip(from.saturating_sub(1)) {
        if out.len() >= MAX_READ {
            break;
        }
        out.push_str(&format!("{}: {}\n", index + 1, line));
        next = index + 2;
    }
    if out.is_empty() {
        return Ok(format!("строк {from} и далее нет: в файле {total} строк"));
    }
    if next <= total {
        out.push_str(&format!(
            "… (обрезано; всего {total} строк, продолжи: read {name} {next})"
        ));
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
    run_tool_g(name, arg, None)
}

/// Отправить событие в хостовый журнал, если прогон объявлен хостовым (HS_HOST_RUN).
///
/// Хост берётся из окружения, а не из аргументов: это не «настройка задачи», а адрес
/// свидетельства, и он должен задаваться снаружи комнаты.
fn post_to_host(run: &str, event: &str) -> Result<(), String> {
    let host = std::env::var("HS_BRIDGE_HOST").unwrap_or_else(|_| "10.0.2.2".to_string());
    let port: u16 = std::env::var("HS_BRIDGE_PORT")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(8790);
    let token = std::env::var("HS_BRIDGE_TOKEN").unwrap_or_default();
    let mut link = crate::model::HttpBridge::new(&host, port, &token, "journal");
    link.post_event(run, event).map(|_| ())
}

/// Инструмент с проверкой выдачи: что не выдано в этом прогоне, то отказ, а не тихий вызов.
///
/// Зачем: набор инструментов — это полномочие, а не удобство. Прогону, который должен только
/// читать, незачем держать `write` и `seal` включёнными «на всякий случай»: модель может ими
/// воспользоваться, и тогда граница прогона определяется её настроением, а не объявлением.
fn run_tool_g(name: &str, arg: &str, granted: Option<&[String]>) -> Result<String, String> {
    if let Some(list) = granted {
        if !list.iter().any(|tool| tool == name) {
            return Err(format!("инструмент {name} не выдан в этом прогоне"));
        }
    }
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
    // Опора должна быть «именем», а не общим словом: иначе проверку удовлетворяет «реестр»
    // или «строка», которые есть в любом отчёте. Требуем цифру или разделитель пути/имени.
    let looks_specific = |token: &str| -> bool {
        token.chars().count() >= 4
            && (token.chars().any(|c| c.is_ascii_digit())
                || token.contains('/')
                || token.contains('.')
                || token.contains('_')
                || token.contains('-'))
    };
    let tokens = |text: &str| -> Vec<String> {
        text.split(|c: char| !(c.is_alphanumeric() || c == '/' || c == '.' || c == '_' || c == '-'))
            .filter(|part| looks_specific(part))
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
    run_task_from(journal_path, task, link, budget, None, false, None)
}

/// Прогон с долговечным журналом: каждый шаг сбрасывается на диск.
///
/// Зачем отдельная функция: только так прогон на диске переживает обрыв питания, и только тогда
/// продолжение имеет что читать. Плата — sync на каждый шаг.
pub fn run_task_durable(
    journal_path: &Path,
    task: &str,
    link: &mut dyn ModelLink,
    budget: Budget,
    granted: Option<Vec<String>>,
) -> std::io::Result<Outcome> {
    run_task_from(journal_path, task, link, budget, None, true, granted)
}

/// Продолжить прогон, оборванный падением, с того места, где он остановился.
///
/// Что берётся из журнала: задача, число шагов и вызовов, расход, история для подсказки.
/// Оборванный хвост отрезается: новые записи после него не читались бы вообще, а валидных байт в
/// нём нет по определению. Факт отрезания записывается в журнал, чтобы это не было тихой правкой.
pub fn run_task_resume(
    journal_path: &Path,
    link: &mut dyn ModelLink,
    budget: Budget,
    granted: Option<Vec<String>>,
) -> std::io::Result<Outcome> {
    let state = resume_state(journal_path).map_err(|error| std::io::Error::other(error))?;
    if state.closed {
        return Err(std::io::Error::other("прогон уже закрыт коммитом: продолжать нечего"));
    }
    if state.torn > 0 {
        let length = std::fs::metadata(journal_path)?.len() - state.torn as u64;
        let file = std::fs::OpenOptions::new().write(true).open(journal_path)?;
        file.set_len(length)?;
        file.sync_all()?;
    }
    let task = if state.task.is_empty() {
        "продолжение без задачи: в журнале нет run/start".to_string()
    } else {
        // Recovery note — приём из разбора dsh-superagent (docs/003): после обрыва нельзя
        // повторять внешние действия вслепую. Модель видит это в подсказке, а не только на хосте.
        format!(
            "{}\n\nПродолжение после обрыва. Сначала проверь, что уже сделано (файлы каталога, \
             история работы, результаты выше), и не повторяй действий, которые уже выполнены \
             или выполнены частично.",
            state.task
        )
    };
    run_task_from(journal_path, &task, link, budget, Some(state), true, granted)
}

fn run_task_from(
    journal_path: &Path,
    task: &str,
    link: &mut dyn ModelLink,
    budget: Budget,
    start: Option<Resumed>,
    durable: bool,
    granted: Option<Vec<String>>,
) -> std::io::Result<Outcome> {
    let mut journal = Journal::open(journal_path)?;
    let mut events: Vec<Event> = Vec::new();
    let mut steps = start.as_ref().map(|state| state.steps).unwrap_or(0);
    let mut calls = start.as_ref().map(|state| state.calls).unwrap_or(0);
    let mut attempts = 0usize;
    let mut spent: f64 = start.as_ref().map(|state| state.spent).unwrap_or(0.0);
    let mut anchor: Option<String> = None;
    let started = std::time::Instant::now();
    let mut status: &'static str = "no-done";

    let opening = match &start {
        Some(state) => format!(
            "task: {task} (продолжение: шагов {}, вызовов {}, потрачено {:.8}, отрезано хвоста {} байт)",
            state.steps, state.calls, state.spent, state.torn
        ),
        None => format!("task: {task}"),
    };
    record(&mut journal, &mut events, "run/start", opening)?;
    // История шагов. Зачем: пока в подсказке был только последний результат, модель теряла и
    // задачу, и то, что уже прочитала: в живом прогоне она дошла до конца файла и вместо ответа
    // снова начала перечислять каталог (7 прогонов подряд, F-0026). Бюджет подсказки ограничен:
    // по строке на шаг и один последний результат целиком.
    let mut history: Vec<String> = start
        .as_ref()
        .map(|state| state.history.clone())
        .unwrap_or_default();
    let mut last: Option<String> = start.as_ref().and_then(|state| state.last.clone());
    let prior_results: Vec<String> = start
        .as_ref()
        .map(|state| state.results.clone())
        .unwrap_or_default();
    let mut prompt = compose_prompt(task, &history, last.as_deref());
    let host_run = std::env::var("HS_HOST_RUN").ok();

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
                last = Some(format!(
                    "{error}. Ответь одной строкой: TOOL <имя> <аргумент> или DONE <итог>."
                ));
                prompt = compose_prompt(task, &history, last.as_deref());
                continue;
            }
        };

        match step {
            Step::Tool { name, arg } => {
                steps += 1;
                record(&mut journal, &mut events, "tool/call", format!("{name} {arg}"))?;
                let result = run_tool_g(&name, &arg, granted.as_deref());
                calls += 1;
                match result {
                    Ok(text) => {
                        record(&mut journal, &mut events, "tool/result", format!("ok {text}"))?;
                        history.push(brief(&format!("{name} {arg}"), &text, true));
                        last = Some(text);
                    }
                    Err(error) => {
                        record(&mut journal, &mut events, "tool/result", format!("err {error}"))?;
                        history.push(brief(&format!("{name} {arg}"), &error, false));
                        last = Some(format!("ошибка: {error}"));
                    }
                }
                prompt = compose_prompt(task, &history, last.as_deref());
                record(&mut journal, &mut events, "step",
                       format!("{steps}, потрачено {spent:.8}"))?;
                // Долговечность на каждом шаге: журнал на диске нужен для продолжения после
                // обрыва питания. Без sync файл остаётся в кэше, и обрыв уносит прогон целиком —
                // продолжать будет нечего (F-0027).
                if durable {
                    journal.sync()?;
                }
                // Подтверждение хостом (H-0007): если прогон объявлен хостовым и хост не принял
                // событие, это не «мелкая ошибка сети», а отсутствие свидетельства. Тогда done не
                // выдаётся вовсе: статус unrecorded, и приёмка такой прогон не примет.
                if let Some(run) = host_run.as_deref() {
                    if let Err(error) = post_to_host(run, &format!("step {steps}")) {
                        record(&mut journal, &mut events, "step/error",
                               format!("хост не подтвердил шаг: {error}"))?;
                        status = "unrecorded";
                        record(&mut journal, &mut events, "run/end",
                               "нет подтверждения хоста: свидетельство неполное".to_string())?;
                        break;
                    }
                }
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
                // Свидетельства продолжаются через обрыв: результаты, полученные до падения,
                // принадлежат тому же прогону, и отбрасывать их значило бы требовать от модели
                // заново прочитать уже прочитанное (иначе верный ответ получал unverified).
                let mut results: Vec<String> = prior_results.clone();
                results.extend(
                    events
                        .iter()
                        .filter(|event| event.kind == "tool/result")
                        .map(|event| event.detail.clone()),
                );
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
    fn событие_хосту_без_моста_это_ошибка_а_не_тишина() {
        // H-0007: если хост недоступен, событие не считается доставленным. Без этого «done,
        // подтверждённое хостом» было бы словом, а не состоянием.
        std::env::set_var("HS_BRIDGE_HOST", "127.0.0.1");
        std::env::set_var("HS_BRIDGE_PORT", "9");
        let result = post_to_host("run-test", "step 1");
        std::env::remove_var("HS_BRIDGE_HOST");
        std::env::remove_var("HS_BRIDGE_PORT");
        assert!(result.is_err(), "без моста событие не должно считаться отправленным");
    }

    #[test]
    fn продолжение_читает_шаги_задачу_и_расход() {
        let path = torn_fixture("resume-read");
        let state = resume_state(&path).unwrap();
        assert_eq!(state.steps, 1, "шагов {}", state.steps);
        assert_eq!(state.calls, 1);
        assert!(state.task.contains("найти X"), "{}", state.task);
        assert_eq!(state.history.len(), 1);
        assert_eq!(state.torn, 4, "хвост {}", state.torn);
        assert!(!state.closed);
        std::fs::remove_dir_all(path.parent().unwrap()).ok();
    }

    #[test]
    fn закрытый_прогон_не_продолжается() {
        let dir = fixture("resume-closed");
        let path = dir.join("journal.bin");
        {
            let mut journal = Journal::open(&path).unwrap();
            journal.append("run/start task: t".as_bytes(), Kind::Data).unwrap();
            journal.append("run/end всё".as_bytes(), Kind::Data).unwrap();
            journal.append(b"commit", Kind::Commit).unwrap();
            journal.sync().unwrap();
        }
        assert!(resume_state(&path).unwrap().closed);
        let mut stub = crate::model::Stub::new(vec!["DONE готово".to_string()]);
        let err = run_task_resume(&path, &mut stub, Budget::default(), None).unwrap_err();
        assert!(err.to_string().contains("закрыт коммитом"), "{err}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn продолжение_учитывает_прежние_шаги_и_не_ломает_порядок() {
        let path = torn_fixture("resume-go");
        let mut stub = crate::model::Stub::new(vec![
            "TOOL read a.md".to_string(),
            "DONE первая строка прочитана".to_string(),
        ]);
        let budget = Budget { steps: 4, seconds: 10.0, allowance: 0.01 };
        let outcome = run_task_resume(&path, &mut stub, budget, None).unwrap();
        assert_eq!(outcome.steps, 2, "шагов {}", outcome.steps);
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        let state = resume_state(&path).unwrap();
        assert!(state.closed, "прогон должен быть закрыт коммитом");
        assert_eq!(state.torn, 0, "оборванный хвост должен быть отрезан");
        std::fs::remove_dir_all(path.parent().unwrap()).ok();
    }

    /// Журнал, который оборвался посреди записи: шаг сделан, коммита нет, хвост нечитаем.
    fn torn_fixture(tag: &str) -> std::path::PathBuf {
        let dir = fixture(tag);
        let path = dir.join("journal.bin");
        {
            let mut journal = Journal::open(&path).unwrap();
            journal.append("run/start task: найти X".as_bytes(), Kind::Data).unwrap();
            journal.append(b"tool/call read a.md", Kind::Data).unwrap();
            journal.append(b"tool/result ok 1: first line", Kind::Data).unwrap();
            journal.append("step 1, потрачено 0.00010000".as_bytes(), Kind::Data).unwrap();
            journal.sync().unwrap();
        }
        {
            let mut file = std::fs::OpenOptions::new().append(true).open(&path).unwrap();
            use std::io::Write;
            file.write_all(b"\x10\x00\x00\x00").unwrap();
        }
        path
    }

    #[test]
    fn подсказка_несёт_задачу_историю_и_последний_результат() {
        let history = vec![
            "read /mnt/CLAIMS.md → ok: 1: # CLAIMS.md".to_string(),
            "list /mnt → ok: CLAIMS.md файл".to_string(),
        ];
        let prompt = compose_prompt("найти statistics", &history, Some("страница 2"));
        assert!(prompt.starts_with("Задача: найти statistics"), "{prompt}");
        assert!(prompt.contains("1) read /mnt/CLAIMS.md"), "{prompt}");
        assert!(prompt.contains("2) list /mnt"), "{prompt}");
        assert!(prompt.contains("Последний результат:\nстраница 2"), "{prompt}");
        // Длинный результат обрезается, и это сказано словами, а не молча.
        let long = "я".repeat(LAST_RESULT + 10);
        let prompt = compose_prompt("t", &[], Some(&long));
        assert!(prompt.contains("… (обрезано)"), "обрезка не отмечена");
        // История не растёт беспредельно: старое выпадает.
        let many: Vec<String> = (0..40).map(|i| format!("шаг {i}")).collect();
        let prompt = compose_prompt("t", &many, None);
        assert!(!prompt.contains("шаг 0 "), "старое не выпало");
        assert!(prompt.contains("шаг 39"), "новое потерялось");
    }

    #[test]
    fn шаг_без_метки_TOOL_но_с_именем_инструмента_принимается() {
        // Живые прогоны: модель писала «read /mnt/CLAIMS.md 91» — смысл ясен, отказ стоил шага.
        assert_eq!(
            parse_step("read /mnt/CLAIMS.md 91").unwrap(),
            Step::Tool { name: "read".to_string(), arg: "/mnt/CLAIMS.md 91".to_string() }
        );
        assert_eq!(
            parse_step("list /mnt").unwrap(),
            Step::Tool { name: "list".to_string(), arg: "/mnt".to_string() }
        );
        // Слово вне списка инструментов по-прежнему ошибка: послабление не превращается в догадки.
        assert!(parse_step("прочитать BRIEF.md").is_err());
    }

    #[test]
    fn общее_слово_не_считается_опорой() {
        // «реестр» есть и в журнале, и в ответе, но это не опора — это вода.
        assert_eq!(claim_anchor("прочитан реестр", &["ok прочитан реестр".to_string()]), None);
        let anchor = claim_anchor(
            "строка 150 в CLAIMS.md",
            &["ok CLAIMS.md:150: | C-0122 |".to_string()],
        )
        .unwrap();
        assert!(anchor == "150" || anchor == "CLAIMS.md", "{anchor}");
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
        let out = tool_search_in(" МАРКЕР", &dir).unwrap();
        assert!(out.contains("найдено 2"), "{out}");
        assert!(out.contains("a.md:2:"), "{out}");
        assert!(out.contains("b.md:1:"), "{out}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn поиск_идёт_и_по_одному_файлу() {
        // Прогон 4: модель попросила `search /mnt/CLAIMS.md statistics` и получила «не каталог».
        let dir = fixture("search-file");
        let out = tool_search_in("a.md МАРКЕР", &dir).unwrap();
        assert!(out.contains("найдено 1"), "{out}");
        assert!(out.contains("a.md:2:"), "{out}");
        assert!(tool_search_in("неттакого.md МАРКЕР", &dir).is_err());
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn поиск_без_совпадений_говорит_об_этом_числом() {
        let dir = fixture("none");
        let out = tool_search_in(" нетакого", &dir).unwrap();
        assert!(out.starts_with("найдено 0"), "{out}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn поиск_отбивает_короткую_иголку_и_не_каталог() {
        let dir = fixture("short");
        assert!(tool_search_in(" и", &dir).is_err());
        assert!(tool_search_in("/нет/такого иго", &dir).is_err());
        assert!(tool_search_in("без_пробела", &dir).is_err());
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn чтение_даёт_номера_строк() {
        let dir = fixture("read");
        let out = tool_read_in("a.md", &dir).unwrap();
        assert!(out.starts_with("1: первая строка"), "{out}");
        assert!(out.contains("МАРКЕР"), "{out}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn чтение_продолжается_с_указанной_строки() {
        let dir = fixture("read-more");
        let full = std::fs::read_to_string(dir.join("a.md")).unwrap();
        let total = full.lines().count();
        let out = tool_read_in(&format!("a.md {}", total), &dir).unwrap();
        assert!(out.starts_with(&format!("{total}: ")), "{out}");
        assert!(!out.contains("обрезано"), "{out}");
        assert!(tool_read_in(&format!("a.md {}", total + 5), &dir).unwrap().contains("нет"));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn список_перечисляет_имена_и_типы() {
        let dir = fixture("list");
        let out = tool_list_in(".", &dir).unwrap();
        assert!(out.contains("a.md"), "{out}");
        assert!(out.contains("каталог"), "{out}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn инструменты_не_выходят_из_рабочего_каталога() {
        // F-0025: в первом живом прогоне `list .` напечатал корень комнаты вместе с bridge-token.
        let dir = fixture("escape");
        for bad in ["..", "/etc", "/etc/passwd", "../..", "a.md/../../.."] {
            assert!(tool_list_in(bad, &dir).is_err(), "list {bad} не отбит");
            assert!(tool_read_in(bad, &dir).is_err(), "read {bad} не отбит");
        }
        assert!(tool_search_in("../.. МАРКЕР", &dir).is_err());
        // Внутри каталога по-прежнему можно: и относительным путём, и абсолютным.
        assert!(tool_read_in("a.md", &dir).is_ok());
        assert!(tool_read_in(&dir.join("a.md").display().to_string(), &dir).is_ok());
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





