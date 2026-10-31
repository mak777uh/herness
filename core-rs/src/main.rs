//! Минимальный CLI ядра: печать файла и проверка цепочки журнала.
//! Ничего не требует от дистрибутива — только ядро и статическая линковка.

use std::env;
use std::fs;
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = env::args().skip(1).collect();
    match args.first().map(String::as_str) {
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
            println!("событий: {}\\nprev: {last_prev}\\nhash: {last_hash}", events.len());
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("hs-core: seal <файл> | chain <events.jsonl>");
            ExitCode::from(2)
        }
    }
}
