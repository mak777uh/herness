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

use std::io::BufRead;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

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
    /// Нужен человек: прогон останавливается и `done` не выдаёт.
    Blocked { text: String },
    /// Делать нечего: задача не воспроизводится или устарела.
    NoWork { text: String },
}

fn terminal_rest<'a>(line: &'a str, token: &str) -> Option<&'a str> {
    let rest = line.strip_prefix(token)?;
    if rest.is_empty() || rest.chars().next().is_some_and(char::is_whitespace) {
        Some(rest.trim())
    } else {
        None
    }
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
    if let Some(rest) = terminal_rest(&line, "BLOCKED") {
        return Ok(Step::Blocked { text: rest.to_string() });
    }
    if let Some(rest) = terminal_rest(&line, "NO-WORK") {
        return Ok(Step::NoWork { text: rest.to_string() });
    }
    if let Some(rest) = terminal_rest(&line, "DONE") {
        return Ok(Step::Done { text: rest.to_string() });
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
pub const KNOWN_TOOLS: [&str; 8] =
    ["seal", "netprobe", "net", "search", "list", "read", "write", "head"];

/// Состояние выдачи инструментов. `Missing` и `Invalid` не являются пустым набором:
/// оба означают отказ всего прогона, а не «разрешено всё».
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GrantState {
    Missing,
    Valid(Vec<String>),
    Invalid(String),
}

/// Разобрать `/tools` строго: JSON-массив известных строк, без фильтрации плохих элементов.
/// Пустой массив — валидный deny-all. Любая ошибка запрещает весь список.
pub fn parse_grants(text: &str) -> Result<Vec<String>, String> {
    let value: serde_json::Value = serde_json::from_str(text)
        .map_err(|error| format!("malformed JSON: {error}"))?;
    let items = value
        .as_array()
        .ok_or_else(|| "expected JSON array of tool names".to_string())?;
    let mut granted = Vec::with_capacity(items.len());
    for (index, item) in items.iter().enumerate() {
        let name = item
            .as_str()
            .ok_or_else(|| format!("item {index} is not a string"))?;
        if !KNOWN_TOOLS.contains(&name) {
            return Err(format!("unknown tool at item {index}"));
        }
        granted.push(name.to_string());
    }
    Ok(granted)
}

/// Прочитать выдачу, сохраняя различие между отсутствующим и нечитаемым файлом.
pub fn load_grants(path: &Path) -> GrantState {
    match std::fs::read_to_string(path) {
        Ok(text) => match parse_grants(&text) {
            Ok(granted) => GrantState::Valid(granted),
            Err(error) => GrantState::Invalid(error),
        },
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => GrantState::Missing,
        Err(error) => GrantState::Invalid(format!("read failed: {error}")),
    }
}

/// Сколько знаков из результата попадает в строку истории.
const HISTORY_BRIEF: usize = 120;
/// Сколько знаков последнего результата показывается целиком.
const LAST_RESULT: usize = 12000;
/// Сколько шагов истории держим в подсказке.
const HISTORY_MAX: usize = 6;

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
        let total_chars = text.chars().count();
    let cut: String = if total_chars > LAST_RESULT {
        let head: String = text.chars().take(LAST_RESULT).collect();
        format!("{head}\n… (обрезано: {total_chars} символов, показано {LAST_RESULT})")
    } else {
        text.to_string()
    };
        let truncated = cut.chars().count() < text.chars().count();
        out.push_str(&cut);
        if truncated {
            out.push_str("\n… (обрезано)");
        }
        out.push('\n');
    }
    out.push_str(
        "\nСледующий шаг — одна строка: TOOL <имя> <аргумент>, DONE <итог> или BLOCKED <почему>.\nЕсли в результате есть строка «разные (N): …» — это готовый ответ на вопрос «сколько разных»: отвечай числом N, не перебирая значения.\nЕсли ответ собирается из нескольких результатов (например, имя файла из одного и номер строки из другого) — собери его и ответь; повторный запрос того же самого ничего не добавит.
Если в результатах уже есть ответ — сразу DONE, не ищи синонимы и другие формулировки.\nЕсли ответа нет и найти его в комнате нельзя — ответь BLOCKED и не выдумывай ответ.\nЕсли файл уже прочитан и ответа в нём нет — переходи к другому файлу, а не перечитывай его.\nВ DONE укажи, откуда взят ответ: путь к файлу и строку, например «docs/X.md:3».\nЕсли нужно посчитать что-то по многим файлам — ищи по каталогу, а не читай файлы по одному.\nsearch показывает не больше 40 совпадений и печатает строку «разные (N): …». Если спрашивают, сколько разных значений, — ответ берётся из N, перебирать по одному не нужно.\nЕсли в задаче назван каталог (например runs/dump) — ищи в нём, а не по всему /mnt.\nnet — это ИНТЕРНЕТ, а не комната: net search <запрос> ищет в сети, net open <номер> открывает результат из выдачи, net links показывает ссылки страницы, net follow <номер> переходит по ссылке. Не путай с netprobe: netprobe — только диагностика сети, страниц он не открывает.\nЕсли задача просит найти что-то, чего в комнате НЕТ (утверждение, файл), то «не найдено» — это НЕ ответ, а отсутствие: отвечай BLOCKED, а не DONE. DONE значит «ответ найден и вот он»; BLOCKED значит «искал, но этого нет». Замер 09.11.2026: на задаче про несуществующее утверждение C-5555 модель написала DONE «не найдено» — правильный отказ, но неверная метка.",
    );
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

/// Fresh batch завершается успешно только для доказанного done с валидным порядком.
pub fn loop_succeeded(outcome: &Outcome) -> bool {
    outcome.order_ok() && outcome.status == "done"
}

/// Fresh success требует не только in-memory done, но и цельный корректный журнал на диске.
pub fn loop_succeeded_with_journal(outcome: &Outcome, journal_path: &Path) -> bool {
    loop_succeeded(outcome)
        && matches!(order_from_journal(journal_path), Ok(problems) if problems.is_empty())
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

/// Признак «мы уже внутри цикла». Ставится дочерним процессам, чтобы они не запускали второй.
/// Сам `seal` больше не порождает ребёнка: отпечаток считается в текущем процессе.
pub const LOOP_GUARD: &str = "HS_LOOP_ACTIVE";

/// Объектный отказ: отсутствие и нечитаемость названы кодом, а не общим текстом.
fn object_error(path: &Path, error: std::io::Error) -> String {
    match error.kind() {
        std::io::ErrorKind::NotFound => format!("S10_NOT_FOUND: нет {}", path.display()),
        std::io::ErrorKind::InvalidData => {
            format!("S12_ENCODING: {} не UTF-8 ({error})", path.display())
        }
        _ => format!("не прочитать {}: {error}", path.display()),
    }
}

/// Инструмент `seal`: отпечаток файла без второго процесса.
///
/// Раньше `seal` запускал сам себя через `current_exe` в режиме `seal`. Это второй экземпляр
/// в admitted-пути и лишняя точка, где дочерний процесс может не унаследовать правило.
/// Отпечаток — чистая функция от байтов (`crate::seal_hash`), поэтому считается здесь.
/// Инструмент остаётся вне первого среза (R8/A01): политика и лимит файла действуют.
fn tool_seal(arg: &str) -> Result<String, String> {
    tool_seal_in(arg, &workspace_root())
}

fn tool_seal_in(arg: &str, workspace: &Path) -> Result<String, String> {
    let target = resolve_in(arg, workspace)?;
    let resource = resource_of(&target, workspace, "file")
        .ok_or_else(|| "S6_CLOSURE_BREACH: путь вне корня".to_string())?;
    if !policy_allows("seal", "seal", &resource) {
        return Err(format!("S6_CLOSURE_BREACH: политика не разрешает запечатать: {resource}"));
    }
    let meta = std::fs::metadata(&target).map_err(|error| object_error(&target, error))?;
    if !meta.is_file() {
        return Err(format!("S11_NOT_REGULAR: не обычный файл: {}", target.display()));
    }
    if meta.len() > MAX_FILE {
        return Err(format!("K4_RESOURCE_LIMIT: файл больше {MAX_FILE} байт"));
    }
    let text = std::fs::read_to_string(&target).map_err(|error| object_error(&target, error))?;
    Ok(crate::seal_hash(&text))
}

/// Выход в сеть для агента (ADR-0054): `net search|open|links|follow`.
///
/// Почему через мост, а не напрямую: комната не имеет прямого выхода. Адреса,
/// ключи и журнал остаются на хосте (ADR-0046), а политика разрешает `net`
/// ровно к одному адресу — мосту. Всё остальное для этого инструмента запрещено,
/// и это граница, а не настройка.
///
/// Аргумент передаётся мосту как есть: `search <запрос>`, `open 3`, `links`,
/// `follow 2`. Разбор — на хосте, в одном месте, чтобы правило номеров не
/// разъезжалось между Rust и Python.
fn tool_net(arg: &str) -> Result<String, String> {
    // Адрес моста: сначала файл в образе, потом окружение, потом адрес хоста по умолчанию.
    // Файл — потому что при restrict=on адрес должен быть ГОСТЕВЫМ (10.0.2.15), а переменная
    // окружения в комнату не доходит: initramfs собирается из фиксированного списка (этап 1.3).
    let host = std::fs::read_to_string("/bridge-host")
        .ok()
        .map(|text| text.trim().to_string())
        .filter(|text| !text.is_empty())
        .or_else(|| std::env::var("HS_BRIDGE_HOST").ok())
        .unwrap_or_else(|| "10.0.2.2".to_string());
    let port: u16 = std::env::var("HS_BRIDGE_PORT")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(8790);
    let resource = format!("net:{host}:{port}");
    if !policy_allows("net", "net", &resource) {
        return Err(format!("политика не разрешает обращение: {resource}"));
    }
    let token = std::env::var("HS_BRIDGE_TOKEN").unwrap_or_default();
    if token.is_empty() {
        return Err("нет токена моста (HS_BRIDGE_TOKEN): сеть недоступна".to_string());
    }
    let request_line = arg.trim();
    if request_line.is_empty() {
        return Err("пустой запрос: нужно search <запрос> | open <номер|адрес> | links | follow <номер>"
            .to_string());
    }
    let mut link = crate::model::HttpBridge::new(&host, port, &token, "net");
    link.path = "/v1/net".to_string();
    link.net_request(request_line)
}

/// Диагностический инструмент: проверить правило песочницы в текущем процессе.
///
/// Раньше проба запускала себя же (`current_exe` + режим `sandbox-probe`). Это второй
/// экземпляр в admitted-пути; теперь `probe`/`reach` вызываются напрямую, а `netprobe`
/// остаётся вне первого среза (R8/A01) — его правила и адрес проверяет политика.
fn tool_netprobe(arg: &str) -> Result<String, String> {
    // Посредник: политика решает, к какому адресу можно обращаться.
    // Адрес берётся из аргумента; пустой — значит мост по умолчанию.
    let address = if arg.trim().is_empty() { "10.0.2.2:8790" } else { arg.trim() };
    let resource = format!("net:{address}");
    if !policy_allows("netprobe", "net", &resource) {
        return Err(format!("политика не разрешает обращение: {resource}"));
    }
    let checks = crate::sandbox::probe()?;
    let mut all_ok = true;
    let mut parts: Vec<String> = Vec::new();
    for (name, ok) in checks {
        if !ok {
            all_ok = false;
        }
        parts.push(format!("{name}: {}", if ok { "да" } else { "НЕТ" }));
    }
    let mut out = format!("sandbox: {}", parts.join(", "));
    // Вторая строка отвечает на другой вопрос: не «работает ли фильтр», а «доступен ли адрес».
    match crate::sandbox::reach(address) {
        Ok(()) => out.push_str(&format!("\nreach: {address} доступен")),
        Err(error) => {
            out.push_str(&format!("\nreach: {address} недоступен ({error})"));
            all_ok = false;
        }
    }
    if all_ok { Ok(out) } else { Err(out) }
}

/// Пределы инструментов: лучше честный обрезанный ответ, чем съеденная память.
pub const MAX_FILES: usize = 500;
pub const MAX_DEPTH: usize = 4;
pub const MAX_FILE: u64 = 1024 * 1024;
pub const MAX_MATCHES: usize = 40;
/// Потолок выдачи `read` в байтах. Отдельно от `MAX_FILE`: одна строка не должна вытеснить
/// весь ответ, даже если файл в пределах лимита.
pub const READ_OUTPUT: usize = 8 * 1024;

fn skip_dir(name: &str) -> bool {
    matches!(name, ".git" | "target" | "node_modules" | "__pycache__" | ".venv")
}

fn collect_files(
    dir: &Path,
    depth: usize,
    out: &mut Vec<std::path::PathBuf>,
    problems: &mut Vec<String>,
) {
    if depth > MAX_DEPTH || out.len() >= MAX_FILES {
        return;
    }
    let entries = match std::fs::read_dir(dir) {
        Ok(entries) => entries,
        Err(error) => {
            problems.push(format!("{}: каталог не прочитан ({error})", dir.display()));
            return;
        }
    };
    let mut items = Vec::new();
    for entry in entries {
        match entry {
            Ok(entry) => items.push(entry),
            Err(error) => {
                problems.push(format!("{}: запись не прочитана ({error})", dir.display()));
            }
        }
    }
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
                    collect_files(&path, depth + 1, out, problems);
                }
            }
            Ok(kind) if kind.is_file() => out.push(path),
            Ok(_) => {}
            Err(error) => {
                problems.push(format!("{}: тип записи не определён ({error})", path.display()));
            }
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

/// Политика: что инструменту разрешено. Данные, а не код — поэтому её можно проверить отдельно.
///
/// Источник один: `lab/tools/policy.json` встроен в бинарь на этапе компиляции. Ручной копии
/// в коде больше нет (S5_POLICY_DRIFT): расхождение JSON↔Rust невозможно по построению, а
/// гейт `check_policy_parity.py` проверяет смысл правил и связь с карточкой.
#[derive(Debug, Clone, PartialEq)]
pub enum Effect {
    Allow,
    Deny,
}

#[derive(Debug, Clone)]
pub struct Rule {
    pub tool: String,
    pub action: String,
    pub resource: String,
    pub effect: Effect,
}

const POLICY_JSON: &str = include_str!("../../lab/tools/policy.json");

/// Политика, разобранная один раз. Ошибка разбора — пустой список, то есть тотальный отказ:
/// сломанная политика обязана закрывать, а не открывать.
fn policy_rules() -> &'static [Rule] {
    static RULES: OnceLock<Vec<Rule>> = OnceLock::new();
    RULES.get_or_init(|| parse_policy(POLICY_JSON))
}

fn parse_policy(text: &str) -> Vec<Rule> {
    let Ok(value) = serde_json::from_str::<serde_json::Value>(text) else {
        return Vec::new();
    };
    let Some(items) = value.get("rules").and_then(|rules| rules.as_array()) else {
        return Vec::new();
    };
    let mut rules = Vec::with_capacity(items.len());
    for item in items {
        // Любое битое правило закрывает всю политику. Иначе выпавшее deny-правило
        // превратилось бы в разрешение — сломанная политика обязана закрывать.
        let Some(effect) = (match item.get("effect").and_then(|effect| effect.as_str()) {
            Some("allow") => Some(Effect::Allow),
            Some("deny") => Some(Effect::Deny),
            _ => None,
        }) else {
            return Vec::new();
        };
        let (Some(tool), Some(action), Some(resource)) = (
            item.get("tool").and_then(|value| value.as_str()),
            item.get("action").and_then(|value| value.as_str()),
            item.get("resource").and_then(|value| value.as_str()),
        ) else {
            return Vec::new();
        };
        rules.push(Rule {
            tool: tool.to_string(),
            action: action.to_string(),
            resource: resource.to_string(),
            effect,
        });
    }
    rules
}

/// Проверить политику: разрешено ли инструменту действие над ресурсом.
///
/// Правило приоритета: запрет сильнее разрешения. Если ни одно правило не разрешает — отказ.
/// Это и есть «неявных разрешений нет»: кто не назван, тот не может.
pub fn policy_allows(tool: &str, action: &str, resource: &str) -> bool {
    let mut allowed = false;
    for rule in policy_rules() {
        if rule.tool != tool || rule.action != action {
            continue;
        }
        if !resource_matches(&rule.resource, resource) {
            continue;
        }
        if rule.effect == Effect::Deny {
            return false;
        }
        allowed = true;
    }
    allowed
}

/// Схема ресурса: `file:`, `dir:`, `net:`. Схемы не смешиваются.
fn split_scheme(text: &str) -> (&str, &str) {
    for scheme in ["file:", "dir:", "net:"] {
        if let Some(rest) = text.strip_prefix(scheme) {
            return (scheme, rest);
        }
    }
    ("", text)
}

/// Совпадает ли ресурс с шаблоном политики.
///
/// `!` перед путём — дополнение (deny «всё, кроме»): шаблон совпадает тогда и только тогда,
/// когда путь НЕ совпадает с остатком. `*` — ровно один сегмент, `**` — любой хвост,
/// включая пустой. Схема шаблона и ресурса обязана совпадать: `file:` не матчится с `net:`.
fn resource_matches(pattern: &str, resource: &str) -> bool {
    let (pattern_scheme, pattern_path) = split_scheme(pattern);
    let (resource_scheme, resource_path) = split_scheme(resource);
    if pattern_scheme != resource_scheme {
        return false;
    }
    // Ресурс для политики обязан быть нормализованным. Если в нём остались `.`/`..`,
    // это не «путь с хитростью», а вход, которого политика не видела: отказ.
    if resource_path.split('/').any(|segment| segment == "." || segment == "..") {
        return false;
    }
    let (negated, pattern_path) = match pattern_path.strip_prefix('!') {
        Some(rest) => (true, rest),
        None => (false, pattern_path),
    };
    let matched = glob_path(pattern_path, resource_path);
    if negated {
        !matched
    } else {
        matched
    }
}

fn glob_path(pattern: &str, resource: &str) -> bool {
    let pattern: Vec<&str> = pattern.split('/').collect();
    let resource: Vec<&str> = resource.split('/').collect();
    glob_segments(&pattern, &resource)
}

fn glob_segments(pattern: &[&str], resource: &[&str]) -> bool {
    match pattern.split_first() {
        None => resource.is_empty(),
        Some((&"**", rest)) => {
            if glob_segments(rest, resource) {
                return true;
            }
            match resource.split_first() {
                Some((_, tail)) => glob_segments(pattern, tail),
                None => false,
            }
        }
        Some((&"*", rest)) => match resource.split_first() {
            Some((segment, tail)) if !segment.is_empty() => glob_segments(rest, tail),
            _ => false,
        },
        Some((segment, rest)) => match resource.split_first() {
            Some((actual, tail)) if actual == segment => glob_segments(rest, tail),
            _ => false,
        },
    }
}

/// Ресурс для политики: путь ОТНОСИТЕЛЬНО корня, с префиксом `/mnt`.
///
/// Зачем так: политика объявлена для комнаты (`/mnt`), а корень бывает разным — комната,
/// тесты, хостовый прогон. Ресурс строится от корня, поэтому шаблон `/mnt/**` совпадает
/// буквально и при этом не зависит от того, где физически лежит корень (F-0072).
///
/// Путь нормализуется ДО сравнения: иначе `work/../work2/x` выглядит как `work/**` и
/// проходит разрешение, а ядро пишет в `work2`. Вне корня ресурса нет — `None`, а не
/// замаскированный `/mnt/...`.
fn resource_of(path: &Path, root: &Path, scheme: &str) -> Option<String> {
    let root = normalize(&plain(&root.canonicalize().unwrap_or_else(|_| root.to_path_buf())));
    let path = if path.is_absolute() {
        normalize(&plain(path))
    } else {
        normalize(&plain(&root.join(path)))
    };
    let relative = path.strip_prefix(&root).ok()?;
    let tail = relative.to_string_lossy().replace('\\', "/");
    if tail.is_empty() {
        Some(format!("{scheme}:/mnt"))
    } else {
        Some(format!("{scheme}:/mnt/{}", tail.trim_start_matches('/')))
    }
}

/// Привести путь инструмента к рабочему каталогу и запретить выход наружу.
///
/// Зачем: первый живой прогон показал, что `list .` в комнате печатает `/` — вместе с
/// `bridge-token`. Токен моста — не «файл рядом», а удостоверение комнаты перед хостом; если
/// модель может его прочитать, ограничение «ключ провайдера вне комнаты» остаётся верным, а
/// «комната не может выдать себя за другую» — уже нет (F-0025).
///
/// Политика здесь НЕ проверяется: у каждого инструмента своё действие (`read`, `list`,
/// `search`, `write`), и решать за него — значит проверять чужое правило.
fn resolve_in(arg: &str, root: &Path) -> Result<PathBuf, String> {
    let root = normalize(&plain(&root.canonicalize().unwrap_or_else(|_| root.to_path_buf())));
    let raw = Path::new(arg.trim());
    let joined = if raw.is_absolute() {
        raw.to_path_buf()
    } else {
        root.join(raw)
    };
    // Существующий путь приводим к канонической форме (это же ловит симлинк наружу),
    // несуществующий — сравниваем по нормализованной записи.
    let path = match joined.canonicalize() {
        Ok(real) => normalize(&plain(&real)),
        Err(_) => normalize(&joined),
    };
    // Посредник: решение принимает политика, а не эта функция. Проверка `starts_with` остаётся
    // как дополнительная стена, но отказ формулирует политика — так граница одна.
    if !path.starts_with(&root) {
        return Err(format!(
            "S6_CLOSURE_BREACH: путь вне рабочего каталога {}: {}",
            root.display(),
            arg.trim()
        ));
    }
    Ok(path)
}

/// Найти `needle_lower` в `line` без учёта регистра; вернуть номер СИМВОЛА начала.
///
/// Почему не `line.to_lowercase().find(...)`: lowercasing меняет длину (`İ` → `i` + точка),
/// поэтому байтовая позиция в lowercased строке не является границей символа исходной.
/// Срез по такой позиции паниковал на Unicode. Здесь каждая lowercase-буква помнит, из
/// какого символа исходной строки она получилась.
fn find_ci(line: &str, needle_lower: &str) -> Option<usize> {
    let mut lowered = String::new();
    let mut origin: Vec<usize> = Vec::new();
    for (index, ch) in line.chars().enumerate() {
        for low in ch.to_lowercase() {
            lowered.push(low);
            origin.push(index);
        }
    }
    let byte = lowered.find(needle_lower)?;
    let start_lower = lowered[..byte].chars().count();
    origin.get(start_lower).copied()
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
    // Один resolve: проверка и чтение смотрят на один и тот же путь (TOCTOU между ними сужается).
    let root = resolve_in(dir, workspace)?;
    let resource = resource_of(&root, workspace, "file")
        .ok_or_else(|| "S6_CLOSURE_BREACH: путь вне корня".to_string())?;
    if !policy_allows("search", "read", &resource) {
        return Err(format!("S6_CLOSURE_BREACH: политика не разрешает поиск: {resource}"));
    }
    // Кавычки модель ставит вокруг подстроки, и они уходили в поиск как символы: запрос
    // «"tool/call"» давал 0 совпадений на тексте, где эта строка есть (F-0044).
    let needle = needle.trim().trim_matches('"').trim_matches('\'').trim();
    if needle.chars().count() < 2 {
        return Err("подстрока короче двух символов: слишком много совпадений".to_string());
    }
    // Ошибки обхода не растворяются в «0 найдено»: каждая попадает в отдельную строку ответа.
    let mut problems: Vec<String> = Vec::new();
    let mut files = Vec::new();
    if root.is_dir() {
        collect_files(&root, 0, &mut files, &mut problems);
    } else if root.is_file() {
        files.push(root.clone());
    } else {
        return Err(format!("нет такого пути: {}", root.display()));
    }
    let scanned = files.len();
    let mut matches: Vec<String> = Vec::new();
    let mut truncated = false;
    let lower_needle = needle.to_lowercase();
    // Считаем ВСЕ совпадения и все разные варианты, даже когда показываем только сорок:
    // иначе ответ «сколько разных» получается заниженным (замер: 3 вместо 4).
    let mut total = 0usize;
    let mut tails: Vec<String> = Vec::new();
    for path in files {
        let meta = match std::fs::metadata(&path) {
            Ok(meta) => meta,
            Err(error) => {
                problems.push(format!("{}: метаданные не прочитаны ({error})", path.display()));
                continue;
            }
        };
        if meta.len() > MAX_FILE {
            problems.push(format!("{}: больше {MAX_FILE} байт — не прочитан", path.display()));
            continue;
        }
        let text = match std::fs::read_to_string(&path) {
            Ok(text) => text,
            Err(error) if error.kind() == std::io::ErrorKind::InvalidData => {
                problems.push(format!("S12_ENCODING: {} не UTF-8", path.display()));
                continue;
            }
            Err(error) => {
                problems.push(format!("{}: не прочитан ({error})", path.display()));
                continue;
            }
        };
        for (index, line) in text.lines().enumerate() {
            // Регистр не должен менять ответ: «usually» и «Usually» — одно и то же слово для
            // человека и для задачи (F-0067). Позиция считается по символам исходной строки.
            let Some(start) = find_ci(line, &lower_needle) else {
                continue;
            };
            total += 1;
            let rest: String = line.chars().skip(start).collect();
            let tail: String = rest
                .split_whitespace()
                .take(2)
                .collect::<Vec<_>>()
                .join(" ");
            if !tails.iter().any(|existing| existing == &tail) {
                tails.push(tail);
            }
            if matches.len() < MAX_MATCHES {
                // Окно показа ДОЛЖНО содержать само совпадение (F-SEARCH-1, 09.11.2026).
                //
                // Раньше брались последние 160 символов строки: для длинной строки
                // CLAIMS.md (445 символов, «C-0295» на позиции 2) окно начиналось с
                // 285-го символа, и модель видела тип «test», но не видела, к какому
                // утверждению он относится. Она искала C-0295 девять раз и сдалась.
                //
                // Теперь окно ставится вокруг совпадения: если оно влезает — показываем
                // от начала строки; если нет — от совпадения с многоточием.
                let trimmed = line.trim();
                let chars: Vec<char> = trimmed.chars().collect();
                let leading = line.chars().take_while(|ch| ch.is_whitespace()).count();
                let hit_char = start.saturating_sub(leading);
                let shown: String = if chars.len() <= 160 {
                    trimmed.to_string()
                } else if hit_char < 120 {
                    // Совпадение близко к началу: показываем от начала.
                    format!("{}…", chars.iter().take(160).collect::<String>())
                } else {
                    // Совпадение далеко: окно вокруг него.
                    let start = hit_char.saturating_sub(40);
                    let end = (hit_char + 120).min(chars.len());
                    format!(
                        "…{}…",
                        chars[start..end].iter().collect::<String>()
                    )
                };
                matches.push(format!(
                    "{}:{}: {}",
                    path.display(),
                    index + 1,
                    shown
                ));
            } else {
                truncated = true;
            }
        }
    }
    let mut errors = String::new();
    if !problems.is_empty() {
        let shown = problems.iter().take(8).cloned().collect::<Vec<_>>().join(" | ");
        errors = format!("\nошибки ({}): {shown}", problems.len());
    }
    if matches.is_empty() {
        return Ok(format!("найдено 0 в {scanned} файлах{errors}"));
    }
    // Сводка по файлам: при 20 файлах модели нужно сначала понять, какие читать, иначе она
    // листает подряд и тратит шаги (замер: 5 из 6 задач MuSiQue не дошли до ответа).
    let mut by_file: Vec<(String, usize)> = Vec::new();
    for line in &matches {
        if let Some((path, _)) = line.split_once(':') {
            match by_file.iter_mut().find(|(name, _)| name == path) {
                Some((_, count)) => *count += 1,
                None => by_file.push((path.to_string(), 1)),
            }
        }
    }
    by_file.sort_by(|left, right| right.1.cmp(&left.1));
    let summary: Vec<String> = by_file
        .iter()
        .take(8)
        .map(|(name, count)| format!("{name} ({count})"))
        .collect();
    let mut out = format!(
        "найдено {} в {scanned} файлах{}:",
        total,
        if truncated { " (обрезано)" } else { "" }
    );
    if !summary.is_empty() {
        out.push_str(&format!("\nфайлы: {}", summary.join(", ")));
    }
    if tails.len() > 1 {
        // Число разных вариантов печатается сразу: это и есть ответ на «сколько разных»,
        // без перебора по одному (A-0024). Список обрезается, счёт — нет.
        let total = tails.len();
        tails.truncate(8);
        out.push_str(&format!("\nразные ({total}): {}", tails.join(" | ")));
    }
    for line in matches {
        out.push('\n');
        out.push_str(&line);
    }
    out.push_str(&errors);
    Ok(out)
}

/// `list <каталог>`: имена и размеры, без рекурсии.
fn tool_list(arg: &str) -> Result<String, String> {
    tool_list_in(arg, &workspace_root())
}

fn tool_list_in(arg: &str, workspace: &Path) -> Result<String, String> {
    // Один resolve: решение и чтение каталога смотрят на один путь, без второго окна.
    let root = resolve_in(arg, workspace)?;
    let resource = resource_of(&root, workspace, "dir")
        .ok_or_else(|| "S6_CLOSURE_BREACH: путь вне корня".to_string())?;
    if !policy_allows("list", "list", &resource) {
        return Err(format!("S6_CLOSURE_BREACH: политика не разрешает просмотр: {resource}"));
    }
    let entries = std::fs::read_dir(&root)
        .map_err(|error| format!("не прочитать {}: {error}", root.display()))?;
    // Каталоги идут первыми и с косой чертой: раньше список сортировался по алфавиту вместе с
    // размерами, и при длинном перечне подкаталог «runs» оказался за пределами видимого куска
    // (задача о подсчёте инструментов: модель его не нашла).
    let mut dirs: Vec<String> = Vec::new();
    let mut files: Vec<String> = Vec::new();
    for entry in entries {
        let entry = entry
            .map_err(|error| format!("не прочитать запись {}: {error}", root.display()))?;
        let name = entry.file_name().to_string_lossy().to_string();
        let kind = entry
            .file_type()
            .map_err(|error| format!("нет типа записи {name}: {error}"))?;
        if kind.is_dir() {
            dirs.push(format!("{name}/\tкаталог"));
        } else {
            // Битая запись — отказ, а не «файл размера 0»: молчаливый ноль выглядит как факт.
            let meta = entry
                .metadata()
                .map_err(|error| format!("нет метаданных {name}: {error}"))?;
            files.push(format!("{name}\t{}", meta.len()));
        }
        if dirs.len() + files.len() >= 200 {
            files.push("… (обрезано)".to_string());
            break;
        }
    }
    dirs.sort();
    files.sort();
    dirs.extend(files);
    Ok(dirs.join("\n"))
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
    let resource = resource_of(&path, workspace, "file")
        .ok_or_else(|| "S6_CLOSURE_BREACH: путь вне корня".to_string())?;
    if !policy_allows("read", "read", &resource) {
        return Err(format!("S6_CLOSURE_BREACH: политика не разрешает чтение: {resource}"));
    }
    let meta = std::fs::metadata(&path).map_err(|error| object_error(&path, error))?;
    if !meta.is_file() {
        return Err(format!("S11_NOT_REGULAR: не обычный файл: {}", path.display()));
    }
    if meta.len() > MAX_FILE {
        return Err(format!("K4_RESOURCE_LIMIT: файл больше {MAX_FILE} байт"));
    }
    // Потоковое чтение: файл не материализуется целиком, а строка проверяется ДО добавления.
    // Иначе одна длинная строка могла переполнить ответ, а «файл прочитан целиком» было бы
    // сказано без чтения хвоста.
    let file = std::fs::File::open(&path).map_err(|error| object_error(&path, error))?;
    let mut reader = std::io::BufReader::new(file);
    let mut out = String::new();
    let mut bytes = Vec::new();
    let mut total = 0usize;
    let mut next = from;
    let mut stopped = false;
    loop {
        bytes.clear();
        let read = reader
            .read_until(b'\n', &mut bytes)
            .map_err(|error| format!("не прочитать {}: {error}", path.display()))?;
        if read == 0 {
            break;
        }
        total += 1;
        if total < from {
            continue;
        }
        let raw = std::str::from_utf8(&bytes)
            .map_err(|_| format!("S12_ENCODING: {} не UTF-8 (строка {total})", path.display()))?;
        let line = raw.strip_suffix('\n').unwrap_or(raw);
        let line = line.strip_suffix('\r').unwrap_or(line);
        let rendered = format!("{total}: {line}\n");
        if out.len() + rendered.len() > READ_OUTPUT {
            if out.is_empty() {
                return Err(format!(
                    "K4_RESOURCE_LIMIT: строка {total} длиннее потолка выдачи {READ_OUTPUT} байт"
                ));
            }
            stopped = true;
            next = total;
            break;
        }
        out.push_str(&rendered);
        next = total + 1;
    }
    if out.is_empty() {
        return Ok(format!("строк {from} и далее нет: в файле {total} строк"));
    }
    if stopped {
        out.push_str(&format!(
            "… (обрезано по {READ_OUTPUT} байт; продолжи: read {name} {next})"
        ));
    } else {
        // Файл прочитан до EOF: сказать это явно и запретить искать то же самое.
        // Найдено прогоном S20: файл прочитан, потом восемь шагов поиска того же файла.
        out.push_str(&format!(
            "(файл прочитан целиком, {total} строк; повторно искать его не нужно — ответ уже здесь)"
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
    // Путь нормализуется ДО policy: `work/../work2/x` иначе выглядит как `work/**`.
    let target = if target.is_absolute() {
        normalize(target)
    } else {
        normalize(&root.join(target))
    };
    // Посредник: решение принимает политика, а не эта функция.
    let resource = resource_of(&target, &root, "file")
        .ok_or_else(|| "S6_CLOSURE_BREACH: путь вне корня".to_string())?;
    if !policy_allows("write", "write", &resource) {
        return Err(format!("S6_CLOSURE_BREACH: политика не разрешает запись: {resource}"));
    }
    let bytes = text.as_bytes().len();
    // Запись через openat2 (WRITE-SYMLINK-R1): путь разрешается ядром ОТНОСИТЕЛЬНО открытого
    // корня, с запретом симлинков и выхода за корень. Проверка и открытие — одна операция,
    // поэтому окна между «проверили» и «записали» нет.
    write_beneath(&root, &target, text.as_bytes())
        .map_err(|error| write_refusal(error, &resource))?;
    Ok(format!("записано {bytes} байт в {}", target.display()))
}

/// Отказ записи с кодом из словаря. `EEXIST` — это create-new, а не ошибка ввода:
/// существующий файл не перезаписывается. Переход ФС и симлинк — граница замыкания.
fn write_refusal(error: std::io::Error, resource: &str) -> String {
    #[cfg(unix)]
    match error.raw_os_error() {
        Some(libc::EEXIST) => {
            return format!("S14_ALREADY_EXISTS: {resource} уже существует; create-new не перезаписывает")
        }
        Some(libc::EXDEV) => {
            return format!("S6_CLOSURE_BREACH: запись пересекает границу ФС: {resource}")
        }
        Some(libc::ELOOP) => {
            return format!("S6_CLOSURE_BREACH: симлинк запрещён: {resource}")
        }
        Some(libc::ENOTDIR) => {
            return format!("S6_CLOSURE_BREACH: компонент пути не каталог: {resource}")
        }
        Some(libc::ENOSPC) => {
            return format!("K4_RESOURCE_LIMIT: нет места для записи: {resource}")
        }
        Some(libc::EDQUOT) => {
            return format!("K4_RESOURCE_LIMIT: превышена квота записи: {resource}")
        }
        _ => {}
    }
    format!("S6_CLOSURE_BREACH: не записать {resource}: {error}")
}

/// Записать файл, не выходя за `root` и не следуя симлинкам.
///
/// `openat2` с `RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS` — единственный способ сделать это
/// атомарно: ядро само разрешает путь от открытого каталога и отказывает на любом симлинке.
/// Последовательность `canonicalize -> проверка -> write` оставляет окно: между проверкой и
/// записью симлинк можно подменить.
#[cfg(target_os = "linux")]
fn write_beneath(root: &Path, target: &Path, bytes: &[u8]) -> std::io::Result<()> {
    use std::ffi::CString;
    use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
    use std::os::unix::ffi::OsStrExt;

    // Путь, который ядро разрешит относительно корня: только относительный и без `..`.
    let relative = target
        .strip_prefix(root)
        .map_err(|_| std::io::Error::new(std::io::ErrorKind::PermissionDenied, "вне корня"))?;
    let relative = relative
        .to_str()
        .ok_or_else(|| std::io::Error::new(std::io::ErrorKind::InvalidInput, "путь не в UTF-8"))?;
    let c_relative = CString::new(relative)
        .map_err(|_| std::io::Error::new(std::io::ErrorKind::InvalidInput, "NUL в пути"))?;
    let c_root = CString::new(root.as_os_str().as_bytes())
        .map_err(|_| std::io::Error::new(std::io::ErrorKind::InvalidInput, "NUL в корне"))?;

    // Корень открывается отдельно и один раз: дальше всё считается от его дескриптора.
    let dir_fd = unsafe { libc::open(c_root.as_ptr(), libc::O_DIRECTORY | libc::O_CLOEXEC) };
    if dir_fd < 0 {
        return Err(std::io::Error::last_os_error());
    }
    let dir_fd = unsafe { OwnedFd::from_raw_fd(dir_fd) };

    // `open_how` объявлен `#[non_exhaustive]`: структурный литерал запрещён, поэтому поля
    // заполняются через `MaybeUninit`. Своя копия структуры была бы вторым описанием ABI,
    // и при смене ядром она разошлась бы молча.
    let mut how = std::mem::MaybeUninit::<libc::open_how>::zeroed();
    unsafe {
        let ptr = how.as_mut_ptr();
        // CREATE-NEW: O_EXCL запрещает перезапись существующего файла; O_TRUNC здесь был бы
        // «запись как перезапись» и молча стирал бы чужой результат.
        (*ptr).flags = (libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_CLOEXEC) as u64;
        (*ptr).mode = 0o644;
        (*ptr).resolve = libc::RESOLVE_BENEATH
            | libc::RESOLVE_NO_SYMLINKS
            | libc::RESOLVE_NO_MAGICLINKS
            | libc::RESOLVE_NO_XDEV;
    }
    let how = unsafe { how.assume_init() };
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat2,
            dir_fd.as_raw_fd(),
            c_relative.as_ptr(),
            &how as *const libc::open_how,
            std::mem::size_of::<libc::open_how>(),
        )
    };
    if fd < 0 {
        return Err(std::io::Error::last_os_error());
    }
    let fd = unsafe { OwnedFd::from_raw_fd(fd as i32) };

    let mut written = 0usize;
    while written < bytes.len() {
        let chunk = unsafe {
            libc::write(
                fd.as_raw_fd(),
                bytes[written..].as_ptr() as *const libc::c_void,
                bytes.len() - written,
            )
        };
        if chunk < 0 {
            return Err(std::io::Error::last_os_error());
        }
        written += chunk as usize;
    }
    Ok(())
}

/// Не-Linux: openat2 нет, поэтому остаётся прежний путь с канонизацией. Это **слабее** и
/// названо так в отчёте: на не-Linux защита от симлинка не атомарна.
#[cfg(not(target_os = "linux"))]
fn write_beneath(root: &Path, target: &Path, bytes: &[u8]) -> std::io::Result<()> {
    let parent = target
        .parent()
        .ok_or_else(|| std::io::Error::new(std::io::ErrorKind::InvalidInput, "у пути нет родителя"))?
        .canonicalize()?;
    if !parent.starts_with(root) {
        return Err(std::io::Error::new(
            std::io::ErrorKind::PermissionDenied,
            "вне корня",
        ));
    }
    // Симлинк на самом target проверяется отдельно: на не-Linux атомарности нет.
    if let Ok(meta) = std::fs::symlink_metadata(target) {
        if meta.file_type().is_symlink() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::PermissionDenied,
                "запись через симлинк запрещена",
            ));
        }
    }
    // create-new и здесь: существующий файл не перезаписывается.
    use std::io::Write;
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(target)?;
    file.write_all(bytes)
}

fn tool_write(arg: &str) -> Result<String, String> {
    let root = workspace_root();
    tool_write_in(arg, &root)
}

/// Отправить событие в хостовый журнал, если прогон объявлен хостовым (HS_HOST_RUN).
///
/// Хост берётся из окружения, а не из аргументов: это не «настройка задачи», а адрес
/// свидетельства, и он должен задаваться снаружи комнаты.
fn post_to_host(event: &serde_json::Value) -> Result<(), String> {
    // Адрес моста: сначала файл в образе, потом окружение, потом адрес хоста по умолчанию.
    // Файл — потому что при restrict=on адрес должен быть ГОСТЕВЫМ (10.0.2.15), а переменная
    // окружения в комнату не доходит: initramfs собирается из фиксированного списка (этап 1.3).
    let host = std::fs::read_to_string("/bridge-host")
        .ok()
        .map(|text| text.trim().to_string())
        .filter(|text| !text.is_empty())
        .or_else(|| std::env::var("HS_BRIDGE_HOST").ok())
        .unwrap_or_else(|| "10.0.2.2".to_string());
    let port: u16 = std::env::var("HS_BRIDGE_PORT")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(8790);
    let token = std::env::var("HS_BRIDGE_TOKEN").unwrap_or_default();
    let mut link = crate::model::HttpBridge::new(&host, port, &token, "journal");
    link.post_event(event).map(|_| ())
}

/// Стадия прогона, выведенная из журнала одним правилом: «чего он ждёт».
///
/// Зачем функция: пока стадия собиралась переменной в трёх местах (ядро, приёмка, отчёт), они
/// могли разойтись. Здесь порядок один: терминальные исходы → подтверждение хостом → опора.
pub fn derive_status(events: &[Event]) -> &'static str {
    let has = |kind: &str| events.iter().any(|event| event.kind == kind);
    if has("run/blocked") {
        return "blocked";
    }
    if has("run/no-work") {
        return "no-work";
    }
    let error_with = |needle: &str| {
        events
            .iter()
            .any(|event| event.kind == "step/error" && event.detail.contains(needle))
    };
    if error_with("хост не подтвердил") {
        return "unrecorded";
    }
    if error_with("бюджет денег") {
        return "budget-money";
    }
    if error_with("бюджет времени") {
        return "budget-time";
    }
    // Провайдер не сообщил расход: бюджет проверить нельзя, и `done` был бы утверждением о
    // бюджете, которого нет (план этап 1.5). Проверка стоит до `run/end`, потому что статус
    // выводится из журнала, а не ставится переменной.
    if error_with("не сообщил расход") {
        return "unknown-cost";
    }
    if !has("run/end") {
        return "no-done";
    }
    // «Шаги кончились» — это не «готово без опоры», а «не дошёл»: причина записана в run/end.
    if events
        .iter()
        .any(|event| event.kind == "run/end" && event.detail.starts_with("шаги кончились"))
    {
        return "no-done";
    }
    let anchored = has("claim/anchored");
    if anchored {
        return "done";
    }
    if has("claim/unverified") {
        return "unverified";
    }
    "done-без-опоры"
}

/// Единая точка гранта прогона: что не выдано задачей, то отказ, а не тихий вызов.
///
/// Это не допуск инструмента: допуск выводится из `registry.state.json` ниже. Грант может
/// только сузить набор, но не расширить его. Тестового флага, обходящего обе проверки, нет.
fn tool_authority(name: &str, granted: &[String]) -> Result<(), String> {
    if !granted.iter().any(|tool| tool == name) {
        return Err(format!(
            "S6_CLOSURE_BREACH: инструмент {name} не выдан в этом прогоне"
        ));
    }
    Ok(())
}

/// Состояние инструмента из производного реестра (R8/Q18).
///
/// `active` не хранится ни в `registry.jsonl`, ни здесь: файл — снимок состояния, который
/// `bin/registry_state.py` пересобирает из append-only событий. Неизвестное имя и битый JSON
/// дают `unreviewed`/пустое состояние, то есть отказ, а не «наверное, можно».
fn registry_state_for(name: &str) -> &'static str {
    static STATES: OnceLock<Vec<(String, String)>> = OnceLock::new();
    let states = STATES.get_or_init(|| {
        let value: serde_json::Value =
            serde_json::from_str(include_str!("../../lab/tools/registry.state.json"))
                .unwrap_or(serde_json::Value::Null);
        let mut out = Vec::new();
        if let Some(tools) = value.get("tools").and_then(serde_json::Value::as_object) {
            for (key, record) in tools {
                if let Some(state) = record.get("state").and_then(serde_json::Value::as_str) {
                    out.push((key.clone(), state.to_string()));
                }
            }
        }
        out
    });
    states
        .iter()
        .find(|(key, _)| key == name)
        .map(|(_, state)| state.as_str())
        .unwrap_or("unreviewed")
}

/// `net` — отдельный bridge path вне реестра инструментов: у него своя политика.
///
/// Отдельная функция от состояния нужна, чтобы предикат `active` проверялся
/// тестом на синтетическом состоянии, не подменяя production `registry.state.json`.
fn registry_allows_state(state: &str, name: &str) -> bool {
    name == "net" || state == "active"
}

fn registry_allows(name: &str) -> bool {
    registry_allows_state(registry_state_for(name), name)
}

/// Инструмент с проверкой выдачи и derived authority.
///
/// Зачем: набор инструментов — это полномочие, а не удобство. Прогону, который должен только
/// читать, незачем держать `write` и `seal` включёнными «на всякий случай»: модель может ими
/// воспользоваться, и тогда граница прогона определяется её настроением, а не объявлением.
/// В R8 все шесть legacy переведены в `quarantined`, `search` — в `rejected`, `head` остаётся
/// `candidate`; поэтому запуск каждого из них обязан вернуть `S13_TOOL_INACTIVE`.
fn run_tool_g(name: &str, arg: &str, granted: &[String]) -> Result<String, String> {
    tool_authority(name, granted)?;
    if !registry_allows(name) {
        return Err(format!(
            "S13_TOOL_INACTIVE: {name} в состоянии {}; допуска нет",
            registry_state_for(name)
        ));
    }
    match name {
        "seal" => tool_seal(arg),
        "netprobe" => tool_netprobe(arg),
        "net" => tool_net(arg),
        "search" => tool_search(arg),
        "list" => tool_list(arg),
        "read" => tool_read(arg),
        "write" => tool_write(arg),
        other => Err(format!("неизвестный инструмент: {other}")),
    }
}

/// Число словом → цифра. Нужно для опоры: в тексте «Пять разных механизмов»,
/// а агент отвечает «5». Без этого верный ответ получал unverified (найдено прогоном S20).
/// Число словом → цифра. Сравнение по длине и байтам, без match по строкам:
/// так функция остаётся верифицируемой (Kani упирался в to_lowercase, Verus — в match).
fn number_word(token: &str) -> Option<&'static str> {
    // Таблица: слово в нижнем регистре и цифра. Длина НЕ хранится: `word.len()` всегда
    // в байтах, и это единственная мера, по которой идёт сравнение. Хранимая длина в
    // символах давала None для всей кириллицы («три» — 3 символа, но 6 байт).
    const TABLE: &[(&str, &str)] = &[
        ("один", "1"), ("одна", "1"), ("одно", "1"),
        ("два", "2"), ("две", "2"),
        ("три", "3"),
        ("четыре", "4"),
        ("пять", "5"),
        ("шесть", "6"),
        ("семь", "7"),
        ("восемь", "8"),
        ("девять", "9"),
        ("десять", "10"),
        ("одиннадцать", "11"),
        ("двенадцать", "12"),
        ("тринадцать", "13"),
        ("четырнадцать", "14"),
        ("пятнадцать", "15"),
        ("двадцать", "20"),
        ("тридцать", "30"),
        ("сорок", "40"),
        ("пятьдесят", "50"),
        ("сто", "100"),
    ];
    let bytes = token.as_bytes();
    for (word, digit) in TABLE {
        let word_bytes = word.as_bytes();
        // Длина берётся из слова: она всегда в байтах, как и bytes.len().
        if bytes.len() != word_bytes.len() {
            continue;
        }
        // Сравнение точное, байт за байтом: to_ascii_lowercase не поддержан Verus,
        // а регистр уже приведён вызывающим кодом (normalize_token).
        if word_bytes.iter().zip(bytes.iter()).all(|(a, b)| a == b) {
            return Some(digit);
        }
    }
    None
}

/// Привести токен к сравнимому виду: число словом → цифра, иначе как есть.
fn normalize_token(token: &str) -> String {
    // number_word сравнивает байты точно (Verus не умеет to_ascii_lowercase),
    // поэтому регистр приводим здесь, до вызова.
    let lower = token.to_lowercase();
    match number_word(&lower) {
        Some(digit) => digit.to_string(),
        None => token.to_string(),
    }
}

/// Опора утверждения: минимальная механическая проверка «сказанное взялось из журнала».
///
/// Что это ловит: модель закончила работу, ничего не выполнив, или придумала путь/число, которого
/// инструменты не возвращали. Что это НЕ делает: не проверяет истинность утверждения — только то,
/// что в нём есть хотя бы один элемент, действительно пришедший из результата инструмента.
fn claim_anchor(final_text: &str, tool_results: &[String]) -> Option<String> {
    // Опора должна быть «именем», а не общим словом: иначе проверку удовлетворяет «реестр»
    // или «строка», которые есть в любом отчёте. Требуем цифру или разделитель пути/имени.
    let looks_specific = |token: &str| -> bool {
        // Число словом — конкретный токен, а не общее слово: «Пять» в тексте и «5» в ответе
        // это одна опора. Без этой ветки «Пять» отбрасывалось, и верный ответ получал
        // unverified (найдено прогоном S20).
        // number_word сравнивает байты точно, поэтому регистр приводим здесь.
        // Проверка идёт ДО отбрасывания: иначе «Три» с большой буквы отбрасывалось и
        // опора не срабатывала (60 % ложных отказов на классе number-word).
        if number_word(&token.to_lowercase()).is_some() {
            return true;
        }
        // Чистое число — конкретный токен независимо от длины: ответ «3» на вопрос
        // «сколько теорем» не должен отбрасываться порогом в три знака (60 % ложных
        // отказов на классе number-word, замер bin/oracle_run.py).
        if token.chars().all(|c| c.is_ascii_digit()) {
            return true;
        }
        // Порог 3, а не 4: имена файлов вида p01/p11 — три знака, и правильный ответ с ними
        token.chars().count() >= 3
            && (token.chars().any(|c| c.is_ascii_digit())
                || token.contains('/')
                || token.contains('.')
                || token.contains('_')
                || token.contains('-'))
    };
    let tokens = |text: &str| -> Vec<String> {
        let mut out = Vec::new();
        for part in text.split(|c: char| !(c.is_alphanumeric() || c == '/' || c == '.' || c == '_' || c == '-')) {
            if !looks_specific(part) {
                continue;
            }
            out.push(part.to_string());
            // «p01.md» и «p01» — одно и то же имя файла: иначе ответ «p01» не находит
            // опору в результате чтения, где имя записано с расширением (замер: задача 5).
            if let Some((stem, _)) = part.split_once('.') {
                if looks_specific(stem) {
                    out.push(stem.to_string());
                }
            }
        }
        out
    };
    // Опора ищется во ВСЕХ результатах прогона, а не только в последнем.
    // Замер на 199 случаях (bin/oracle_run.py): поиск только в последнем давал 77 % ложных
    // отказов, когда агент читал несколько файлов и отвечал по первому. Результат инструмента —
    // свидетельство независимо от того, когда он получен; «памятью» его делает не время, а
    // отсутствие в журнале. Всё, что здесь, — из журнала.
    if tool_results.is_empty() {
        return None;
    }
    let haystack: Vec<String> = tool_results.iter().flat_map(|text| tokens(text)).collect();
    let haystack_norm: Vec<String> = haystack.iter().map(|t| normalize_token(t)).collect();
    for token in tokens(final_text) {
        let normalized = normalize_token(&token);
        if haystack.contains(&token) || haystack_norm.contains(&normalized) {
            return Some(token);
        }
    }
    // Ответ часто уточняет имя: «docs/ADR-0052-flail-is-diagnostic.md», тогда как в результате
    // было «ADR-0052». Требуем, чтобы имя из результата целиком входило в имя из ответа и было
    // не короче четырёх знаков, — это не ослабляет опору, а сверяет её по вхождению (F-0037).
    for token in tokens(final_text) {
        // Вхождение проверяется в ОБЕ стороны: «ADR-0001» в ответе и «ADR-0001-test.md» в
        // результате — одно и то же имя файла. Односторонняя проверка давала 50 % ложных
        // отказов на классе direct (замер bin/oracle_run.py).
        let contained = haystack.iter().any(|candidate| {
            candidate.chars().count() >= 4
                && (token.contains(candidate.as_str()) || candidate.contains(token.as_str()))
        });
        if contained {
            // Возвращаем токен ИЗ ОТВЕТА: опора живёт в ответе, а не в результате.
            return Some(token);
        }
    }
    // Третий канал: ссылка «файл:строка» в ответе. Модель часто называет источник путём, а не
    // повтором предмета вопроса («test — /mnt/CLAIMS.md:222»). Считаем опорой саму ссылку, если
    // такая строка есть в результатах: это то, что делает человек — смотрит туда, куда сослались
    // (F-0068).
    referenced_anchor(final_text, tool_results)
}

/// Ссылка «путь:строка» из ответа, подтверждённая результатом инструмента.
fn referenced_anchor(final_text: &str, tool_results: &[String]) -> Option<String> {
    for part in final_text.split_whitespace() {
        let cleaned = part.trim_matches(|c: char| !(c.is_alphanumeric() || "/._:-".contains(c)));
        let Some((path, line)) = cleaned.rsplit_once(':') else { continue };
        if path.len() < 3 || line.is_empty() || !line.chars().all(|c| c.is_ascii_digit()) {
            continue;
        }
        let name = path.rsplit('/').next().unwrap_or(path);
        if name.len() < 3 {
            continue;
        }
        let confirmed = tool_results.iter().any(|result| {
            result.contains(path) || (result.contains(name) && result.contains(&format!(":{line}")))
        });
        if confirmed {
            return Some(cleaned.to_string());
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

    #[derive(PartialEq)]
    enum Phase { Idle, WaitingResult, WaitingStep }
    let mut phase = Phase::Idle;
    let mut ended = false;
    let mut calls = 0usize;
    let mut steps = 0usize;
    for event in events {
        if ended {
            problems.push(format!("событие {} после run/end", event.kind));
        }
        match event.kind {
            "run/end" => {
                if ended {
                    problems.push("повторный run/end".to_string());
                } else {
                    ended = true;
                }
            }
            "tool/call" => {
                calls += 1;
                if phase == Phase::WaitingResult {
                    problems.push("tool/call без result предшествующего вызова".to_string());
                } else if phase == Phase::WaitingStep {
                    problems.push("tool/call без завершающего step предшествующего вызова".to_string());
                } else {
                    phase = Phase::WaitingResult;
                }
            }
            "tool/result" => {
                if phase != Phase::WaitingResult {
                    problems.push("tool/result без предшествующего tool/call".to_string());
                } else {
                    phase = Phase::WaitingStep;
                }
            }
            "step" => {
                steps += 1;
                if phase == Phase::WaitingResult {
                    problems.push("step до tool/result".to_string());
                } else if phase != Phase::WaitingStep {
                    problems.push("step без предшествующего tool/result".to_string());
                } else {
                    phase = Phase::Idle;
                }
            }
            _ => {}
        }
    }
    match phase {
        Phase::WaitingResult => problems.push("tool/call без tool/result".to_string()),
        Phase::WaitingStep => problems.push("tool/call без завершающего step".to_string()),
        Phase::Idle => {}
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
    // Legacy-путь локальной диагностики намеренно перечисляет весь известный набор.
    // Bridge-путь сюда не заходит и обязан передать прочитанную выдачу явно.
    let granted = KNOWN_TOOLS.iter().map(|name| name.to_string()).collect();
    run_task_with_budget(journal_path, task, link, Budget::default(), granted)
}

/// То же, но с явным бюджетом и явной выдачей. Пустой набор — deny-all;
/// неявного «разрешено всё» в API прогона больше нет.
pub fn run_task_with_budget(
    journal_path: &Path,
    task: &str,
    link: &mut dyn ModelLink,
    budget: Budget,
    granted: Vec<String>,
) -> std::io::Result<Outcome> {
    run_task_from(journal_path, task, link, budget, None, false, granted)
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
    granted: Vec<String>,
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
    granted: Vec<String>,
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
    granted: Vec<String>,
) -> std::io::Result<Outcome> {
    let mut journal = Journal::open(journal_path)?;
    let mut events: Vec<Event> = Vec::new();
    let mut steps = start.as_ref().map(|state| state.steps).unwrap_or(0);
    // Петля по информации: тот же вызов + тот же результат (C-0223: 84% против 15%).
    let mut loop_seen: std::collections::HashMap<String, String> = std::collections::HashMap::new();
    let mut loop_hits: usize = 0;
    // Застой: результат не принёс ни одного нового слова. Точный детектор повтора молчит там,
    // где модель перебирает формулировки, а шаги тратятся (A-0017).
    let mut seen_words: std::collections::HashSet<u64> = std::collections::HashSet::new();
    let mut stall_hits: usize = 0;
    const STALL_STOP: usize = 3;
    const LOOP_STOP: usize = 3;
    let mut calls = start.as_ref().map(|state| state.calls).unwrap_or(0);
    let mut attempts = 0usize;
    let mut spent: f64 = start.as_ref().map(|state| state.spent).unwrap_or(0.0);
    // Был ли хоть один ответ модели без данных о расходе.
    let mut cost_unknown = false;
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
    let host_session = std::env::var("HS_HOST_SESSION").ok();

    while attempts < budget.steps && steps < budget.steps {
        if started.elapsed().as_secs_f64() > budget.seconds {
            record(&mut journal, &mut events, "step/error",
                   format!("бюджет времени исчерпан: {:.0} с", budget.seconds))?;
            status = "budget-time";
            break;
        }
        attempts += 1;
        let reply = link.complete(&prompt);
        // Неизвестный расход не считается нулевым: флаг переживёт шаг и даст статус
        // `unknown-cost` вместо `done` (план этап 1.5).
        match link.last_usage() {
            Some(usage) => match usage.allowance {
                Some(money) if money.is_finite() && money >= 0.0 => spent += money,
                _ => cost_unknown = true,
            },
            None => cost_unknown = true,
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
                    "{error}. Ответь одной строкой: TOOL <имя> <аргумент>, DONE <итог> или BLOCKED <почему>."
                ));
                prompt = compose_prompt(task, &history, last.as_deref());
                continue;
            }
        };

        match step {
            Step::Tool { name, arg } => {
                steps += 1;
                record(&mut journal, &mut events, "tool/call", format!("{name} {arg}"))?;
                let mut result_tag = "err";
                let result = run_tool_g(&name, &arg, &granted);
                calls += 1;
                match result {
                    Ok(text) => {
                        result_tag = "ok";
                        record(&mut journal, &mut events, "tool/result", format!("ok {text}"))?;
                        history.push(brief(&format!("{name} {arg}"), &text, true));
                        let key = format!("{name} {arg}");
                        let repeated = loop_seen.get(&key).map(|prev| prev == &text).unwrap_or(false);
                        if repeated { loop_hits += 1; } else { loop_hits = 0; }
                        loop_seen.insert(key, text.clone());
                        // Новизна: считаем слова длиной от 4 символов; если их не было — застой.
                        let mut fresh = 0usize;
                        for word in text.split(|c: char| !c.is_alphanumeric()) {
                            if word.chars().count() < 4 {
                                continue;
                            }
                            let mut hasher = std::collections::hash_map::DefaultHasher::new();
                            std::hash::Hash::hash(word, &mut hasher);
                            if seen_words.insert(std::hash::Hasher::finish(&hasher)) {
                                fresh += 1;
                            }
                        }
                        if fresh == 0 {
                            stall_hits += 1;
                        } else {
                            stall_hits = 0;
                        }
                        if stall_hits >= STALL_STOP {
                            record(&mut journal, &mut events, "run/blocked",
                                   format!("застой: {stall_hits} результата подряд без новых данных"))?;
                            status = "blocked";
                            break;
                        }
                        if repeated {
                            last = Some(format!(
                                "{text}\n\n[петля #{loop_hits}: этот вызов уже давал тот же ответ. Ответь DONE, если ответ уже есть, иначе смени запрос или скажи BLOCKED.]"
                            ));
                        } else {
                            last = Some(text);
                        }
                        if loop_hits >= LOOP_STOP {
                            record(&mut journal, &mut events, "run/blocked",
                                   format!("петля: {loop_hits} повтора без нового результата"))?;
                            status = "blocked";
                            break;
                        }
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
                // Подтверждение хостом шлётся одним потоком в конце прогона: сверяются все события.
                if spent > budget.allowance {
                    record(&mut journal, &mut events, "step/error",
                           format!("бюджет денег исчерпан: {spent:.8} > {:.8}", budget.allowance))?;
                    status = "budget-money";
                    record(&mut journal, &mut events, "run/end", "остановлен бюджетом".to_string())?;
                    break;
                }
            }
            // «Нужен человек» и «делать нечего» — такие же исходы, как done, и так же попадают в
            // журнал отдельным событием: приёмка должна отличать «не смог» от «нечего делать»
            // и от «готово» (H-0006). Опора тут не проверяется: это не утверждение о результате.
            Step::Blocked { text } => {
                record(&mut journal, &mut events, "run/blocked", text)?;
                status = "blocked";
                record(&mut journal, &mut events, "run/end", "ждёт человека".to_string())?;
                break;
            }
            Step::NoWork { text } => {
                record(&mut journal, &mut events, "run/no-work", text)?;
                status = "no-work";
                record(&mut journal, &mut events, "run/end", "делать нечего".to_string())?;
                break;
            }
            Step::Done { text } => {
                // Финальный ответ тоже оплачивается: известный overspend не становится done.
                if spent > budget.allowance {
                    record(&mut journal, &mut events, "step/error",
                           format!("бюджет денег исчерпан: {spent:.8} > {:.8}", budget.allowance))?;
                    record(&mut journal, &mut events, "run/end", "остановлен бюджетом".to_string())?;
                    break;
                }
                // Протокол (доказан в Lean, bin/session_types.py): DONE не может быть первым
                // шагом — нечего завершать. Без TOOL опоры не будет, и «готово» окажется пустым.
                if calls == 0 {
                    record(&mut journal, &mut events, "step/error",
                           "DONE первым шагом: нечего завершать, сначала TOOL".to_string())?;
                    status = "bad-step";
                    last = Some("Ты ещё ничего не сделал. Сначала TOOL, потом DONE.".to_string());
                    prompt = compose_prompt(task, &history, last.as_deref());
                    continue;
                }
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
                // Неизвестный расход — не ноль (план этап 1.5). Событие пишется здесь, а статус
                // из него выводит `derive_status`: одно правило вместо переменной (H-0008).
                if cost_unknown {
                    record(
                        &mut journal,
                        &mut events,
                        "step/error",
                        "провайдер не сообщил расход: бюджет проверить нельзя".to_string(),
                    )?;
                }
                record(&mut journal, &mut events, "run/end", text)?;
                break;
            }
        }
    }

    // Одно правило вместо переменной-счётчика (H-0008): если run/end ещё не записан, пишем его
    // с причиной, а стадию выводим из журнала — так ядро и приёмка считают одно и то же.
    if !events.iter().any(|event| event.kind == "run/end") {
        // Если прогон уже остановлен причиной (петля, застой, отказ), run/end обязан её повторить:
        // иначе журнал противоречит сам себе — «застой» и «шаги кончились» одновременно (F-0042).
        let blocked_reason = events
            .iter()
            .rev()
            .find(|event| event.kind == "run/blocked")
            .map(|event| event.detail.clone());
        let reason = if let Some(detail) = blocked_reason {
            format!("остановлен: {detail}")
        } else if status == "bad-step" {
            format!("провайдер не дал разбираемого шага за {attempts} попыток")
        } else {
            format!("шаги кончились без сигнала завершения (попыток {attempts})")
        };
        record(&mut journal, &mut events, "run/end", reason)?;
    }
    status = derive_status(&events);
    // Подтверждение хостом: отправляем ВЕСЬ поток как refs-only проекции, а не только шаги.
    // Иначе подделка claim/anchored или run/start не ловится сверкой. Run выбирает хост: тело
    // /v1/journal его не содержит; session приходит из host-issued файла образа.
    if host_run.is_some() {
        let mut failure = if host_session.is_none() {
            Some("хост не выдал session для журнала".to_string())
        } else {
            None
        };
        if failure.is_none() {
            let mut projection = crate::host_event::ProjectionState::default();
            for event in &events {
                let payload = match crate::host_event::project_event(
                    event.kind, &event.detail, host_session.as_deref().unwrap_or_default(),
                    &mut projection,
                ) {
                    Ok(payload) => payload,
                    Err(error) => {
                        failure = Some(error);
                        break;
                    }
                };
                if let Err(error) = post_to_host(&payload) {
                    failure = Some(error);
                    break;
                }
            }
        }
        if let Some(error) = failure {
            record(&mut journal, &mut events, "step/error",
                   format!("хост не подтвердил событие: {error}"))?;
            status = "unrecorded";
            record(&mut journal, &mut events, "run/end",
                   "нет подтверждения хоста: свидетельство неполное".to_string())?;
        }
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
    let mut blocks = 0usize;
    let mut ends_with_commit = false;
    for entry in &walked.entries {
        if entry.kind == crate::journal::Kind::Commit {
            blocks += 1;
            if events.is_empty() {
                problems.push("пустой блок перед маркером коммита".to_string());
            } else {
                problems.extend(verify_order(&events));
            }
            events.clear();
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

    if !events.is_empty() {
        problems.push("незавершённый блок после последнего коммита".to_string());
    }
    if blocks == 0 {
        problems.push("в журнале нет завершённых блоков".to_string());
    }
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
        "run/blocked" => "run/blocked",
        "run/no-work" => "run/no-work",
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
    fn поиск_показывает_само_совпадение_в_длинной_строке() {
        // F-SEARCH-1 (09.11.2026). Строка CLAIMS.md на 445 символов, «C-0295» на
        // позиции 2. Прежнее окно брало ПОСЛЕДНИЕ 160 символов, и модель видела
        // тип «test», но не видела, к какому утверждению он относится: она искала
        // C-0295 девять раз и сдалась (провал N07 в прогоне новых задач).
        let dir = fixture("search-window");
        let long_line = format!(
            "| C-0295 | {} | test | команда |",
            "очень длинное описание утверждения ".repeat(10)
        );
        std::fs::write(dir.join("CLAIMS.md"), format!("{long_line}\n")).unwrap();
        let out = tool_search_in("CLAIMS.md C-0295", &dir).unwrap();
        assert!(out.contains("C-0295"), "окно не содержит совпадения: {out}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn поиск_показывает_совпадение_в_середине_строки() {
        // Второй случай: совпадение далеко от начала. Окно ставится вокруг него,
        // а не в конце строки.
        let dir = fixture("search-window-mid");
        let long_line = format!(
            "начало {} СЕРЕДИНА {} конец",
            "заполнитель ".repeat(15),
            "заполнитель ".repeat(15)
        );
        std::fs::write(dir.join("A.md"), format!("{long_line}\n")).unwrap();
        let out = tool_search_in("A.md СЕРЕДИНА", &dir).unwrap();
        assert!(out.contains("СЕРЕДИНА"), "окно не содержит совпадения: {out}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn net_разрешён_только_к_мосту() {
        // ADR-0054: комната не имеет прямого выхода. Разрешён один адрес — мост.
        assert!(policy_allows("net", "net", "net:10.0.2.2:8790"));
        assert!(!policy_allows("net", "net", "net:example.com:443"));
        assert!(!policy_allows("net", "net", "net:1.1.1.1:53"));
        // Запись в файлы для net закрыта: выход в сеть не пишет в комнату.
        assert!(!policy_allows("net", "write", "file:/mnt/work/x"));
    }

    #[test]
    fn net_не_перекрыт_общим_запретом() {
        // Дефект, найденный живым прогоном 09.11.2026: общий запрет `net:**`
        // совпадал и с адресом моста, а запрет сильнее разрешения — net не
        // работал вовсе. Тест держит это исправление: если кто-то вернёт
        // общий запрет, он покраснеет.
        let blanket: Vec<&str> = policy_rules()
            .iter()
            .filter(|rule| rule.tool == "net" && rule.action == "net"
                    && rule.effect == Effect::Deny)
            .map(|rule| rule.resource.as_str())
            .collect();
        assert!(blanket.is_empty(), "общий запрет для net вернулся: {blanket:?}");
    }

    #[test]
    fn policy_разбирается_целиком() {
        // Если include_str или разбор сломались, policy_rules пуста, и всё закрыто.
        // Пустая политика — отказ, но это не «норма»: правило проверяется числом.
        assert_eq!(policy_rules().len(), 23, "policy.json: 23 правила");
    }

    #[test]
    fn policy_с_битым_правилом_закрывает_всё() {
        // Одно битое правило — пустая политика, а не «остальные правила в силе»:
        // выпавшее deny не должно стать разрешением.
        let broken = r#"{"rules":[
            {"tool":"read","action":"read","resource":"file:/mnt/**","effect":"allow"},
            {"tool":"read","action":"write","resource":"file:/mnt/**","effect":"maybe"}
        ]}"#;
        assert!(parse_policy(broken).is_empty());
        let missing = r#"{"rules":[{"tool":"read","action":"read","effect":"deny"}]}"#;
        assert!(parse_policy(missing).is_empty());
    }

    #[test]
    fn policy_запрещает_вне_корня_и_похожий_префикс() {
        assert!(policy_allows("read", "read", "file:/mnt/a.md"));
        assert!(!policy_allows("read", "read", "file:/etc/passwd"));
        // `/mntx` не внутри `/mnt`: граница сегментная, а не префикс строки.
        assert!(!policy_allows("read", "read", "file:/mntx/a.md"));
        assert!(!policy_allows("write", "write", "file:/mnt/work2/x"));
        assert!(!policy_allows("write", "write", "file:/mnt/work/../work2/x"));
    }

    #[test]
    fn policy_понимает_дополнение() {
        // `!` — дополнение: deny «всё, кроме разрешённого».
        assert!(resource_matches("file:!/mnt/**", "file:/etc/passwd"));
        assert!(!resource_matches("file:!/mnt/**", "file:/mnt/a"));
        assert!(resource_matches("net:!10.0.2.2:8790", "net:1.1.1.1:53"));
        assert!(!resource_matches("net:!10.0.2.2:8790", "net:10.0.2.2:8790"));
    }

    #[test]
    fn policy_не_смешивает_схемы() {
        assert!(resource_matches("dir:/mnt/**", "dir:/mnt/a"));
        assert!(!resource_matches("dir:/mnt/**", "file:/mnt/a"));
        assert!(!resource_matches("file:/mnt/**", "net:/mnt/a"));
    }

    #[test]
    fn head_разрешён_только_в_fixtures() {
        assert!(policy_allows("head", "read", "file:/mnt/fixtures/head-slice.txt"));
        assert!(!policy_allows("head", "read", "file:/mnt/work/x"));
        assert!(!policy_allows("head", "read", "file:/etc/passwd"));
        assert!(!policy_allows("head", "write", "file:/mnt/fixtures/x"));
        assert!(!policy_allows("head", "net", "net:10.0.2.2:8790"));
    }

    #[test]
    fn net_есть_в_списке_инструментов() {
        assert!(KNOWN_TOOLS.contains(&"net"));
        // netprobe остаётся: он диагностика сети, а не выход в сеть.
        assert!(KNOWN_TOOLS.contains(&"netprobe"));
    }

    #[test]
    fn выдача_различает_missing_valid_и_invalid() {
        let dir = fixture("grants-state");
        let path = dir.join("tools.json");
        assert_eq!(load_grants(&path), GrantState::Missing);
        assert_eq!(parse_grants("[]").unwrap(), Vec::<String>::new());
        assert_eq!(parse_grants(r#"["net"]"#).unwrap(), vec!["net".to_string()]);
        for bad in ["", "{", "{}", "null", r#""net""#, r#"["net",7]"#, r#"["net","unknown"]"#] {
            assert!(parse_grants(bad).is_err(), "негодная выдача принята: {bad}");
        }
        std::fs::write(&path, r#"["net",7]"#).unwrap();
        assert!(matches!(load_grants(&path), GrantState::Invalid(_)));
        assert!(matches!(load_grants(&dir), GrantState::Invalid(_)));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn пустая_выдача_запрещает_даже_активный_net() {
        let granted = parse_grants("[]").unwrap();
        // Положительный контроль: net действительно имеет derived допуск, поэтому отказ
        // ниже исходит из per-run grant, а не из неактивного состояния реестра.
        assert!(registry_allows("net"));
        assert!(tool_authority("net", &granted).is_err());
        assert!(tool_authority("net", &["net".to_string()]).is_ok());
        let error = run_tool_g("net", "", &granted).unwrap_err();
        assert!(error.contains("не выдан"), "{error}");
    }

    #[test]
    fn fresh_и_resume_применяют_пустую_выдачу_одинаково() {
        let dir = fixture("grants-runtime");
        let fresh = dir.join("fresh.bin");
        let mut link = crate::model::Stub::new(vec![
            "TOOL net".to_string(),
            "DONE проверено".to_string(),
        ]);
        run_task_with_budget(
            &fresh,
            "проверить отказ",
            &mut link,
            Budget { steps: 3, seconds: 10.0, allowance: 1.0 },
            Vec::new(),
        )
        .unwrap();
        let fresh_text = String::from_utf8_lossy(&std::fs::read(&fresh).unwrap()).into_owned();
        assert!(fresh_text.contains("инструмент net не выдан"), "{fresh_text}");

        let resumed = dir.join("resumed.bin");
        {
            let mut journal = Journal::open(&resumed).unwrap();
            journal.append("run/start task: проверить отказ".as_bytes(), Kind::Data).unwrap();
            journal.sync().unwrap();
        }
        let mut link = crate::model::Stub::new(vec![
            "TOOL net".to_string(),
            "DONE проверено".to_string(),
        ]);
        run_task_resume(
            &resumed,
            &mut link,
            Budget { steps: 3, seconds: 10.0, allowance: 1.0 },
            Vec::new(),
        )
        .unwrap();
        let resumed_text = String::from_utf8_lossy(&std::fs::read(&resumed).unwrap()).into_owned();
        assert!(resumed_text.contains("инструмент net не выдан"), "{resumed_text}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn legacy_и_head_не_запускаются_без_допуска() {
        for name in ["seal", "netprobe", "search", "list", "read", "write", "head"] {
            let granted = vec![name.to_string()];
            let error = run_tool_g(name, "", &granted).unwrap_err();
            assert!(
                error.contains("S13_TOOL_INACTIVE"),
                "{name}: ожидался S13_TOOL_INACTIVE, получено {error}"
            );
        }
        // net — отдельный bridge path: реестр его не блокирует.
        assert!(registry_allows("net"));
        // Состояние берётся из производного файла, а не из JSON-флага в снимке.
        assert_eq!(registry_state_for("search"), "rejected");
        assert_eq!(registry_state_for("head"), "candidate");
    }

    #[test]
    fn только_active_даёт_допуск_предикату() {
        // Предикат допускает только derived `active`; test-only событие в реестре
        // обязано остаться `admitted_inactive` и сюда не попасть.
        assert!(registry_allows_state("active", "head"));
        assert!(!registry_allows_state("admitted_inactive", "head"));
        assert!(!registry_allows_state("candidate", "head"));
        assert!(!registry_allows_state("unreviewed", "head"));
        // `net` — отдельный bridge path, но не инструмент реестра.
        assert!(registry_allows_state("unreviewed", "net"));
        // Production-файл не подменяется этим тестом.
        assert_eq!(registry_state_for("head"), "candidate");
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
        assert_eq!(
            problems,
            vec!["tool/call без tool/result".to_string(), "шагов 0, вызовов 1".to_string()]
        );
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
    fn review2_order_oracles() {
        let sequence = |kinds: &[&'static str]| -> Vec<Event> {
            kinds.iter().map(|kind| event(kind)).collect()
        };
        let valid = vec![
            "run/start",
            "tool/call", "tool/result", "step",
            "tool/call", "tool/result", "step",
            "run/end",
        ];
        assert!(verify_order(&sequence(&valid)).is_empty());
        let invalid = [
            (
                vec!["run/start", "tool/call", "step", "tool/result", "step", "run/end"],
                "step до tool/result",
            ),
            (
                vec!["run/start", "step", "tool/call", "tool/result", "step", "run/end"],
                "step без предшествующего tool/result",
            ),
            (
                vec!["run/start", "run/end", "run/end"],
                "повторный run/end",
            ),
            (
                vec!["run/start", "run/end", "note"],
                "событие note после run/end",
            ),
            (
                vec!["note", "run/start", "run/end"],
                "первое событие note, а не run/start",
            ),
        ];
        for (kinds, expected) in invalid {
            let problems = verify_order(&sequence(&kinds));
            assert!(
                problems.iter().any(|problem| problem == expected),
                "нет exact diagnostic {expected}: {problems:?}"
            );
        }
        let no_end = verify_order(&sequence(&["run/start"]));
        assert!(no_end.iter().any(|problem| problem == "последнее событие run/start, а не run/end"));
    }

    #[test]
    fn review1_exact_grant_refusal() {
        let cases = [
            ("err S6_CLOSURE_BREACH: инструмент write не выдан в этом прогоне", "denied"),
            ("err S6_CLOSURE_BREACH: путь вне корня", "error"),
            ("err S6_CLOSURE_BREACH: инструмент read не выдан в этом прогоне", "error"),
            ("err S6_CLOSURE_BREACH: инструмент write не выдан в этом прогоне лишнее", "error"),
            ("err инструмент write не выдан в этом прогоне", "error"),
        ];
        for (result, expected) in cases {
            let projected = crate::host_event::project_events(
                "11111111-1111-4111-8111-111111111111",
                [("tool/call", "write /mnt/x"), ("tool/result", result)],
            ).unwrap();
            assert_eq!(projected[1]["status"], expected, "{result}");
        }
    }

    #[test]
    fn review1_unknown_cost_parity() {
        for detail in [
            "не сообщил расход",
            "провайдер не сообщил расход: бюджет проверить нельзя",
        ] {
            let events = vec![
                event("run/start"),
                Event { kind: "step/error", detail: detail.to_string() },
                event("run/end"),
            ];
            assert_eq!(derive_status(&events), "unknown-cost", "{detail}");
        }
    }

    #[test]
    fn review1_order_state_machine() {
        let sequence = |kinds: &[&'static str]| -> Vec<Event> {
            kinds.iter().map(|kind| event(kind)).collect()
        };
        let valid = vec![
            "run/start",
            "tool/call", "tool/result", "step",
            "tool/call", "tool/result", "step",
            "run/end",
        ];
        assert!(verify_order(&sequence(&valid)).is_empty());
        let invalid = vec![
            vec!["run/start", "tool/call", "step", "tool/result", "run/end"],
            vec!["run/start", "step", "tool/call", "tool/result", "run/end"],
            vec!["run/start", "tool/call", "tool/result", "run/end"],
            vec!["run/start", "run/end", "run/end"],
            vec![
                "run/start", "tool/call", "tool/result", "step", "run/end",
                "run/start", "tool/call", "tool/result", "step", "run/end",
            ],
        ];
        for kinds in invalid {
            let problems = verify_order(&sequence(&kinds));
            assert!(!problems.is_empty(), "ложный PASS: {kinds:?}");
        }
    }

    #[test]
    fn review1_fresh_disk_proof() {
        let dir = fixture("review1-fresh-disk-proof");
        let valid = dir.join("valid.bin");
        let mut journal = Journal::open(&valid).unwrap();
        journal.append(b"run/start task: x", Kind::Data).unwrap();
        journal.append("run/end готово".as_bytes(), Kind::Data).unwrap();
        journal.append(b"", Kind::Commit).unwrap();
        journal.sync().unwrap();
        let outcome = Outcome {
            steps: 0, calls: 0, events: 2, records: 3, commits: 1,
            status: "done", problems: vec![], anchor: None,
        };
        assert!(loop_succeeded(&outcome));
        assert!(loop_succeeded_with_journal(&outcome, &valid));

        let invalid = dir.join("invalid.bin");
        std::fs::write(&invalid, b"NOT-HSJ2\0\0\0\0").unwrap();
        assert!(loop_succeeded(&outcome), "in-memory done остаётся done");
        assert!(!loop_succeeded_with_journal(&outcome, &invalid));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn w03_differential_corpus() {
        let vector: serde_json::Value = serde_json::from_str(include_str!(
            "../../tests/vectors/w03-lifecycle.json"
        ))
        .unwrap();
        for row in vector["terminal"].as_array().unwrap() {
            let actual = parse_step(row["reply"].as_str().unwrap());
            let expected = &row["expect"];
            if expected["error"].as_bool().unwrap_or(false) {
                assert!(actual.is_err(), "terminal collision принята: {}", row["id"]);
                continue;
            }
            let step = actual.unwrap_or_else(|error| panic!("{}: {error}", row["id"]));
            match expected["kind"].as_str().unwrap() {
                "done" => assert_eq!(step, Step::Done { text: expected["text"].as_str().unwrap().to_string() }),
                "blocked" => assert_eq!(step, Step::Blocked { text: expected["text"].as_str().unwrap().to_string() }),
                "no-work" => assert_eq!(step, Step::NoWork { text: expected["text"].as_str().unwrap().to_string() }),
                "tool" => assert_eq!(step, Step::Tool {
                    name: expected["name"].as_str().unwrap().to_string(),
                    arg: expected["arg"].as_str().unwrap().to_string(),
                }),
                other => panic!("неизвестный expected kind: {other}"),
            }
        }
        let static_kind = |kind: &str| -> &'static str {
            match kind {
                "run/start" => "run/start",
                "run/end" => "run/end",
                "run/blocked" => "run/blocked",
                "run/no-work" => "run/no-work",
                "step/error" => "step/error",
                "tool/call" => "tool/call",
                "tool/result" => "tool/result",
                "step" => "step",
                "claim/anchored" => "claim/anchored",
                "claim/unverified" => "claim/unverified",
                other => panic!("неизвестный kind: {other}"),
            }
        };
        let events = |lines: &[String]| -> Vec<Event> {
            lines.iter().map(|line| {
                let (kind, detail) = line.split_once(' ').unwrap_or((line.as_str(), ""));
                Event { kind: static_kind(kind), detail: detail.to_string() }
            }).collect()
        };
        for row in vector["statuses"].as_array().unwrap() {
            let lines: Vec<String> = row["events"].as_array().unwrap().iter()
                .map(|value| value.as_str().unwrap().to_string()).collect();
            assert_eq!(derive_status(&events(&lines)), row["expect"].as_str().unwrap(), "{}", row["id"]);
        }
        for row in vector["pairing"].as_array().unwrap() {
            let lines: Vec<String> = row["events"].as_array().unwrap().iter()
                .map(|value| value.as_str().unwrap().to_string()).collect();
            assert_eq!(verify_order(&events(&lines)).is_empty(), row["valid"].as_bool().unwrap(), "{}", row["id"]);
            let projection_input: Vec<(&str, &str)> = lines.iter().map(|line| {
                line.split_once(' ').unwrap_or((line.as_str(), ""))
            }).collect();
            let projected = crate::host_event::project_events(
                "11111111-1111-4111-8111-111111111111", projection_input,
            );
            if row["id"] == "step-mismatch" {
                assert!(projected.is_ok(), "valid projection pairs: {:?}", projected.err());
            } else {
                assert_eq!(projected.is_ok(), row["valid"].as_bool().unwrap(), "host projection {}", row["id"]);
            }
        }
        for row in vector["authority"].as_array().unwrap() {
            let result = row["result"].as_str().unwrap();
            let projected = crate::host_event::project_events(
                "11111111-1111-4111-8111-111111111111",
                [("tool/call", "write /mnt/x"), ("tool/result", result)],
            ).unwrap();
            let expected = if row["id"] == "structured-refusal" {
                "denied"
            } else if result.starts_with("ok") {
                "ok"
            } else {
                "error"
            };
            assert_eq!(projected[1]["status"], expected, "authority {}", row["id"]);
        }
    }

    #[test]
    fn w03_grant_refusal_is_structured() {
        let error = tool_authority("write", &["search".to_string()]).unwrap_err();
        assert!(error.starts_with("S6_CLOSURE_BREACH:"), "{error}");
        let outcome = |status, problems: Vec<String>| Outcome {
            steps: 1, calls: 1, events: 5, records: 6, commits: 1,
            status, problems, anchor: Some("a.md".to_string()),
        };
        assert!(loop_succeeded(&outcome("done", vec![])));
        assert!(!loop_succeeded(&outcome("unverified", vec![])));
        assert!(!loop_succeeded(&outcome("done", vec!["нарушение порядка".to_string()])));
    }

    #[test]
    fn w03_final_known_cost_overspend_is_not_done() {
        struct CostSequence { replies: Vec<String>, costs: Vec<Option<f64>>, index: usize }
        impl ModelLink for CostSequence {
            fn complete(&mut self, _prompt: &str) -> Reply {
                let reply = self.replies.get(self.index).cloned().unwrap_or_default();
                self.index += 1;
                Reply::Text(reply)
            }
            fn last_usage(&self) -> Option<crate::model::Usage> {
                Some(crate::model::Usage {
                    prompt_tokens: 0,
                    completion_tokens: 0,
                    allowance: self.costs.get(self.index - 1).copied().flatten(),
                })
            }
        }
        let replies = vec!["TOOL list /".to_string(), "DONE готово: a.md".to_string()];
        let vector: serde_json::Value = serde_json::from_str(include_str!(
            "../../tests/vectors/w03-lifecycle.json"
        )).unwrap();
        // Corpus исполняется напрямую: null и malformed cost становятся отсутствующим Usage,
        // а не нулём. Дополнительные invalid-finite cases проверяют ту же fail-closed границу.
        let mut cases: Vec<(String, Option<f64>, f64, bool, &str)> = vector["budget"]
            .as_array().unwrap().iter().map(|row| {
                let cost = row["cost"].as_str().and_then(|value| value.parse::<f64>().ok());
                let allowance = row["allowance"].as_f64().unwrap();
                let expected = match row["id"].as_str().unwrap() {
                    "known-zero" => "done",
                    "known-over" => "budget-money",
                    _ => "unknown-cost",
                };
                (row["id"].as_str().unwrap().to_string(), cost, allowance,
                 row["accepted"].as_bool().unwrap(), expected)
            }).collect();
        cases.extend([
            ("nan".to_string(), Some(f64::NAN), 0.01, false, "unknown-cost"),
            ("infinite".to_string(), Some(f64::INFINITY), 0.01, false, "unknown-cost"),
            ("negative".to_string(), Some(-0.01), 0.01, false, "unknown-cost"),
        ]);
        let mut failures = Vec::new();
        for (name, final_cost, allowance, accepted, expected) in cases {
            let dir = fixture(&format!("w03-final-cost-{name}"));
            let journal = dir.join("journal.bin");
            let mut link = CostSequence {
                replies: replies.clone(), costs: vec![Some(0.0), final_cost], index: 0,
            };
            let outcome = run_task_with_budget(
                &journal, "проверить финальный расход", &mut link,
                Budget { steps: 4, seconds: 10.0, allowance },
                all_tools(),
            ).unwrap();
            if outcome.status != expected || !outcome.order_ok()
                || loop_succeeded(&outcome) != accepted
                || loop_succeeded_with_journal(&outcome, &journal) != accepted
            {
                failures.push(format!("{name}: статус {}, проблемы {:?}", outcome.status, outcome.problems));
            }
            std::fs::remove_dir_all(&dir).ok();
        }
        assert!(failures.is_empty(), "{}", failures.join("; "));
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
    fn стадия_выводится_из_журнала_одним_правилом() {
        let event = |kind: &'static str, detail: &str| Event { kind, detail: detail.to_string() };
        assert_eq!(derive_status(&[event("run/start", "task: x")]), "no-done");
        assert_eq!(
            derive_status(&[event("run/blocked", "нужен доступ"), event("run/end", "ждёт человека")]),
            "blocked"
        );
        assert_eq!(
            derive_status(&[event("run/no-work", "не воспроизводится"), event("run/end", "делать нечего")]),
            "no-work"
        );
        assert_eq!(
            derive_status(&[event("run/end", "готово"), event("claim/anchored", "C-0021")]),
            "done"
        );
        assert_eq!(
            derive_status(&[event("run/end", "готово"), event("claim/unverified", "нет опоры")]),
            "unverified"
        );
        assert_eq!(derive_status(&[event("run/end", "готово")]), "done-без-опоры");
        assert_eq!(
            derive_status(&[
                event("step/error", "хост не подтвердил шаг: недоступен"),
                event("run/end", "нет подтверждения хоста"),
            ]),
            "unrecorded"
        );
    }

    #[test]
    fn разбор_шага_нужен_человек_и_делать_нечего() {
        // H-0006: исходов больше одного. «Не смог» и «нечего делать» — разные состояния,
        // и оба не должны выглядеть как done.
        assert_eq!(
            parse_step("BLOCKED нужен доступ к репозиторию").unwrap(),
            Step::Blocked { text: "нужен доступ к репозиторию".to_string() }
        );
        assert_eq!(
            parse_step("NO-WORK задача не воспроизводится").unwrap(),
            Step::NoWork { text: "задача не воспроизводится".to_string() }
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
        let event = crate::host_event::project_event(
            "step",
            "1",
            "11111111-1111-4111-8111-111111111111",
            &mut crate::host_event::ProjectionState::default(),
        )
        .unwrap();
        let result = post_to_host(&event);
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
        let err = run_task_resume(&path, &mut stub, Budget::default(), Vec::new()).unwrap_err();
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
        let outcome = run_task_resume(&path, &mut stub, budget, vec!["read".to_string()]).unwrap();
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
        assert!(prompt.contains("обрезано:"), "обрезка не отмечена");
        assert!(prompt.contains(&format!("показано {LAST_RESULT}")), "не сказано, сколько показано");
        // История не растёт беспредельно: старое выпадает.
        let many: Vec<String> = (0..40).map(|i| format!("шаг {i}")).collect();
        let prompt = compose_prompt("t", &many, None);
        assert!(!prompt.contains("шаг 0 "), "старое не выпало");
        assert!(prompt.contains("шаг 39"), "новое потерялось");
    }

    #[test]
    fn число_словом_находится_в_любом_регистре() {
        // Опора должна понимать «Три» и «три» одинаково: в тексте число словом,
        // в ответе цифрой (найдено прогоном S15).
        // number_word сравнивает байты точно: регистр приводит normalize_token.
        assert_eq!(number_word("три"), Some("3"), "нижний регистр");
        assert_eq!(number_word("пять"), Some("5"));
        assert_eq!(number_word("сто"), Some("100"));
        assert_eq!(number_word("нет такого"), None);
        // Регистр приводится на уровне normalize_token — так и вызывается опора.
        assert_eq!(normalize_token("Три"), "3", "заглавная первая");
        assert_eq!(normalize_token("ТРИ"), "3", "все заглавные");
        assert_eq!(normalize_token("Пять"), "5");
        assert_eq!(normalize_token("C-0276"), "C-0276", "не число — без изменений");
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
        // 8 событий: start, ответ(TOOL), вызов, результат, шаг, ответ(DONE), claim/unverified,
        // run/end; плюс маркер коммита. Раньше здесь было 9 — лишний run/end, который
        // писался вторым проходом; после H-0008 стадия выводится, а не дописывается.
        assert_eq!(outcome.events, 8);
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

    // --- WRITE-SYMLINK-R1: запись не выходит за корень и не следует симлинкам ---------------

    /// Каталог теста: корень, сосед-снаружи и файл-жертва вне корня.
    fn write_fixture(tag: &str) -> (std::path::PathBuf, std::path::PathBuf) {
        let base = std::env::temp_dir().join(format!("hs-wr-{}-{}", std::process::id(), tag));
        let _ = std::fs::remove_dir_all(&base);
        let root = base.join("root");
        let outside = base.join("outside");
        std::fs::create_dir_all(&root).unwrap();
        // Политика разрешает запись только в `work` (правило `file:/mnt/work/**`), поэтому
        // фикстура повторяет боевой путь, а не пишет в корень.
        std::fs::create_dir_all(root.join("work")).unwrap();
        std::fs::create_dir_all(&outside).unwrap();
        std::fs::write(outside.join("victim.md"), "исходное\n").unwrap();
        (root, outside)
    }

    fn read(path: &std::path::Path) -> String {
        std::fs::read_to_string(path).unwrap_or_default()
    }

    // --- положительные контроли ------------------------------------------------------------

    #[test]
    fn обычная_запись_внутри_корня_проходит() {
        let (root, _outside) = write_fixture("plain");
        let arg = format!("{} содержимое", root.join("work/new.md").display());
        tool_write_in(&arg, &root).expect("запись внутри корня обязана проходить");
        assert_eq!(read(&root.join("work/new.md")), "содержимое");
        std::fs::remove_dir_all(root.parent().unwrap()).ok();
    }

    #[test]
    fn перезапись_существующего_файла_отклонена() {
        // CREATE-NEW: write не перезаписывает. Существующий файл — отказ S14, а не «новое».
        let (root, _outside) = write_fixture("overwrite");
        std::fs::write(root.join("work/a.md"), "старое").unwrap();
        let arg = format!("{} новое", root.join("work/a.md").display());
        let result = tool_write_in(&arg, &root);
        assert!(result.is_err(), "перезапись обязана быть отклонена: {result:?}");
        assert!(result.unwrap_err().starts_with("S14_ALREADY_EXISTS"), "нужен S14");
        assert_eq!(read(&root.join("work/a.md")), "старое", "файл перезаписан или обрезан");
        std::fs::remove_dir_all(root.parent().unwrap()).ok();
    }

    #[test]
    fn повторная_запись_после_создания_отклонена() {
        let (root, _outside) = write_fixture("twice");
        let arg = format!("{} первое", root.join("work/new.md").display());
        tool_write_in(&arg, &root).expect("первая запись CREATE-NEW проходит");
        let again = format!("{} второе", root.join("work/new.md").display());
        let result = tool_write_in(&again, &root);
        assert!(result.is_err(), "вторая запись обязана быть отклонена: {result:?}");
        assert!(result.unwrap_err().starts_with("S14_ALREADY_EXISTS"));
        assert_eq!(read(&root.join("work/new.md")), "первое");
        std::fs::remove_dir_all(root.parent().unwrap()).ok();
    }

    #[test]
    fn запись_в_подкаталог_проходит() {
        let (root, _outside) = write_fixture("subdir");
        std::fs::create_dir_all(root.join("work/sub")).unwrap();
        let arg = format!("{} вложенное", root.join("work/sub/x.md").display());
        tool_write_in(&arg, &root).expect("запись в подкаталог обязана проходить");
        assert_eq!(read(&root.join("work/sub/x.md")), "вложенное");
        std::fs::remove_dir_all(root.parent().unwrap()).ok();
    }

    // --- восемь запрещённых классов ---------------------------------------------------------

    #[test]
    #[cfg(unix)]
    fn симлинк_на_файл_снаружи_отклонён() {
        let (root, outside) = write_fixture("link-file");
        let link = root.join("work/escape.md");
        std::os::unix::fs::symlink(outside.join("victim.md"), &link).unwrap();
        let arg = format!("{} ПОДМЕНА", link.display());
        let result = tool_write_in(&arg, &root);
        assert!(result.is_err(), "запись через симлинк наружу обязана быть отклонена: {result:?}");
        assert_eq!(read(&outside.join("victim.md")), "исходное\n", "файл вне корня изменён");
        std::fs::remove_dir_all(root.parent().unwrap()).ok();
    }

    #[test]
    #[cfg(unix)]
    fn симлинк_на_каталог_снаружи_отклонён() {
        let (root, outside) = write_fixture("link-dir");
        let link = root.join("work/outdir");
        std::os::unix::fs::symlink(&outside, &link).unwrap();
        let arg = format!("{} ПОДМЕНА", link.join("victim.md").display());
        let result = tool_write_in(&arg, &root);
        assert!(result.is_err(), "запись через симлинк-каталог обязана быть отклонена: {result:?}");
        assert_eq!(read(&outside.join("victim.md")), "исходное\n");
        std::fs::remove_dir_all(root.parent().unwrap()).ok();
    }

    #[test]
    #[cfg(unix)]
    fn цепочка_симлинков_отклонена() {
        let (root, outside) = write_fixture("link-chain");
        let first = root.join("work/l1");
        let second = root.join("work/l2");
        std::os::unix::fs::symlink(outside.join("victim.md"), &second).unwrap();
        std::os::unix::fs::symlink(&second, &first).unwrap();
        let arg = format!("{} ПОДМЕНА", first.display());
        assert!(tool_write_in(&arg, &root).is_err(), "цепочка симлинков обязана быть отклонена");
        assert_eq!(read(&outside.join("victim.md")), "исходное\n");
        std::fs::remove_dir_all(root.parent().unwrap()).ok();
    }

    #[test]
    fn путь_с_двумя_точками_наружу_отклонён() {
        let (root, outside) = write_fixture("dotdot");
        let target = root.join("..").join("outside").join("victim.md");
        let arg = format!("{} ПОДМЕНА", target.display());
        assert!(tool_write_in(&arg, &root).is_err(), "`..` наружу обязано быть отклонено");
        assert_eq!(read(&outside.join("victim.md")), "исходное\n");
        std::fs::remove_dir_all(root.parent().unwrap()).ok();
    }

    #[test]
    fn абсолютный_путь_наружу_отклонён() {
        let (root, outside) = write_fixture("absolute");
        let arg = format!("{} ПОДМЕНА", outside.join("victim.md").display());
        assert!(tool_write_in(&arg, &root).is_err(), "абсолютный путь наружу обязано быть отклонено");
        assert_eq!(read(&outside.join("victim.md")), "исходное\n");
        std::fs::remove_dir_all(root.parent().unwrap()).ok();
    }

    #[test]
    #[cfg(unix)]
    fn симлинк_внутри_корня_тоже_отклонён() {
        // RESOLVE_NO_SYMLINKS запрещает ЛЮБОЙ симлинк, в том числе ведущий внутрь корня.
        // Это строже, чем «не выйти за корень», и так и задумано: симлинк в рабочем каталоге
        // агента — не штатный способ записи, а попытка обойти правило.
        let (root, _outside) = write_fixture("link-inside");
        std::fs::write(root.join("work/real.md"), "старое").unwrap();
        let link = root.join("work/alias.md");
        std::os::unix::fs::symlink(root.join("work/real.md"), &link).unwrap();
        let arg = format!("{} новое", link.display());
        assert!(tool_write_in(&arg, &root).is_err(), "симлинк обязан быть отклонён и внутри корня");
        assert_eq!(read(&root.join("work/real.md")), "старое");
        std::fs::remove_dir_all(root.parent().unwrap()).ok();
    }

    #[test]
    #[cfg(unix)]
    fn симлинк_на_несуществующий_файл_снаружи_отклонён() {
        // Симлинк на путь, которого ещё нет: запись создала бы файл снаружи.
        let (root, outside) = write_fixture("link-dangling");
        let link = root.join("work/dangling.md");
        std::os::unix::fs::symlink(outside.join("created.md"), &link).unwrap();
        let arg = format!("{} ПОДМЕНА", link.display());
        assert!(tool_write_in(&arg, &root).is_err(), "висячий симлинк наружу обязан быть отклонён");
        assert!(!outside.join("created.md").exists(), "файл снаружи создан");
        std::fs::remove_dir_all(root.parent().unwrap()).ok();
    }

    fn all_tools() -> Vec<String> {
        KNOWN_TOOLS.iter().map(|name| name.to_string()).collect()
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
    fn поиск_не_режет_строку_по_чужой_позиции() {
        // `İ` в нижнем регистре занимает больше байт, чем в исходной строке. Раньше позиция
        // находилась в lowercased строке и применялась к исходной: срез падал на границе
        // символа. Теперь позиция считается по символам исходной строки.
        let dir = fixture("search-unicode");
        std::fs::write(dir.join("u.md"), "İstanbul МАРКЕР\n").unwrap();
        let out = tool_search_in("u.md МАРКЕР", &dir).unwrap();
        assert!(out.contains("u.md:1:"), "{out}");
        assert!(out.contains("İstanbul"), "{out}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn поиск_называет_нечитаемые_файлы() {
        let dir = fixture("search-problems");
        std::fs::write(dir.join("big.md"), vec![b'x'; MAX_FILE as usize + 1]).unwrap();
        let out = tool_search_in(". МАРКЕР", &dir).unwrap();
        assert!(out.contains("найдено 2"), "{out}");
        assert!(out.contains("ошибки (1)"), "{out}");
        assert!(out.contains("big.md"), "{out}");

        std::fs::write(dir.join("bad.bin"), [0xff, 0xfe, 0x4d]).unwrap();
        let bad = tool_search_in("bad.bin МАРКЕР", &dir).unwrap();
        assert!(bad.starts_with("найдено 0"), "{bad}");
        assert!(bad.contains("S12_ENCODING"), "{bad}");
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
    fn чтение_останавливается_до_потолка_выдачи() {
        let dir = fixture("read-cap-lines");
        let mut body = String::new();
        for index in 1..=1000 {
            body.push_str(&format!("строка {index:04}: значение\n"));
        }
        std::fs::write(dir.join("big.md"), body).unwrap();
        let out = tool_read_in("big.md", &dir).unwrap();
        assert!(out.starts_with("1: строка 0001"), "{out}");
        assert!(out.contains("обрезано по"), "{out}");
        assert!(!out.contains("1000: строка"), "{out}");
        // Потолок относится к файловым строкам; служебный хвост добавляется после него.
        assert!(out.len() <= READ_OUTPUT + 200, "выдача {} байт", out.len());
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn чтение_не_переполняется_одной_строкой() {
        let dir = fixture("read-cap-line");
        let long = "х".repeat(READ_OUTPUT);
        std::fs::write(dir.join("long.md"), format!("{long}\n")).unwrap();
        let error = tool_read_in("long.md", &dir).unwrap_err();
        assert!(error.contains("K4_RESOURCE_LIMIT"), "{error}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn чтение_называет_объектные_отказы() {
        let dir = fixture("read-objects");
        let missing = tool_read_in("нет.md", &dir).unwrap_err();
        assert!(missing.contains("S10_NOT_FOUND"), "{missing}");
        let not_file = tool_read_in(".", &dir).unwrap_err();
        assert!(not_file.contains("S11_NOT_REGULAR"), "{not_file}");
        std::fs::write(dir.join("bad.bin"), [0xff, 0xfe, 0x00]).unwrap();
        let bad = tool_read_in("bad.bin", &dir).unwrap_err();
        assert!(bad.contains("S12_ENCODING"), "{bad}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn список_перечисляет_имена_и_типы() {
        let dir = fixture("list");
        std::fs::create_dir_all(dir.join("work")).unwrap();
        let out = tool_list_in(".", &dir).unwrap();
        assert!(out.contains("a.md"), "{out}");
        assert!(out.contains("каталог"), "{out}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn список_явно_отказывает_на_не_каталоге() {
        let dir = fixture("list-file");
        let error = tool_list_in("a.md", &dir).unwrap_err();
        assert!(error.contains("не прочитать"), "{error}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn печать_считается_в_процессе() {
        let dir = fixture("seal");
        std::fs::create_dir_all(dir.join("work/sub")).unwrap();
        std::fs::write(dir.join("work/sealed.md"), "тело\n").unwrap();
        let expected = crate::seal_hash("тело\n");
        assert_eq!(tool_seal_in("work/sealed.md", &dir).unwrap(), expected);
        let error = tool_seal_in("work/sub", &dir).unwrap_err();
        assert!(error.contains("S11_NOT_REGULAR"), "{error}");
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
            usage: crate::model::Usage { prompt_tokens: 10, completion_tokens: 10, allowance: Some(0.02) },
        };
        let budget = Budget { steps: 10, seconds: 30.0, allowance: 0.01 };
        let outcome = run_task_with_budget(&journal, "тест", &mut link, budget, all_tools()).unwrap();
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
        let outcome = run_task_with_budget(&journal, "тест", &mut link, budget, all_tools()).unwrap();
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
        let outcome = run_task_with_budget(&journal, "тест", &mut link, budget, all_tools()).unwrap();
        assert_eq!(outcome.calls, 2, "ровно два шага");
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        std::fs::remove_dir_all(&dir).ok();
    }

    /// Провайдер, который не сообщает расход: `last_usage` возвращает `None`.
    ///
    /// Настоящий случай: в ответе провайдера нет поля `usage`. Раньше это читалось как
    /// «бесплатно», и бюджет не срабатывал никогда.
    struct NoUsage {
        replies: Vec<String>,
        index: usize,
    }

    impl NoUsage {
        fn new(replies: Vec<String>) -> Self {
            NoUsage { replies, index: 0 }
        }
    }

    impl crate::model::ModelLink for NoUsage {
        fn complete(&mut self, _prompt: &str) -> crate::model::Reply {
            match self.replies.get(self.index).cloned() {
                Some(text) => {
                    self.index += 1;
                    crate::model::Reply::Text(text)
                }
                None => crate::model::Reply::End,
            }
        }
    }

    #[test]
    fn провайдер_без_расхода_даёт_unknown_cost_а_не_done() {
        let dir = fixture("unknown-cost");
        let journal = dir.join("j.bin");
        let method = dir.join("m.md");
        std::fs::write(&method, "тело\n").unwrap();
        let mut link = NoUsage::new(vec![
            format!("TOOL seal {}", method.display()),
            "DONE запечатано: method.md".to_string(),
        ]);
        let budget = Budget { steps: 5, seconds: 30.0, allowance: 1.0 };
        let outcome = run_task_with_budget(&journal, "тест", &mut link, budget, all_tools()).unwrap();
        // Опора есть (имя файла из результата), но стоимость неизвестна: это не `done`.
        assert_eq!(outcome.status, "unknown-cost", "{:?}", outcome.problems);
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn провайдер_с_нулевым_расходом_даёт_done() {
        // Обратная сторона: известный НУЛЕВОЙ расход — это не «неизвестно».
        let dir = fixture("zero-cost");
        let journal = dir.join("j.bin");
        let method = dir.join("m.md");
        std::fs::write(&method, "тело\n").unwrap();
        let mut link = crate::model::Stub::new(vec![
            format!("TOOL seal {}", method.display()),
            "DONE запечатано: method.md".to_string(),
        ]);
        let budget = Budget { steps: 5, seconds: 30.0, allowance: 1.0 };
        let outcome = run_task_with_budget(&journal, "тест", &mut link, budget, all_tools()).unwrap();
        assert_eq!(outcome.status, "done", "{:?}", outcome.problems);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn запись_работает_только_внутри_корня() {
        let dir = fixture("write");
        std::fs::create_dir_all(dir.join("work")).unwrap();
        let inside = format!("{} привет", dir.join("work").join("новый.md").display());
        let ok = tool_write_in(&inside, &dir).unwrap();
        assert!(ok.contains("записано"), "{ok}");
        assert_eq!(std::fs::read_to_string(dir.join("work").join("новый.md")).unwrap(), "привет");

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
    #[test]
    fn опора_находит_имя_файла_без_расширения() {
        // Имя в результате записано с расширением (p01.md), а в ответе — без (p01).
        // Такой ответ получал unverified до правки токенизации (F-0031, задача 5 MuSiQue).
        let results = vec!["p01.md:3 Daniel Webster".to_string()];
        assert_eq!(
            claim_anchor("Fletcher Webster; файлы: p01", &results).as_deref(),
            Some("p01")
        );
    }

}








