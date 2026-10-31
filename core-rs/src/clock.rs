//! Время: на Linux — монотонные секунды с загрузки ядра, на хосте — секунды с запуска процесса.
//! Нужно, чтобы один и тот же код собирался и проверялся и в нашей системе, и на Windows.

use std::sync::OnceLock;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

static START: OnceLock<Instant> = OnceLock::new();

/// Секунды с запуска: на Linux — с загрузки ядра (CLOCK_MONOTONIC), иначе — с первого вызова.
pub fn uptime_seconds() -> f64 {
    #[cfg(unix)]
    {
        // SAFETY: clock_gettime с CLOCK_MONOTONIC валиден всегда.
        unsafe {
            let mut now: libc::timespec = std::mem::zeroed();
            if libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut now) == 0 {
                return now.tv_sec as f64 + now.tv_nsec as f64 / 1_000_000_000.0;
            }
        }
    }
    let start = START.get_or_init(Instant::now);
    start.elapsed().as_secs_f64()
}

/// Время стены — для датировки записей.
pub fn wall_seconds() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|delta| delta.as_secs_f64())
        .unwrap_or(0.0)
}
