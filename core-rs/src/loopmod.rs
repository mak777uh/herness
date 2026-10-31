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
pub const MAX_STEPS: usize = 8;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Step {
    Tool { name: String, arg: String },
    Done { text: String },
}

pub trait Provider {
    fn next_step(&mut self) -> Option<Step>;
}

/// Провайдер-сценарий: последовательность шагов, заданная заранее.
pub struct Scripted {
    steps: Vec<Step>,
    index: usize,
}

impl Scripted {
    pub fn new(steps: Vec<Step>) -> Self {
        Scripted { steps, index: 0 }
    }

    /// Стандартный сценарий прогона: запечатать методологию, затем закончить.
    pub fn seal_method(method: &str) -> Self {
        Scripted::new(vec![
            Step::Tool { name: "seal".to_string(), arg: method.to_string() },
            Step::Done { text: "методология запечатана".to_string() },
        ])
    }
}

impl Provider for Scripted {
    fn next_step(&mut self) -> Option<Step> {
        let step = self.steps.get(self.index).cloned();
        self.index += 1;
        step
    }
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
fn tool_seal(arg: &str) -> Result<String, String> {
    let exe = std::env::current_exe().map_err(|error| format!("нет своего пути: {error}"))?;
    let output = Command::new(exe)
        .arg("seal")
        .arg(arg)
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
    provider: &mut dyn Provider,
) -> std::io::Result<Outcome> {
    let mut journal = Journal::open(journal_path)?;
    let mut events: Vec<Event> = Vec::new();
    let mut steps = 0usize;
    let mut calls = 0usize;
    let mut status: &'static str = "no-done";

    record(
        &mut journal,
        &mut events,
        "run/start",
        format!("task: запечатать {}", method_path.display()),
    )?;

    while steps < MAX_STEPS {
        let Some(step) = provider.next_step() else { break };
        match step {
            Step::Tool { name, arg } => {
                steps += 1;
                record(&mut journal, &mut events, "tool/call", format!("{name} {arg}"))?;
                let result = match name.as_str() {
                    "seal" => tool_seal(&arg),
                    other => Err(format!("неизвестный инструмент: {other}")),
                };
                calls += 1;
                match result {
                    Ok(text) => {
                        record(&mut journal, &mut events, "tool/result", format!("ok {text}"))?
                    }
                    Err(error) => {
                        record(&mut journal, &mut events, "tool/result", format!("err {error}"))?
                    }
                }
                record(&mut journal, &mut events, "step", format!("{steps} ok"))?;
            }
            Step::Done { text } => {
                status = "done";
                record(&mut journal, &mut events, "run/end", text)?;
                break;
            }
        }
    }

    if status != "done" {
        record(
            &mut journal,
            &mut events,
            "run/end",
            "шаги кончились без сигнала завершения".to_string(),
        )?;
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
        let text = String::from_utf8_lossy(&entry.payload);
        let mut parts = text.splitn(2, ' ');
        let raw = parts.next().unwrap_or_default();
        let detail = parts.next().unwrap_or_default().to_string();
        let kind: &'static str = match raw {
            "run/start" => "run/start",
            "tool/call" => "tool/call",
            "tool/result" => "tool/result",
            "step" => "step",
            "run/end" => "run/end",
            other => {
                problems.push(format!("неизвестное событие в журнале: {other}"));
                "?"
            }
        };
        events.push(Event { kind, detail });
    }

    problems.extend(verify_order(&events));
    if !ends_with_commit {
        problems.push("журнал не заканчивается маркером коммита".to_string());
    }
    Ok(problems)
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
    fn прогон_пишет_журнал_и_соблюдает_порядок() {
        let dir = std::env::temp_dir().join(format!("hs-loop-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let journal = dir.join("journal.bin");
        let method = dir.join("method.md");
        std::fs::write(&method, "тело методологии\n").unwrap();

        let mut provider = Scripted::seal_method(method.to_str().unwrap());
        let outcome = run(&journal, &method, &mut provider).unwrap();
        assert_eq!(outcome.status, "done");
        assert_eq!(outcome.steps, 1);
        assert_eq!(outcome.calls, 1);
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        // 5 событий: start, call, result, step, end; плюс маркер коммита.
        assert_eq!(outcome.events, 5);
        assert_eq!(outcome.records, 6);
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

        let mut provider = Scripted::new(vec![Step::Tool {
            name: "seal".to_string(),
            arg: method.to_str().unwrap().to_string(),
        }]);
        let outcome = run(&journal, &method, &mut provider).unwrap();
        assert_eq!(outcome.status, "no-done");
        assert!(outcome.order_ok(), "{:?}", outcome.problems);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn порядок_читается_из_файла_после_прогона() {
        let dir = std::env::temp_dir().join(format!("hs-loop-file-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let journal = dir.join("journal.bin");
        let method = dir.join("method.md");
        std::fs::write(&method, "тело\n").unwrap();

        let mut provider = Scripted::seal_method(method.to_str().unwrap());
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

        let mut provider = Scripted::seal_method(method.to_str().unwrap());
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
