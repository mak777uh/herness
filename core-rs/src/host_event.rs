//! W07B: refs-only проекция локального event stream для хостового журнала.
//!
//! Сырой detail не покидает комнату. Его целостность подтверждает доменно-разделённый SHA-256,
//! а хост получает только тип, статус, безопасные refs и call/session identifiers.

use serde_json::{json, Value};
use sha2::Digest;

pub const EVENT_DOMAIN: &[u8] = b"HOST-JOURNAL-EVENT-V1\0";
pub const MAX_BODY_BYTES: usize = 16 * 1024;

#[derive(Debug, Default)]
pub struct ProjectionState {
    call_seq: u64,
    pending: Option<String>,
    pending_tool: Option<String>,
}

pub fn valid_session(session: &str) -> bool {
    if session.len() != 36 {
        return false;
    }
    session.bytes().enumerate().all(|(index, byte)| {
        if matches!(index, 8 | 13 | 18 | 23) {
            byte == b'-'
        } else {
            byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()
        }
    })
}

fn valid_tool(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 64
        && name.bytes().enumerate().all(|(index, byte)| {
            byte.is_ascii_lowercase()
                || byte.is_ascii_digit()
                || (index > 0 && matches!(byte, b'.' | b'_' | b'-'))
        })
}

fn word_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}

fn claim_ref(detail: &str) -> Option<String> {
    let bytes = detail.as_bytes();
    if bytes.len() < 6 {
        return None;
    }
    for index in 0..=bytes.len() - 6 {
        if &bytes[index..index + 2] != b"C-"
            || !bytes[index + 2..index + 6]
                .iter()
                .all(|byte| byte.is_ascii_digit())
        {
            continue;
        }
        let before = index == 0 || !word_byte(bytes[index - 1]);
        let after = index + 6 == bytes.len() || !word_byte(bytes[index + 6]);
        if before && after {
            return Some(format!(
                "c-{}",
                std::str::from_utf8(&bytes[index + 2..index + 6]).ok()?
            ));
        }
    }
    None
}

fn exact_grant_refusal(detail: &str, tool: &str) -> bool {
    detail == format!("err S6_CLOSURE_BREACH: инструмент {tool} не выдан в этом прогоне")
}

fn result_status(detail: &str, pending_tool: &str) -> &'static str {
    let head = detail.split(' ').next().unwrap_or_default().to_lowercase();
    if head == "ok" {
        "ok"
    } else if exact_grant_refusal(detail, pending_tool) {
        "denied"
    } else if matches!(head.as_str(), "err" | "error" | "ошибка" | "failed") {
        "error"
    } else {
        "recorded"
    }
}

fn known_type(kind: &str) -> bool {
    matches!(
        kind,
        "run/start"
            | "run/end"
            | "run/blocked"
            | "run/no-work"
            | "step/error"
            | "model/reply"
            | "tool/call"
            | "tool/result"
            | "claim/anchored"
            | "claim/unverified"
            | "step"
    )
}

/// Одно событие. Состояние вызовов передаётся по всему потоку, включая продолжение прогона.
pub fn project_event(
    kind: &str,
    detail: &str,
    session: &str,
    state: &mut ProjectionState,
) -> Result<Value, String> {
    if !valid_session(session) {
        return Err("host session не является canonical UUID".to_string());
    }
    if !known_type(kind) {
        return Err("неизвестный тип события для host projection".to_string());
    }
    let line = format!("{kind} {detail}");
    let mut hasher = sha2::Sha256::new();
    hasher.update(EVENT_DOMAIN);
    hasher.update(line.as_bytes());
    let digest = hex::encode(hasher.finalize());

    let mut call_id = None;
    let mut result_tool: Option<String> = None;
    let mut refs = Vec::new();
    if kind == "tool/call" {
        if state.pending.is_some() {
            return Err("tool/call без result предшествующего вызова".to_string());
        }
        state.call_seq += 1;
        let identifier = format!("call-{:06}", state.call_seq);
        let tool = detail.split(' ').next().unwrap_or_default();
        if !valid_tool(tool) {
            return Err("имя инструмента не безопасно для host ref".to_string());
        }
        refs.push(json!({"id": tool, "kind": "tool"}));
        state.pending = Some(identifier.clone());
        state.pending_tool = Some(tool.to_string());
        call_id = Some(Value::String(identifier));
    } else if kind == "tool/result" {
        let identifier = state
            .pending
            .clone()
            .ok_or_else(|| "tool/result без предшествующего tool/call".to_string())?;
        let pending_tool = state.pending_tool.clone().unwrap_or_default();
        result_tool = Some(pending_tool.clone());
        refs.push(json!({"id": identifier, "kind": "call"}));
        call_id = Some(Value::String(identifier));
        state.pending = None;
        state.pending_tool = None;
    } else if kind == "claim/anchored" {
        if let Some(identifier) = claim_ref(detail) {
            refs.push(json!({"id": identifier, "kind": "claim"}));
        }
    }

    let status = match kind {
        "run/start" => "started",
        "run/end" => "ended",
        "run/blocked" => "blocked",
        "run/no-work" => "no-work",
        "step/error" => "error",
        "model/reply" => "replied",
        "tool/result" => result_status(detail, result_tool.as_deref().unwrap_or_default()),
        _ => "recorded",
    };
    Ok(json!({
        "schema": "host-journal-event-v1",
        "session": session,
        "type": kind,
        "call_id": call_id,
        "status": status,
        "refs": refs,
        "digests": {"event": digest},
    }))
}

pub fn project_events<'a>(
    session: &str,
    events: impl IntoIterator<Item = (&'a str, &'a str)>,
) -> Result<Vec<Value>, String> {
    let mut state = ProjectionState::default();
    let projected = events
        .into_iter()
        .map(|(kind, detail)| project_event(kind, detail, session, &mut state))
        .collect::<Result<Vec<_>, _>>()?;
    if state.pending.is_some() {
        return Err("tool/call без tool/result к концу проекции".to_string());
    }
    Ok(projected)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn w03_host_projection_rejects_nested_calls() {
        let result = project_events(
            "11111111-1111-4111-8111-111111111111",
            [
                ("tool/call", "read a"),
                ("tool/call", "read b"),
            ],
        );
        let error = result.expect_err("nested calls не должны перезаписывать pending");
        assert!(error.contains("tool/call"), "{error}");
    }

    #[test]
    fn host_event_vector() {
        let vector: Value = serde_json::from_str(include_str!(
            "../../tests/vectors/host-journal-event-v1.json"
        ))
        .unwrap();
        let session = vector["session"].as_str().unwrap();
        let local: Vec<(&str, &str)> = vector["events"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| {
                let line = row["local"].as_str().unwrap();
                let (kind, detail) = line.split_once(' ').unwrap();
                (kind, detail)
            })
            .collect();
        let actual = project_events(session, local).unwrap();
        let expected: Vec<Value> = vector["events"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| row["expected"].clone())
            .collect();
        assert_eq!(actual, expected);
        for event in &actual {
            assert!(!crate::canonical_json(event).contains("CANARY-W07B-RAW-SECRET"));
        }
    }

    #[test]
    fn host_event_review_vector() {
        let vector: Value = serde_json::from_str(include_str!(
            "../../tests/vectors/host-journal-event-review-v1.json"
        ))
        .unwrap();
        let session = vector["session"].as_str().unwrap();
        let local: Vec<(&str, &str)> = vector["events"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| {
                let line = row["local"].as_str().unwrap();
                let (kind, detail) = line.split_once(' ').unwrap();
                (kind, detail)
            })
            .collect();
        let actual = project_events(session, local).unwrap();
        let expected: Vec<Value> = vector["events"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| row["expected"].clone())
            .collect();
        assert_eq!(actual, expected);
    }
}
