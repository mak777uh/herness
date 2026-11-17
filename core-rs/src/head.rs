//! `file_read_stream` — первый read-only срез `head` (HEAD-SLICE-R1).
//!
//! Граница держится на `openat2(root_fd, relative, O_RDONLY|O_CLOEXEC,
//! RESOLVE_BENEATH|RESOLVE_NO_SYMLINKS|RESOLVE_NO_MAGICLINKS|RESOLVE_NO_XDEV)`.
//! После open — `fstat`; не regular file отвергается. Потоковый цикл читает не больше
//! `max_bytes_read`, строка выдаётся только целиком, `bytes_read` считается по выданным
//! строкам, `bytes_received` остаётся диагностикой. `truncated=false` только при
//! доказанном EOF (`read()==0`). Это Linux-инструмент: без `openat2` запуск отказывает,
//! fallback на канонизацию запрещён.
//!
//! Admission проверяется снаружи (подпись/срок), но этот модуль требует
//! `VerifiedAdmission` с tool=head и digest'ом fixture-манифеста. Полная семантика
//! карточки и точные байты card/source/binary/policy/room — на promoter; см.
//! `docs/DECISIONS-R8-2026-11-17.md` (Q11/A01).

use std::collections::BTreeMap;
use std::fmt;
use std::io::Read;
use std::path::Path;

use serde_json::Value;

use crate::admission::{digest_bytes, VerifiedAdmission};

pub const CHUNK: usize = 4096;
pub const OUTPUT_BYTES: usize = 8192;
pub const MIN_LINES: usize = 1;
pub const MAX_LINES: usize = 200;
pub const MIN_MAX_BYTES: usize = 1;
pub const MAX_MAX_BYTES: usize = 65536;
pub const TOOL: &str = "head";

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

impl fmt::Display for StopReason {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HeadOutput {
    pub lines: Vec<String>,
    pub bytes_read: usize,
    /// Диагностика для evidence; в вывод инструмента не входит.
    pub bytes_received: usize,
    pub truncated: bool,
    pub stop_reason: StopReason,
}

impl HeadOutput {
    pub fn outcome(&self) -> &'static str {
        "ok"
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PathRef {
    pub root_ref: String,
    pub segments: Vec<String>,
}

impl PathRef {
    pub fn new(root_ref: &str, segments: &[&str]) -> Self {
        Self {
            root_ref: root_ref.to_string(),
            segments: segments.iter().map(|item| item.to_string()).collect(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HeadRequest {
    pub path_ref: PathRef,
    pub line_count: usize,
    pub max_bytes_read: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FixtureFile {
    pub bytes: u64,
    pub lines: u64,
    pub sha256: String,
    pub data_class: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FixtureManifest {
    pub root_ref: String,
    pub fixture_root: String,
    pub accepted_classes: Vec<String>,
    pub files: BTreeMap<String, FixtureFile>,
}

fn schema_error(reason: impl AsRef<str>) -> String {
    format!("S1_SCHEMA: {}", reason.as_ref())
}

fn closure_error(reason: impl AsRef<str>) -> String {
    format!("S6_CLOSURE_BREACH: {}", reason.as_ref())
}

fn missing_error(reason: impl AsRef<str>) -> String {
    format!("S10_NOT_FOUND: {}", reason.as_ref())
}

fn regular_error(reason: impl AsRef<str>) -> String {
    format!("S11_NOT_REGULAR: {}", reason.as_ref())
}

fn encoding_error(reason: impl AsRef<str>) -> String {
    format!("S12_ENCODING: {}", reason.as_ref())
}

fn limit_error(reason: impl AsRef<str>) -> String {
    format!("K4_RESOURCE_LIMIT: {}", reason.as_ref())
}

fn admission_error(reason: impl AsRef<str>) -> String {
    format!("K11_ADMISSION_REQUIRED: {}", reason.as_ref())
}

fn class_error(reason: impl AsRef<str>) -> String {
    format!("K6_DATA_CLASS_UNKNOWN: {}", reason.as_ref())
}

fn safe_segment(segment: &str) -> bool {
    !segment.is_empty()
        && segment != "."
        && segment != ".."
        && !segment.contains('/')
        && !segment.contains('\\')
        && !segment.contains('\0')
}

fn safe_relative(path: &str) -> bool {
    !path.is_empty()
        && !path.starts_with('/')
        && !path.contains('\\')
        && !path.contains('\0')
        && path.split('/').all(safe_segment)
}

impl FixtureManifest {
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        let value: Value = serde_json::from_slice(bytes)
            .map_err(|error| schema_error(format!("fixture manifest не JSON: {error}")))?;
        let object = value
            .as_object()
            .ok_or_else(|| schema_error("fixture manifest должен быть объектом"))?;
        let schema = object
            .get("schema_version")
            .and_then(Value::as_str)
            .ok_or_else(|| schema_error("fixture manifest: нет schema_version"))?;
        if schema != "fixture-manifest-v1" {
            return Err(schema_error("fixture manifest: ожидалась fixture-manifest-v1"));
        }
        let root_ref = object
            .get("root_ref")
            .and_then(Value::as_str)
            .ok_or_else(|| schema_error("fixture manifest: нет root_ref"))?
            .to_string();
        let fixture_root = object
            .get("fixture_root")
            .and_then(Value::as_str)
            .ok_or_else(|| schema_error("fixture manifest: нет fixture_root"))?
            .to_string();
        if !safe_segment(&fixture_root) {
            return Err(schema_error("fixture manifest: fixture_root не сегмент"));
        }
        let accepted_classes = object
            .get("accepted_classes")
            .and_then(Value::as_array)
            .ok_or_else(|| schema_error("fixture manifest: нет accepted_classes"))?
            .iter()
            .map(|item| {
                item.as_str()
                    .map(|text| text.to_string())
                    .ok_or_else(|| schema_error("fixture manifest: класс не строка"))
            })
            .collect::<Result<Vec<_>, _>>()?;
        if !accepted_classes.iter().any(|item| item == "model_visible") {
            return Err(class_error("fixture manifest не принимает model_visible"));
        }
        let files = object
            .get("files")
            .and_then(Value::as_array)
            .ok_or_else(|| schema_error("fixture manifest: нет files"))?;
        let mut parsed = BTreeMap::new();
        for item in files {
            let file = item
                .as_object()
                .ok_or_else(|| schema_error("fixture manifest: файл не объект"))?;
            let path = file
                .get("path")
                .and_then(Value::as_str)
                .ok_or_else(|| schema_error("fixture manifest: у файла нет path"))?;
            if !safe_relative(path) {
                return Err(schema_error(format!("fixture manifest: небезопасный путь {path}")));
            }
            let bytes_count = file
                .get("bytes")
                .and_then(Value::as_u64)
                .ok_or_else(|| schema_error("fixture manifest: у файла нет bytes"))?;
            let line_count = file
                .get("lines")
                .and_then(Value::as_u64)
                .ok_or_else(|| schema_error("fixture manifest: у файла нет lines"))?;
            let sha256 = file
                .get("sha256")
                .and_then(Value::as_str)
                .ok_or_else(|| schema_error("fixture manifest: у файла нет sha256"))?
                .to_string();
            let data_class = file
                .get("data_class")
                .and_then(Value::as_str)
                .ok_or_else(|| schema_error("fixture manifest: у файла нет data_class"))?
                .to_string();
            if parsed
                .insert(
                    path.to_string(),
                    FixtureFile {
                        bytes: bytes_count,
                        lines: line_count,
                        sha256,
                        data_class,
                    },
                )
                .is_some()
            {
                return Err(schema_error(format!("fixture manifest: дубликат {path}")));
            }
        }
        Ok(Self {
            root_ref,
            fixture_root,
            accepted_classes,
            files: parsed,
        })
    }
}

/// Проверка допуска, которую runtime обязан сделать до любого открытия файла.
pub fn check_admission(
    admission: Option<&VerifiedAdmission>,
    fixture_manifest_digest: &str,
) -> Result<(), String> {
    let admission = admission.ok_or_else(|| admission_error("admission отсутствует"))?;
    if admission.tool != TOOL {
        return Err(admission_error(format!(
            "admission выдан для {}, а не для {TOOL}",
            admission.tool
        )));
    }
    let admitted = admission
        .digests
        .get("fixture_digest")
        .ok_or_else(|| admission_error("в admission нет fixture_digest"))?;
    if admitted != fixture_manifest_digest {
        return Err(admission_error("fixture manifest не совпадает с допущенными байтами"));
    }
    Ok(())
}

fn class_gate(manifest: &FixtureManifest, file: &FixtureFile) -> Result<(), String> {
    if file.data_class == "secret" {
        return Err("K6_SECRET_EGRESS: fixture помечен secret".to_string());
    }
    if file.data_class != "model_visible"
        || !manifest
            .accepted_classes
            .iter()
            .any(|item| item == "model_visible")
    {
        return Err(class_error(format!(
            "класс {} не допущен для head",
            file.data_class
        )));
    }
    Ok(())
}

fn request_relative(
    manifest: &FixtureManifest,
    request: &HeadRequest,
) -> Result<(String, Option<String>), String> {
    if request.path_ref.root_ref != manifest.root_ref {
        return Err(closure_error(format!(
            "root_ref {} не входит в комнату {}",
            request.path_ref.root_ref, manifest.root_ref
        )));
    }
    if request.path_ref.segments.is_empty() {
        return Err(closure_error("path_ref без сегментов"));
    }
    for segment in &request.path_ref.segments {
        if !safe_segment(segment) {
            return Err(closure_error(format!("небезопасный сегмент {segment:?}")));
        }
    }
    if request.path_ref.segments[0] != manifest.fixture_root {
        return Err(closure_error("путь вне fixture_root"));
    }
    let open_relative = request.path_ref.segments.join("/");
    let tail = &request.path_ref.segments[1..];
    let lookup = if tail.is_empty() {
        None
    } else {
        Some(tail.join("/"))
    };
    Ok((open_relative, lookup))
}

/// Проверка схемы и класса до открытия: порядок Q17 — K11 → S1 → S6 → K6.
fn validate_request<'a>(
    manifest: &'a FixtureManifest,
    request: &HeadRequest,
) -> Result<(String, Option<&'a FixtureFile>), String> {
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
    let (open_relative, lookup) = request_relative(manifest, request)?;
    let Some(lookup) = lookup else {
        return Ok((open_relative, None));
    };
    let file = manifest
        .files
        .get(&lookup)
        .ok_or_else(|| class_error(format!("файл {lookup} не помечен в fixture manifest")))?;
    class_gate(manifest, file)?;
    Ok((open_relative, Some(file)))
}

#[cfg(target_os = "linux")]
fn open_beneath(root: &Path, relative: &str) -> Result<std::fs::File, String> {
    use std::ffi::CString;
    use std::os::fd::{FromRawFd, OwnedFd};
    use std::os::unix::ffi::OsStrExt;

    if relative.is_empty() || relative.starts_with('/') || relative.contains('\0') {
        return Err(closure_error("путь для openat2 пуст или абсолютен"));
    }
    let c_root = CString::new(root.as_os_str().as_bytes())
        .map_err(|_| closure_error("NUL в корне"))?;
    let c_relative =
        CString::new(relative).map_err(|_| closure_error("NUL в пути"))?;
    let dir_fd = unsafe { libc::open(c_root.as_ptr(), libc::O_DIRECTORY | libc::O_CLOEXEC) };
    if dir_fd < 0 {
        return Err(closure_error(format!(
            "не открыть корень {}: {}",
            root.display(),
            std::io::Error::last_os_error()
        )));
    }
    let dir_fd = unsafe { OwnedFd::from_raw_fd(dir_fd) };
    let mut how = std::mem::MaybeUninit::<libc::open_how>::zeroed();
    unsafe {
        let ptr = how.as_mut_ptr();
        (*ptr).flags = (libc::O_RDONLY | libc::O_CLOEXEC) as u64;
        (*ptr).mode = 0;
        (*ptr).resolve = libc::RESOLVE_BENEATH
            | libc::RESOLVE_NO_SYMLINKS
            | libc::RESOLVE_NO_MAGICLINKS
            | libc::RESOLVE_NO_XDEV;
    }
    let how = unsafe { how.assume_init() };
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat2,
            std::os::fd::AsRawFd::as_raw_fd(&dir_fd),
            c_relative.as_ptr(),
            &how as *const libc::open_how,
            std::mem::size_of::<libc::open_how>(),
        )
    };
    if fd < 0 {
        let error = std::io::Error::last_os_error();
        return Err(match error.raw_os_error() {
            Some(libc::ENOENT) => missing_error(format!("нет объекта {relative}")),
            Some(libc::ELOOP) | Some(libc::EXDEV) | Some(libc::ENOTDIR) => {
                closure_error(format!("openat2 отказал {relative}: {error}"))
            }
            Some(libc::EACCES) | Some(libc::EPERM) => {
                closure_error(format!("openat2 отказал {relative}: {error}"))
            }
            Some(libc::ENOSYS) => {
                closure_error("openat2 недоступен; fallback запрещён")
            }
            _ => closure_error(format!("openat2 отказал {relative}: {error}")),
        });
    }
    Ok(unsafe { std::fs::File::from_raw_fd(fd as i32) })
}

#[cfg(not(target_os = "linux"))]
fn open_beneath(_root: &Path, _relative: &str) -> Result<std::fs::File, String> {
    Err("S13_TOOL_INACTIVE: file_read_stream требует Linux/openat2; fallback запрещён".to_string())
}

fn is_regular(file: &std::fs::File) -> Result<bool, String> {
    #[cfg(target_os = "linux")]
    {
        use std::os::fd::AsRawFd;
        let mut metadata = std::mem::MaybeUninit::<libc::stat>::zeroed();
        let result = unsafe { libc::fstat(file.as_raw_fd(), metadata.as_mut_ptr()) };
        if result != 0 {
            return Err(closure_error(format!(
                "fstat отказал: {}",
                std::io::Error::last_os_error()
            )));
        }
        let metadata = unsafe { metadata.assume_init() };
        Ok(metadata.st_mode & libc::S_IFMT == libc::S_IFREG)
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = file;
        Ok(false)
    }
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
    // CR не срезается: строки делятся только по \n (S02).
    lines.push(text.to_string());
    *bytes_read += line_bytes.len();
    Ok(())
}

/// Прочитать не больше `line_count` строк и не больше `max_bytes_read` из fixture.
///
/// `fixture_manifest_digest` — `sha256:` от точных байтов манифеста; он должен совпадать
/// с полем `fixture_digest` проверенного admission. `bytes_received` — диагностика.
pub fn file_read_stream(
    root: &Path,
    fixture_manifest_bytes: &[u8],
    request: &HeadRequest,
    admission: Option<&VerifiedAdmission>,
) -> Result<HeadOutput, String> {
    check_admission(admission, &digest_bytes(fixture_manifest_bytes))?;
    let manifest = FixtureManifest::parse(fixture_manifest_bytes)?;
    let (relative, file_meta) = validate_request(&manifest, request)?;
    let mut file = open_beneath(root, &relative)?;
    if !is_regular(&file)? {
        return Err(regular_error(format!("{relative} не regular file")));
    }
    if let Some(meta) = file_meta {
        #[cfg(target_os = "linux")]
        {
            use std::os::fd::AsRawFd;
            let mut stat = std::mem::MaybeUninit::<libc::stat>::zeroed();
            if unsafe { libc::fstat(file.as_raw_fd(), stat.as_mut_ptr()) } != 0 {
                return Err(closure_error("fstat после open отказал"));
            }
            let stat = unsafe { stat.assume_init() };
            if stat.st_size as u64 != meta.bytes {
                return Err(admission_error(
                    "размер fixture не совпадает с fixture manifest (exact bytes)",
                ));
            }
        }
        let _ = meta;
    }

    let mut lines: Vec<String> = Vec::new();
    let mut bytes_read = 0usize;
    let mut bytes_received = 0usize;
    let mut pending: Vec<u8> = Vec::new();
    let mut buffer = [0u8; CHUNK];
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
        let read = file
            .read(&mut buffer[..want])
            .map_err(|error| closure_error(format!("read отказал: {error}")))?;
        if read == 0 {
            eof = true;
            break;
        }
        bytes_received += read;
        pending.extend_from_slice(&buffer[..read]);
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
    Ok(HeadOutput {
        lines,
        bytes_read,
        bytes_received,
        truncated,
        stop_reason,
    })
}

#[cfg(all(test, target_os = "linux"))]
mod tests {
    use super::*;
    use crate::admission::VerifiedAdmission;
    use std::os::unix::fs::symlink;
    use std::path::PathBuf;

    fn temp_root(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "herness-head-{}-{name}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("fixtures")).unwrap();
        root
    }

    fn fixture_bytes() -> Vec<u8> {
        std::fs::read("../lab/fixtures/model_visible/head-slice.txt").unwrap()
    }

    fn manifest_value(files: &[(&str, u64, &str, &str)]) -> Value {
        serde_json::json!({
            "schema_version": "fixture-manifest-v1",
            "root_ref": "room:input",
            "fixture_root": "fixtures",
            "accepted_classes": ["model_visible"],
            "files": files.iter().map(|(path, bytes, sha, class)| serde_json::json!({
                "path": path,
                "bytes": bytes,
                "lines": 1,
                "sha256": sha,
                "data_class": class,
            })).collect::<Vec<_>>(),
        })
    }

    fn admission_for(manifest: &[u8]) -> VerifiedAdmission {
        let mut digests = BTreeMap::new();
        for field in crate::admission::DIGEST_FIELDS {
            digests.insert(field.to_string(), digest_bytes(manifest));
        }
        VerifiedAdmission {
            tool: "head".to_string(),
            epoch: 1,
            seq: 1,
            test_only: true,
            digests,
        }
    }

    fn request(segments: &[&str], line_count: usize, max_bytes_read: usize) -> HeadRequest {
        HeadRequest {
            path_ref: PathRef::new("room:input", segments),
            line_count,
            max_bytes_read,
        }
    }

    fn run(root: &Path, manifest: &[u8], segments: &[&str], line_count: usize, max: usize) -> Result<HeadOutput, String> {
        let admission = admission_for(manifest);
        file_read_stream(root, manifest, &request(segments, line_count, max), Some(&admission))
    }

    #[test]
    fn positive_control_returns_first_three_lines() {
        let root = temp_root("positive");
        let bytes = fixture_bytes();
        std::fs::write(root.join("fixtures/head-slice.txt"), &bytes).unwrap();
        let sha = digest_bytes(&bytes);
        let manifest = serde_json::to_vec(&manifest_value(&[("head-slice.txt", 471, &sha, "model_visible")])).unwrap();
        let output = run(&root, &manifest, &["fixtures", "head-slice.txt"], 3, 4096).unwrap();
        assert_eq!(output.outcome(), "ok");
        assert_eq!(output.lines.len(), 3);
        assert_eq!(output.bytes_read, 144);
        assert!(output.truncated);
        assert_eq!(output.stop_reason, StopReason::LineCap);
        assert!(output.bytes_received <= 4096);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn eof_proves_untruncated_and_preserves_cr() {
        let root = temp_root("eof");
        let bytes = b"a\r\nb\r\n";
        std::fs::write(root.join("fixtures/cr.txt"), bytes).unwrap();
        let manifest = serde_json::to_vec(&manifest_value(&[("cr.txt", 6, &digest_bytes(bytes), "model_visible")])).unwrap();
        let output = run(&root, &manifest, &["fixtures", "cr.txt"], 5, 4096).unwrap();
        assert_eq!(output.lines, vec!["a\r".to_string(), "b\r".to_string()]);
        assert_eq!(output.bytes_read, 6);
        assert!(!output.truncated);
        assert_eq!(output.stop_reason, StopReason::Eof);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn byte_cap_never_exceeds_limit() {
        let root = temp_root("bytecap");
        let bytes = fixture_bytes();
        std::fs::write(root.join("fixtures/head-slice.txt"), &bytes).unwrap();
        let manifest = serde_json::to_vec(&manifest_value(&[("head-slice.txt", 471, &digest_bytes(&bytes), "model_visible")])).unwrap();
        let output = run(&root, &manifest, &["fixtures", "head-slice.txt"], 200, 64).unwrap();
        assert_eq!(output.lines.len(), 1);
        assert_eq!(output.bytes_read, 41);
        assert!(output.truncated);
        assert_eq!(output.stop_reason, StopReason::ByteCap);
        assert!(output.bytes_received <= 64);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn cap_below_first_line_is_k4() {
        let root = temp_root("k4");
        let bytes = fixture_bytes();
        std::fs::write(root.join("fixtures/head-slice.txt"), &bytes).unwrap();
        let manifest = serde_json::to_vec(&manifest_value(&[("head-slice.txt", 471, &digest_bytes(&bytes), "model_visible")])).unwrap();
        let error = run(&root, &manifest, &["fixtures", "head-slice.txt"], 3, 32).unwrap_err();
        assert!(error.starts_with("K4_RESOURCE_LIMIT:"), "{error}");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn line_count_and_max_are_schema_checked_before_path() {
        let root = temp_root("schema");
        let manifest = serde_json::to_vec(&manifest_value(&[])).unwrap();
        let error = run(&root, &manifest, &["fixtures", "missing"], 0, 4096).unwrap_err();
        assert!(error.starts_with("S1_SCHEMA:"), "{error}");
        let error = run(&root, &manifest, &["fixtures", "missing"], 1, 0).unwrap_err();
        assert!(error.starts_with("S1_SCHEMA:"), "{error}");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn outside_root_and_dotdot_are_s6() {
        let root = temp_root("outside");
        let manifest = serde_json::to_vec(&manifest_value(&[("head-slice.txt", 1, &digest_bytes(b"x"), "model_visible")])).unwrap();
        let error = run(&root, &manifest, &["etc", "passwd"], 3, 4096).unwrap_err();
        assert!(error.starts_with("S6_CLOSURE_BREACH:"), "{error}");
        let error = run(&root, &manifest, &["fixtures", "..", "secret.txt"], 3, 4096).unwrap_err();
        assert!(error.starts_with("S6_CLOSURE_BREACH:"), "{error}");
        let error = run(&root, &manifest, &["fixtures", "head-slice.txt"], 3, 4096).unwrap_err();
        assert!(error.starts_with("S10_NOT_FOUND:"), "{error}");
        let error = run(&root, &manifest, &["fixtures", "unlisted.txt"], 3, 4096).unwrap_err();
        assert!(error.starts_with("K6_DATA_CLASS_UNKNOWN:"), "{error}");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn symlink_outside_and_inside_are_s6() {
        let root = temp_root("symlink");
        let bytes = fixture_bytes();
        std::fs::write(root.join("fixtures/head-slice.txt"), &bytes).unwrap();
        let outside = root.join("outside.txt");
        std::fs::write(&outside, b"canary").unwrap();
        symlink(&outside, root.join("fixtures/escape")).unwrap();
        symlink("head-slice.txt", root.join("fixtures/alias")).unwrap();
        let manifest = serde_json::to_vec(&manifest_value(&[
            ("head-slice.txt", 471, &digest_bytes(&bytes), "model_visible"),
            ("escape", 6, &digest_bytes(b"canary"), "model_visible"),
            ("alias", 471, &digest_bytes(&bytes), "model_visible"),
        ]))
        .unwrap();
        for name in ["escape", "alias"] {
            let error = run(&root, &manifest, &["fixtures", name], 3, 4096).unwrap_err();
            assert!(error.starts_with("S6_CLOSURE_BREACH:"), "{name}: {error}");
        }
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn missing_declared_file_is_s10_and_directory_is_s11() {
        let root = temp_root("objects");
        std::fs::create_dir_all(root.join("fixtures/dir")).unwrap();
        let manifest = serde_json::to_vec(&manifest_value(&[
            ("absent.txt", 1, &digest_bytes(b"x"), "model_visible"),
            ("dir", 0, &digest_bytes(b""), "model_visible"),
        ]))
        .unwrap();
        let error = run(&root, &manifest, &["fixtures", "absent.txt"], 3, 4096).unwrap_err();
        assert!(error.starts_with("S10_NOT_FOUND:"), "{error}");
        let error = run(&root, &manifest, &["fixtures", "dir"], 3, 4096).unwrap_err();
        assert!(error.starts_with("S11_NOT_REGULAR:"), "{error}");
        let error = run(&root, &manifest, &["fixtures"], 3, 4096).unwrap_err();
        assert!(error.starts_with("S11_NOT_REGULAR:"), "{error}");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn classes_are_fail_closed() {
        let root = temp_root("classes");
        for name in ["unknown.txt", "secret.txt"] {
            std::fs::write(root.join("fixtures").join(name), b"x\n").unwrap();
        }
        let manifest = serde_json::to_vec(&manifest_value(&[
            ("unknown.txt", 2, &digest_bytes(b"x\n"), "unknown"),
            ("secret.txt", 2, &digest_bytes(b"x\n"), "secret"),
        ]))
        .unwrap();
        let error = run(&root, &manifest, &["fixtures", "unknown.txt"], 3, 4096).unwrap_err();
        assert!(error.starts_with("K6_DATA_CLASS_UNKNOWN:"), "{error}");
        let error = run(&root, &manifest, &["fixtures", "secret.txt"], 3, 4096).unwrap_err();
        assert!(error.starts_with("K6_SECRET_EGRESS:"), "{error}");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn invalid_utf8_is_s12() {
        let root = temp_root("utf8");
        let bytes = b"\xff\n";
        std::fs::write(root.join("fixtures/bad.txt"), bytes).unwrap();
        let manifest = serde_json::to_vec(&manifest_value(&[("bad.txt", 2, &digest_bytes(bytes), "model_visible")])).unwrap();
        let error = run(&root, &manifest, &["fixtures", "bad.txt"], 3, 4096).unwrap_err();
        assert!(error.starts_with("S12_ENCODING:"), "{error}");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn missing_or_mismatched_admission_is_k11() {
        let root = temp_root("admission");
        let bytes = fixture_bytes();
        std::fs::write(root.join("fixtures/head-slice.txt"), &bytes).unwrap();
        let manifest = serde_json::to_vec(&manifest_value(&[("head-slice.txt", 471, &digest_bytes(&bytes), "model_visible")])).unwrap();
        let request = request(&["fixtures", "head-slice.txt"], 3, 4096);
        let error = file_read_stream(&root, &manifest, &request, None).unwrap_err();
        assert!(error.starts_with("K11_ADMISSION_REQUIRED:"), "{error}");
        let mut admission = admission_for(&manifest);
        admission.digests.insert("fixture_digest".into(), digest_bytes(b"other"));
        let error = file_read_stream(&root, &manifest, &request, Some(&admission)).unwrap_err();
        assert!(error.starts_with("K11_ADMISSION_REQUIRED:"), "{error}");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn output_cap_stops_without_exceeding_and_without_k4() {
        let root = temp_root("output");
        let mut bytes = Vec::new();
        for index in 0..200 {
            bytes.extend_from_slice(format!("line {index:03} 012345678901234567890123456789012345\n").as_bytes());
        }
        std::fs::write(root.join("fixtures/many.txt"), &bytes).unwrap();
        let manifest = serde_json::to_vec(&manifest_value(&[("many.txt", bytes.len() as u64, &digest_bytes(&bytes), "model_visible")])).unwrap();
        let output = run(&root, &manifest, &["fixtures", "many.txt"], 200, 65536).unwrap();
        assert!(output.bytes_read <= OUTPUT_BYTES);
        assert!(output.truncated);
        assert_eq!(output.stop_reason, StopReason::OutputCap);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn three_repeats_are_deterministic() {
        let root = temp_root("repeat");
        let bytes = fixture_bytes();
        std::fs::write(root.join("fixtures/head-slice.txt"), &bytes).unwrap();
        let manifest = serde_json::to_vec(&manifest_value(&[("head-slice.txt", 471, &digest_bytes(&bytes), "model_visible")])).unwrap();
        let first = run(&root, &manifest, &["fixtures", "head-slice.txt"], 3, 4096).unwrap();
        for _ in 0..2 {
            let again = run(&root, &manifest, &["fixtures", "head-slice.txt"], 3, 4096).unwrap();
            assert_eq!(first, again);
        }
        let _ = std::fs::remove_dir_all(root);
    }
}
