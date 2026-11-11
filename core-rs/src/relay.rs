//! `tcp-relay`: stdin/stdout ↔ TCP. Режим для QEMU `guestfwd`.
//!
//! Зачем: `restrict=on` закрывает гостю выход наружу, а `guestfwd` умеет только «запусти
//! команду на хосте и соедини её stdio с гостевым TCP». На Windows нет `nc`/`socat`, поэтому
//! командой становится сам `hs-core`.
//!
//! Что этот режим НЕ делает: не проверяет, кто пришёл, не ограничивает объём, не умеет
//! нескольких соединений. Он обслуживает один канал к мосту и запускается только из `guestfwd`.

use std::io::{Read, Write};
use std::net::TcpStream;

/// Соединить stdio с TCP по адресу и перекачивать байты в обе стороны, пока одна не закроется.
pub fn run(address: &str) -> Result<(), String> {
    let stream = TcpStream::connect(address)
        .map_err(|error| format!("нет соединения с {address}: {error}"))?;
    let mut to_socket = stream
        .try_clone()
        .map_err(|error| format!("не раздвоить сокет: {error}"))?;
    let mut from_socket = stream;

    // Поток «сокет -> stdout»: без него ответ моста не дойдёт, пока гость не закроет ввод.
    let reader = std::thread::spawn(move || {
        let mut stdout = std::io::stdout();
        let mut buffer = [0u8; 8192];
        loop {
            match from_socket.read(&mut buffer) {
                Ok(0) => break,
                Ok(n) => {
                    if stdout.write_all(&buffer[..n]).is_err() {
                        break;
                    }
                    let _ = stdout.flush();
                }
                Err(_) => break,
            }
        }
    });

    let mut stdin = std::io::stdin();
    let mut buffer = [0u8; 8192];
    loop {
        match stdin.read(&mut buffer) {
            Ok(0) => break,
            Ok(n) => {
                if to_socket.write_all(&buffer[..n]).is_err() {
                    break;
                }
            }
            Err(_) => break,
        }
    }
    let _ = reader.join();
    Ok(())
}
