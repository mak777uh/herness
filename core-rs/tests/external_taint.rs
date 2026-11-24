//! Контракт границы внешних данных: ответ `/v1/net` приходит в комнату с меткой
//! `[external_untrusted]`.
//!
//! Проверяется публичный API `HttpBridge::net_request` на локальном фейковом мосте:
//! успех и типизированный отказ оба обязаны быть помечены. Это не проверка моста и
//! не доказательство, что модель слушается метки; это граница комнаты: без метки
//! внешний текст неотличим от содержимого комнаты.

use std::io::{Read, Write};
use std::net::TcpListener;
use std::thread;

use hs_core::model::HttpBridge;

const MARKER: &str = "[external_untrusted]";

fn canonical_response(body: &str) -> String {
    format!(
        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    )
}

/// Крошечный сервер: один запрос, один ответ. Сеть не нужна.
fn serve_once(response: String) -> (u16, thread::JoinHandle<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let handle = thread::spawn(move || {
        let (mut socket, _) = listener.accept().unwrap();
        let mut buffer = [0u8; 4096];
        let read = socket.read(&mut buffer).unwrap_or(0);
        let request = String::from_utf8_lossy(&buffer[..read]).to_string();
        let _ = socket.write_all(response.as_bytes());
        request
    });
    (port, handle)
}

#[test]
fn успешный_ответ_помечен_как_внешний() {
    let (port, handle) = serve_once(canonical_response(r#"{"output":"найдено 1"}"#));
    let mut link = HttpBridge::new("127.0.0.1", port, "local-tk", "net");
    link.path = "/v1/net".to_string();
    let text = link.net_request("search x").unwrap();
    assert!(text.starts_with(MARKER), "{text}");
    assert!(text.contains("найдено 1"), "{text}");
    let request = handle.join().unwrap();
    assert!(request.starts_with("POST /v1/net"), "{request}");
}

#[test]
fn отказ_сети_тоже_помечен_как_внешний() {
    let (port, handle) = serve_once(canonical_response(r#"{"error":"net","message":"boom"}"#));
    let mut link = HttpBridge::new("127.0.0.1", port, "local-tk", "net");
    link.path = "/v1/net".to_string();
    let error = link.net_request("open 9").unwrap_err();
    assert!(error.starts_with(MARKER), "{error}");
    assert!(error.contains("net: boom"), "{error}");
    handle.join().unwrap();
}
