// Кандидат, сгенерированный herness new_tool.py (herness-new-tool-v1).
// Шаблон: file_read_stream@1. Это НЕ допущенный инструмент:
// admission отсутствует, registry.active его не содержит.
//
// Чистая функция над байтами: без файлов, сети, процессов и системного времени.
// S02: CHUNK=4096; CR сохраняется; строка выдаётся только целиком; EOF только
// при исчерпании входа; truncated=false только при доказанном EOF; output_cap —
// остановка, не отказ; max_bytes_read ограничивает принятые байты.

pub const CHUNK: usize = 4096;
pub const OUTPUT_BYTES: usize = 8192;
pub const MIN_LINES: usize = 1;
pub const MAX_LINES: usize = 200;
pub const MIN_MAX_BYTES: usize = 1;
pub const MAX_MAX_BYTES: usize = 65536;
pub const SPEC_ID: &str = "frs-a02";
pub const DEFAULT_LINE_COUNT: usize = 5;
pub const DEFAULT_MAX_BYTES_READ: usize = 4096;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Request {
    pub line_count: usize,
    pub max_bytes_read: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Outcome {
    pub lines: Vec<String>,
    pub bytes_read: usize,
    pub bytes_received: usize,
    pub truncated: bool,
    pub stop_reason: StopReason,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StopReason {
    Eof,
    LineCap,
    ByteCap,
    OutputCap,
}

impl StopReason {
    pub fn as_str(&self) -> &'static str {
        match self {
            StopReason::Eof => "eof",
            StopReason::LineCap => "line_cap",
            StopReason::ByteCap => "byte_cap",
            StopReason::OutputCap => "output_cap",
        }
    }
}

fn schema_error(reason: impl AsRef<str>) -> String {
    format!("S1_SCHEMA: {}", reason.as_ref())
}

fn encoding_error(reason: impl AsRef<str>) -> String {
    format!("S12_ENCODING: {}", reason.as_ref())
}

fn limit_error(reason: impl AsRef<str>) -> String {
    format!("K4_RESOURCE_LIMIT: {}", reason.as_ref())
}

fn check_schema(request: &Request) -> Result<(), String> {
    if !(MIN_LINES..=MAX_LINES).contains(&request.line_count) {
        return Err(schema_error(format!(
            "line_count={} вне [{MIN_LINES}, {MAX_LINES}]",
            request.line_count
        )));
    }
    if !(MIN_MAX_BYTES..=MAX_MAX_BYTES).contains(&request.max_bytes_read) {
        return Err(schema_error(format!(
            "max_bytes_read={} вне [{MIN_MAX_BYTES}, {MAX_MAX_BYTES}]",
            request.max_bytes_read
        )));
    }
    Ok(())
}

fn line_exceeds_output(bytes_read: usize, line: &[u8]) -> bool {
    bytes_read
        .checked_add(line.len())
        .is_none_or(|total| total > OUTPUT_BYTES)
}

fn emit_line(
    line_bytes: &[u8],
    lines: &mut Vec<String>,
    bytes_read: &mut usize,
) -> Result<(), String> {
    let content = line_bytes.strip_suffix(b"\n").unwrap_or(line_bytes);
    let text = std::str::from_utf8(content)
        .map_err(|error| encoding_error(format!("выданная строка не UTF-8: {error}")))?;
    lines.push(text.to_string());
    *bytes_read += line_bytes.len();
    Ok(())
}

pub fn stream(input: &[u8], request: &Request) -> Result<Outcome, String> {
    check_schema(request)?;

    let mut lines: Vec<String> = Vec::new();
    let mut bytes_read = 0usize;
    let mut bytes_received = 0usize;
    let mut pending: Vec<u8> = Vec::new();
    let mut index = 0usize;
    let mut stop_reason = StopReason::Eof;
    let mut eof = false;

    'outer: loop {
        if lines.len() >= request.line_count {
            stop_reason = StopReason::LineCap;
            break;
        }
        if bytes_received >= request.max_bytes_read {
            stop_reason = StopReason::ByteCap;
            break;
        }
        let want = CHUNK.min(request.max_bytes_read - bytes_received);
        let available = input.len() - index;
        let take = want.min(available);
        if take == 0 {
            eof = true;
            break;
        }
        bytes_received += take;
        pending.extend_from_slice(&input[index..index + take]);
        index += take;

        while let Some(position) = pending.iter().position(|byte| *byte == b'\n') {
            let line: Vec<u8> = pending.drain(..=position).collect();
            if line_exceeds_output(bytes_read, &line) {
                stop_reason = StopReason::OutputCap;
                break 'outer;
            }
            emit_line(&line, &mut lines, &mut bytes_read)?;
            if lines.len() >= request.line_count {
                stop_reason = StopReason::LineCap;
                break 'outer;
            }
        }

        if bytes_received >= request.max_bytes_read {
            if lines.is_empty() && !pending.is_empty() {
                return Err(limit_error(format!(
                    "max_bytes_read={} меньше первой строки",
                    request.max_bytes_read
                )));
            }
            stop_reason = StopReason::ByteCap;
            break;
        }
    }

    if eof && !pending.is_empty() && lines.len() < request.line_count {
        let line = std::mem::take(&mut pending);
        if line_exceeds_output(bytes_read, &line) {
            stop_reason = StopReason::OutputCap;
        } else {
            emit_line(&line, &mut lines, &mut bytes_read)?;
        }
    }

    let truncated = stop_reason != StopReason::Eof;
    Ok(Outcome {
        lines,
        bytes_read,
        bytes_received,
        truncated,
        stop_reason,
    })
}
