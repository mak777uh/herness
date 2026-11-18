//! Harness процесса для HEAD-SLICE-R1: один и тот же бинарь работает на хосте
//! и как init в QEMU-госте.
//!
//! Job связывает точные байты (checks), admission, fixture manifest, root и кейсы.
//! Промоутер передаёт job через унаследованный fd запечатанного memfd; в гостевом
//! режиме path остаётся `/job.json`. Каждый результат печатается одной JSON-строкой
//! с маркером `HEAD-SLICE-R1`.
//! В гостевом режиме после job бинарь выключает машину (`reboot(RB_POWER_OFF)`);
//! сеть/диск/host mounts не нужны и не запрашиваются.

use std::collections::BTreeMap;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

use serde_json::{json, Value};

use hs_core::admission::{self, VerifiedAdmission};
use hs_core::head::{self, HeadRequest, PathRef};

const MARKER: &str = "HEAD-SLICE-R1";

fn emit(value: Value) {
    let mut stdout = std::io::stdout().lock();
    let _ = writeln!(stdout, "{MARKER} {}", value);
    let _ = stdout.flush();
}

fn code_of(error: &str) -> String {
    error
        .split_once(':')
        .map(|(code, _)| code.to_string())
        .unwrap_or_else(|| "UNKNOWN".to_string())
}

fn field<'a>(value: &'a Value, key: &str) -> Result<&'a Value, String> {
    value
        .get(key)
        .ok_or_else(|| format!("job: нет поля {key}"))
}

fn read_bytes(path: &Path) -> Result<Vec<u8>, String> {
    let mut file = std::fs::File::open(path)
        .map_err(|error| format!("job: не открыть {}: {error}", path.display()))?;
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes)
        .map_err(|error| format!("job: не прочитать {}: {error}", path.display()))?;
    Ok(bytes)
}

fn read_job(job_fd: Option<i32>, path: &Path) -> Result<String, String> {
    if let Some(fd) = job_fd {
        #[cfg(unix)]
        {
            use std::os::fd::FromRawFd;
            // fd унаследован от promoter: memfd уже запечатан, путь не нужен.
            let mut file = unsafe { std::fs::File::from_raw_fd(fd) };
            // os.write в promoter оставил offset в конце; читаем с начала.
            file.seek(SeekFrom::Start(0))
                .map_err(|error| format!("job fd {fd}: seek: {error}"))?;
            let mut text = String::new();
            file.read_to_string(&mut text)
                .map_err(|error| format!("job fd {fd}: {error}"))?;
            return Ok(text);
        }
        #[cfg(not(unix))]
        {
            let _ = fd;
            return Err("job fd не поддержан на этой платформе".to_string());
        }
    }
    std::fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))
}

fn verify_admission_case(
    case: &Value,
    top: &Value,
    now_unix: i64,
) -> Result<Option<VerifiedAdmission>, String> {
    let admission_value = match case.get("admission") {
        Some(Value::Null) => return Ok(None),
        Some(value) => value,
        None => field(top, "admission")?,
    };
    if admission_value.is_null() {
        return Ok(None);
    }
    let manifest_path = PathBuf::from(
        field(admission_value, "manifest")?
            .as_str()
            .ok_or_else(|| "job: admission.manifest не строка".to_string())?,
    );
    let sig_path = PathBuf::from(
        field(admission_value, "sig")?
            .as_str()
            .ok_or_else(|| "job: admission.sig не строка".to_string())?,
    );
    let anchor_path = PathBuf::from(
        field(admission_value, "anchor")?
            .as_str()
            .ok_or_else(|| "job: admission.anchor не строка".to_string())?,
    );
    let signature = std::fs::read_to_string(&sig_path)
        .map_err(|error| format!("K11_ADMISSION_REQUIRED: не прочитать sig: {error}"))?;
    let verified = admission::verify_admission(
        &read_bytes(&manifest_path)?,
        &signature,
        &read_bytes(&anchor_path)?,
        now_unix,
        true,
    )?;
    Ok(Some(verified))
}

fn verify_checks(
    top: &Value,
    case: &Value,
    verified: &VerifiedAdmission,
) -> Result<(), String> {
    let checks_value = case.get("checks").unwrap_or(field(top, "checks")?);
    let checks = checks_value
        .as_object()
        .ok_or_else(|| "job: checks не объект".to_string())?;
    for field_name in admission::DIGEST_FIELDS {
        let path = checks
            .get(field_name)
            .and_then(Value::as_str)
            .ok_or_else(|| {
                format!("K11_ADMISSION_REQUIRED: в checks нет {field_name}")
            })?;
        let expected = verified
            .digests
            .get(field_name)
            .ok_or_else(|| format!("K11_ADMISSION_REQUIRED: в admission нет {field_name}"))?;
        admission::verify_file_digest(expected, Path::new(path))?;
    }
    Ok(())
}

fn run_case(
    case: &Value,
    top: &Value,
    now_unix: i64,
    root: &Path,
) -> Value {
    let id = case
        .get("id")
        .and_then(Value::as_str)
        .unwrap_or("<без id>")
        .to_string();
    let verified = match verify_admission_case(case, top, now_unix) {
        Ok(value) => value,
        Err(error) => {
            return json!({
                "id": id,
                "outcome": "refusal",
                "code": code_of(&error),
                "error": error,
            });
        }
    };
    if let Some(verified) = verified.as_ref() {
        if let Err(error) = verify_checks(top, case, verified) {
            return json!({
                "id": id,
                "outcome": "refusal",
                "code": code_of(&error),
                "error": error,
            });
        }
    }

    let manifest_path = match case.get("fixture_manifest").and_then(Value::as_str) {
        Some(path) => PathBuf::from(path),
        None => match top.get("fixture_manifest").and_then(Value::as_str) {
            Some(path) => PathBuf::from(path),
            None => {
                return json!({
                    "id": id,
                    "outcome": "refusal",
                    "code": "S1_SCHEMA",
                    "error": "job: нет fixture_manifest",
                });
            }
        },
    };
    let manifest_bytes = match read_bytes(&manifest_path) {
        Ok(bytes) => bytes,
        Err(error) => {
            return json!({
                "id": id,
                "outcome": "refusal",
                "code": "S1_SCHEMA",
                "error": error,
            });
        }
    };
    let path_ref = match case.get("path_ref").and_then(Value::as_object) {
        Some(object) => object,
        None => {
            return json!({
                "id": id,
                "outcome": "refusal",
                "code": "S1_SCHEMA",
                "error": "job: нет path_ref",
            });
        }
    };
    let root_ref = path_ref
        .get("root_ref")
        .and_then(Value::as_str)
        .unwrap_or("");
    let segments: Vec<String> = match path_ref.get("segments").and_then(Value::as_array) {
        Some(values) => values
            .iter()
            .map(|item| item.as_str().unwrap_or("").to_string())
            .collect(),
        None => {
            return json!({
                "id": id,
                "outcome": "refusal",
                "code": "S1_SCHEMA",
                "error": "job: нет segments",
            });
        }
    };
    let line_count = case
        .get("line_count")
        .and_then(Value::as_u64)
        .unwrap_or(u64::MAX) as usize;
    let max_bytes_read = case
        .get("max_bytes_read")
        .and_then(Value::as_u64)
        .unwrap_or(u64::MAX) as usize;
    let request = HeadRequest {
        path_ref: PathRef {
            root_ref: root_ref.to_string(),
            segments,
        },
        line_count,
        max_bytes_read,
    };
    match head::file_read_stream(
        root,
        &manifest_bytes,
        &request,
        verified.as_ref(),
    ) {
        Ok(output) => json!({
            "id": id,
            "outcome": "ok",
            "code": "",
            "lines": output.lines,
            "bytes_read": output.bytes_read,
            "bytes_received": output.bytes_received,
            "truncated": output.truncated,
            "stop_reason": output.stop_reason.as_str(),
        }),
        Err(error) => json!({
            "id": id,
            "outcome": "refusal",
            "code": code_of(&error),
            "error": error,
        }),
    }
}

fn guest_poweroff() -> ! {
    unsafe {
        libc::sync();
        // isa-debug-exit есть в команде QEMU; он завершает машину детерминированно.
        #[cfg(target_arch = "x86_64")]
        {
            if libc::iopl(3) == 0 {
                std::arch::asm!(
                    "out dx, eax",
                    in("dx") 0xf4u16,
                    in("eax") 0x10u32,
                    options(nomem, nostack, preserves_flags)
                );
                std::process::exit(3);
            }
        }
        let _ = libc::reboot(libc::RB_POWER_OFF);
    }
    std::process::exit(0);
}

fn main() {
    let mut job_path = PathBuf::from("/job.json");
    let mut job_fd: Option<i32> = None;
    let mut guest = false;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        match argument.as_str() {
            "--guest" => guest = true,
            "--job" => {
                if let Some(value) = args.next() {
                    job_path = PathBuf::from(value);
                }
            }
            "--job-fd" => {
                let parsed = args.next().and_then(|value| value.parse::<i32>().ok());
                match parsed {
                    Some(fd) if fd >= 0 => job_fd = Some(fd),
                    _ => {
                        emit(json!({
                            "id": "__setup__",
                            "outcome": "error",
                            "code": "JOB_FD",
                            "error": "job fd: ожидалось неотрицательное целое",
                        }));
                        if guest {
                            guest_poweroff();
                        }
                        std::process::exit(2);
                    }
                }
            }
            other => {
                eprintln!("неизвестный аргумент {other}");
                std::process::exit(2);
            }
        }
    }

    let job_text = match read_job(job_fd, &job_path) {
        Ok(text) => text,
        Err(error) => {
            emit(json!({
                "id": "__setup__",
                "outcome": "error",
                "code": "JOB_READ",
                "error": error,
            }));
            if guest {
                guest_poweroff();
            }
            std::process::exit(1);
        }
    };
    let job: Value = match serde_json::from_str(&job_text) {
        Ok(value) => value,
        Err(error) => {
            emit(json!({
                "id": "__setup__",
                "outcome": "error",
                "code": "JOB_JSON",
                "error": error.to_string(),
            }));
            if guest {
                guest_poweroff();
            }
            std::process::exit(1);
        }
    };

    let root = PathBuf::from(match job.get("root").and_then(Value::as_str) {
        Some(value) => value,
        None => {
            emit(json!({
                "id": "__setup__",
                "outcome": "error",
                "code": "JOB_ROOT",
                "error": "job: нет строкового root",
            }));
            if guest {
                guest_poweroff();
            }
            std::process::exit(1);
        }
    });
    let now_unix = match job.get("now_unix").and_then(Value::as_i64) {
        Some(value) => value,
        None => {
            emit(json!({
                "id": "__setup__",
                "outcome": "error",
                "code": "JOB_NOW",
                "error": "job: нет целого now_unix",
            }));
            if guest {
                guest_poweroff();
            }
            std::process::exit(1);
        }
    };
    let cases = match job.get("cases").and_then(Value::as_array) {
        Some(value) => value.clone(),
        None => {
            emit(json!({
                "id": "__setup__",
                "outcome": "error",
                "code": "JOB_CASES",
                "error": "job: нет массива cases",
            }));
            if guest {
                guest_poweroff();
            }
            std::process::exit(1);
        }
    };

    // Setup проверяется на первом кейсе: если admission битый, каждый кейс
    // получит K11; это видно в выводе и не маскируется.
    let mut seen: BTreeMap<String, usize> = BTreeMap::new();
    for case in &cases {
        let result = run_case(case, &job, now_unix, &root);
        let id = result
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or("<без id>")
            .to_string();
        *seen.entry(id).or_insert(0) += 1;
        emit(result);
    }
    emit(json!({
        "id": "__summary__",
        "outcome": "ok",
        "cases": cases.len(),
        "unique_ids": seen.len(),
        "duplicates": seen.iter().filter(|(_, count)| **count > 1).map(|(id, _)| id.clone()).collect::<Vec<_>>(),
    }));

    if guest {
        // Дать serial-буферу уйти до выключения.
        std::thread::sleep(std::time::Duration::from_millis(200));
        guest_poweroff();
    }
}
