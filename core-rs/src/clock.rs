//! lib.rs — общая часть плюс измерение времени до старта init.

use std::time::{SystemTime, UNIX_EPOCH};

/// Секунды с загрузки ядра (монотонные) — по ним сравниваем быстроту ядер.
pub fn uptime_seconds() -> f64 {
    // SAFETY: clock_gettime с CLOCK_MONOTONIC валиден всегда.
    unsafe {
        let mut now: libc::timespec = std::mem::zeroed();
        if libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut now) != 0 {
            return 0.0;
        }
        now.tv_sec as f64 + now.tv_nsec as f64 / 1_000_000_000.0
    }
}

/// Время стены — на случай, если понадобится датировать запись в журнале.
pub fn wall_seconds() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|delta| delta.as_secs_f64())
        .unwrap_or(0.0)
}
