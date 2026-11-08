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
    /// Нужен человек: прогон останавливается и `done` не выдаёт.
    Blocked { text: String },
    /// Делать нечего: задача не воспроизводится или устарела.
    NoWork { text: String },
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
    if let Some(rest) = line.strip_prefix("BLOCKED") {
        return Ok(Step::Blocked { text: rest.trim().to_string() });
    }
    if let Some(rest) = line.strip_prefix("NO-WORK") {
        return Ok(Step::NoWork { text: rest.trim().to_string() });
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
pub const KNOWN_TOOLS: [&str; 7] =
    ["seal", "netprobe", "net", "search", "list", "read", "write"];

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
Если в результатах уже есть ответ — сразу DONE, не ищи синонимы и другие формулировки.\nЕсли ответа нет и найти его в комнате нельзя — ответь BLOCKED и не выдумывай ответ.\nЕсли файл уже прочитан и ответа в нём нет — переходи к другому файлу, а не перечитывай его.\nВ DONE укажи, откуда взят ответ: путь к файлу и строку, например «docs/X.md:3».\nЕсли нужно посчитать что-то по многим файлам — ищи по каталогу, а не читай файлы по одному.\nsearch показывает не больше 40 совпадений и печатает строку «разные (N): …». Если спрашивают, сколько разных значений, — ответ берётся из N, перебирать по одному не нужно.\nЕсли в задаче назван каталог (например runs/dump) — ищи в нём, а не по всему /mnt.\nnet — это ИНТЕРНЕТ, а не комната: net search <запрос> ищет в сети, net open <номер> открывает результат из выдачи, net links показывает ссылки страницы, net follow <номер> переходит по ссылке. Не путай с netprobe: netprobe — только диагностика сети, страниц он не открывает.",
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
    // Посредник: политика решает, можно ли запечатать этот файл.
    {
        let target = resolve_in(arg, &workspace_root())?;
        let resource = resource_of(&target, &workspace_root());
        if !policy_allows("seal", "seal", &resource) {
            return Err(format!("политика не разрешает запечатать: {resource}"));
        }
    }
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
    let host = std::env::var("HS_BRIDGE_HOST").unwrap_or_else(|_| "10.0.2.2".to_string());
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

/// Диагностический инструмент: проверить, что правило песочницы унаследовано процессом.
fn tool_netprobe(arg: &str) -> Result<String, String> {
    // Посредник: политика решает, к какому адресу можно обращаться.
    // Адрес берётся из аргумента; пустой — значит мост по умолчанию.
    let address = if arg.trim().is_empty() { "10.0.2.2:8790" } else { arg.trim() };
    let resource = format!("net:{address}");
    if !policy_allows("netprobe", "net", &resource) {
        return Err(format!("политика не разрешает обращение: {resource}"));
    }
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
pub const MAX_READ: usize = 24 * 1024;

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

/// Политика: что инструменту разрешено. Данные, а не код — поэтому её можно проверить отдельно.
///
/// Зачем отдельная структура: раньше граница была размазана по функциям («здесь проверяем,
/// здесь не забыли»). Теперь она объявлена один раз и проверяется в одном месте — это посредник
/// из flowguard-spec: не «система безопасна», а «мимо этой точки значение не пройдёт».
#[derive(Debug, Clone, PartialEq)]
pub enum Effect {
    Allow,
    Deny,
}

#[derive(Debug, Clone)]
pub struct Rule {
    pub tool: &'static str,
    pub action: &'static str,
    pub resource: &'static str,
    pub effect: Effect,
}

/// Политика инструментов. Совпадает с lab/tools/policy.json; расхождение ловит гейт.
pub const POLICY: &[Rule] = &[
    Rule { tool: "read", action: "read", resource: "file:/mnt/**", effect: Effect::Allow },
    Rule { tool: "read", action: "write", resource: "file:/mnt/**", effect: Effect::Deny },
    Rule { tool: "read", action: "net", resource: "net:**", effect: Effect::Deny },
    Rule { tool: "search", action: "read", resource: "file:/mnt/**", effect: Effect::Allow },
    Rule { tool: "search", action: "write", resource: "file:/mnt/**", effect: Effect::Deny },
    Rule { tool: "search", action: "net", resource: "net:**", effect: Effect::Deny },
    Rule { tool: "list", action: "list", resource: "dir:/mnt/**", effect: Effect::Allow },
    Rule { tool: "list", action: "write", resource: "file:/mnt/**", effect: Effect::Deny },
    Rule { tool: "write", action: "write", resource: "file:/mnt/work/**", effect: Effect::Allow },
    Rule { tool: "write", action: "net", resource: "net:**", effect: Effect::Deny },
    Rule { tool: "seal", action: "seal", resource: "file:/mnt/work/**", effect: Effect::Allow },
    Rule { tool: "netprobe", action: "net", resource: "net:10.0.2.2:8790", effect: Effect::Allow },
    // net — выход в сеть для агента (ADR-0054). Разрешён ТОЛЬКО к мосту: комната
    // не имеет прямого выхода, адреса и ключи остаются на хосте (ADR-0046).
    //
    // Общего запрета `net:**` здесь НЕТ намеренно: он совпадал бы и с адресом
    // моста (`**` берёт любой хвост), а запрет сильнее разрешения — тогда net
    // не работал бы вовсе. Ненужен он и по принципу политики: «неявных
    // разрешений нет», кто не назван — тот не может. Разрешён один адрес,
    // всё остальное запрещено по умолчанию.
    Rule { tool: "net", action: "net", resource: "net:10.0.2.2:8790", effect: Effect::Allow },
    Rule { tool: "net", action: "write", resource: "file:/mnt/**", effect: Effect::Deny },
];

/// Проверить политику: разрешено ли инструменту действие над ресурсом.
///
/// Правило приоритета: запрет сильнее разрешения. Если ни одно правило не разрешает — отказ.
/// Это и есть «неявных разрешений нет»: кто не назван, тот не может.
pub fn policy_allows(tool: &str, action: &str, resource: &str) -> bool {
    let mut allowed = false;
    for rule in POLICY {
        if rule.tool != tool || rule.action != action {
            continue;
        }
        if !resource_matches(rule.resource, resource) {
            continue;
        }
        if rule.effect == Effect::Deny {
            return false;
        }
        allowed = true;
    }
    allowed
}

/// Совпадает ли ресурс с шаблоном политики. `**` — любой хвост, `*` — один сегмент.
///
/// `/mnt` в шаблоне означает «внутри корня», а не буквально путь: корень бывает разным
/// (комната `/mnt`, тесты — временный каталог, хостовый прогон — свой). Поэтому шаблон
/// сравнивается по хвосту после `/mnt`.
/// Ресурс для политики: путь ОТНОСИТЕЛЬНО корня, с префиксом `/mnt`.
///
/// Зачем так: политика объявлена для комнаты (`/mnt`), а корень бывает разным — комната,
/// тесты, хостовый прогон. Ресурс строится от корня, поэтому шаблон `/mnt/**` совпадает
/// буквально и при этом не зависит от того, где физически лежит корень (F-0072).
fn resource_of(path: &Path, root: &Path) -> String {
    let path = plain(path);
    let root = plain(&root.canonicalize().unwrap_or_else(|_| root.to_path_buf()));
    let relative = path.strip_prefix(&root).map(|tail| tail.to_path_buf()).unwrap_or(path);
    let tail = relative.display().to_string().replace('\\', "/");
    if tail.is_empty() {
        "file:/mnt".to_string()
    } else {
        format!("file:/mnt/{}", tail.trim_start_matches('/'))
    }
}

/// Снять схему ресурса: file:, dir:, net: говорят, что это, а не где.
fn strip_scheme(text: &str) -> &str {
    for scheme in ["file:", "dir:", "net:"] {
        if let Some(rest) = text.strip_prefix(scheme) {
            return rest;
        }
    }
    text
}

fn resource_matches(pattern: &str, resource: &str) -> bool {
    // Схема ресурса (file:, dir:, net:) не участвует в сравнении: она говорит, что это,
    // а не где. Иначе dir:/mnt/** и file:/mnt/** считались бы разными шаблонами.
    let pattern = strip_scheme(pattern);
    let resource = strip_scheme(resource);
    // Шаблон проверяется БУКВАЛЬНО (F-0072). Раньше `/mnt/**` совпадал с любым ресурсом,
    // потому что «внутри корня» проверялось отдельно в resolve_in. Но `policy_allows` —
    // публичная функция: с `file:/etc/passwd` она отвечала «разрешено». Сверка с моделью
    // в Lean показала 10 расхождений из 18, все в сторону разрешения.
    if let Some(prefix) = pattern.strip_suffix("/**") {
        return resource == prefix || resource.starts_with(&format!("{prefix}/"));
    }
    if let Some(prefix) = pattern.strip_suffix("**") {
        return resource.starts_with(prefix);
    }
    pattern == resource
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
    // Посредник: решение принимает политика, а не эта функция. Проверка `starts_with` остаётся
    // как дополнительная стена, но отказ формулирует политика — так граница одна.
    if !path.starts_with(&root) {
        return Err(format!(
            "путь вне рабочего каталога {}: {}",
            root.display(),
            arg.trim()
        ));
    }
    let resource = resource_of(&path, &root);
    if !policy_allows("read", "read", &resource) {
        return Err(format!("политика не разрешает чтение: {resource}"));
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
    // Посредник: политика решает, можно ли искать в этом каталоге.
    {
        let target = resolve_in(dir, workspace)?;
        let resource = resource_of(&target, workspace);
        if !policy_allows("search", "read", &resource) {
            return Err(format!("политика не разрешает поиск: {resource}"));
        }
    }
    // Кавычки модель ставит вокруг подстроки, и они уходили в поиск как символы: запрос
    // «"tool/call"» давал 0 совпадений на тексте, где эта строка есть (F-0044).
    let needle = needle.trim().trim_matches('"').trim_matches('\'').trim();
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
    // Считаем ВСЕ совпадения и все разные варианты, даже когда показываем только сорок:
    // иначе ответ «сколько разных» получается заниженным (замер: 3 вместо 4).
    let mut total = 0usize;
    let mut tails: Vec<String> = Vec::new();
    for path in files {
        let Ok(meta) = std::fs::metadata(&path) else { continue };
        if meta.len() > MAX_FILE {
            continue;
        }
        let Ok(text) = std::fs::read_to_string(&path) else { continue };
        for (index, line) in text.lines().enumerate() {
            // Регистр не должен менять ответ: «usually» и «Usually» — одно и то же слово для
            // человека и для задачи (F-0067).
            let lower_line = line.to_lowercase();
            let lower_needle = needle.to_lowercase();
            if !lower_line.contains(&lower_needle) {
                continue;
            }
            total += 1;
            if let Some(position) = lower_line.find(&lower_needle) {
                let tail: String = line[position..]
                    .split_whitespace()
                    .take(2)
                    .collect::<Vec<_>>()
                    .join(" ");
                if !tails.iter().any(|existing| existing == &tail) {
                    tails.push(tail);
                }
            }
            if matches.len() < MAX_MATCHES {
                // Окно показа сдвигается к совпадению: иначе слово за 160-м символом находится,
                // но не показывается, и поиск по нему следом даёт ноль (F-0066).
                let trimmed = line.trim();
                let start = trimmed.chars().count().saturating_sub(160);
                let shown: String = if start == 0 {
                    trimmed.chars().take(160).collect()
                } else {
                    let offset = trimmed
                        .char_indices()
                        .nth(start.min(trimmed.chars().count().saturating_sub(1)))
                        .map(|(byte, _)| byte)
                        .unwrap_or(0);
                    format!("…{}", trimmed[offset..].chars().take(160).collect::<String>())
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
    if matches.is_empty() {
        return Ok(format!("найдено 0 в {scanned} файлах"));
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
    if matches.is_empty() {
        return Ok(format!("найдено 0 в {scanned} файлах"));
    }
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
    Ok(out)
}

/// `list <каталог>`: имена и размеры, без рекурсии.
fn tool_list(arg: &str) -> Result<String, String> {
    tool_list_in(arg, &workspace_root())
}

fn tool_list_in(arg: &str, workspace: &Path) -> Result<String, String> {
    // Посредник: политика решает, можно ли смотреть этот каталог.
    {
        let target = resolve_in(arg, workspace)?;
        let resource = resource_of(&target, workspace).replace("file:", "dir:");
        if !policy_allows("list", "list", &resource) {
            return Err(format!("политика не разрешает просмотр: {resource}"));
        }
    }
    let root = resolve_in(arg, workspace)?;
    let entries = std::fs::read_dir(&root)
        .map_err(|error| format!("не прочитать {}: {error}", root.display()))?;
    // Каталоги идут первыми и с косой чертой: раньше список сортировался по алфавиту вместе с
    // размерами, и при длинном перечне подкаталог «runs» оказался за пределами видимого куска
    // (задача о подсчёте инструментов: модель его не нашла).
    let mut dirs: Vec<String> = Vec::new();
    let mut files: Vec<String> = Vec::new();
    for entry in entries.flatten() {
        let meta = entry.metadata().ok();
        let name = entry.file_name().to_string_lossy().to_string();
        match entry.file_type() {
            Ok(kind) if kind.is_dir() => dirs.push(format!("{name}/\tкаталог")),
            _ => files.push(format!("{name}\t{}", meta.map(|m| m.len()).unwrap_or(0))),
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
    } else {
        // Файл прочитан целиком: сказать это явно и запретить искать то же самое.
        // Найдено прогоном S20: файл прочитан, потом восемь шагов поиска того же файла.
        // Это не подсказка ответа, а граница: повторный поиск прочитанного — трата шагов.
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
    // Посредник: решение принимает политика, а не эта функция.
    let resource = resource_of(target, &root);
    if !policy_allows("write", "write", &resource) {
        return Err(format!("политика не разрешает запись: {resource}"));
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
                let result = run_tool_g(&name, &arg, granted.as_deref());
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
    // Подтверждение хостом: отправляем ВЕСЬ поток событий, а не только шаги. Иначе подделка
    // claim/anchored или run/start не ловится сверкой (асимметрия, отмеченная в отчёте).
    if let Some(run) = host_run.as_deref() {
        for event in &events {
            let line = format!("{} {}", event.kind, event.detail).trim().to_string();
            if let Err(error) = post_to_host(run, &line) {
                record(&mut journal, &mut events, "step/error",
                       format!("хост не подтвердил событие: {error}"))?;
                status = "unrecorded";
                record(&mut journal, &mut events, "run/end",
                       "нет подтверждения хоста: свидетельство неполное".to_string())?;
                break;
            }
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
        std::fs::create_dir_all(dir.join("work")).unwrap();
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








