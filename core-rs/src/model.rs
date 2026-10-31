//! ModelLink — «как мы говорим с моделью», спрятанное за одним трейтом.
//!
//! Зачем трейт: развилка «B1 (TLS внутри комнаты) или B2 (мост на хосте)» должна быть выбором
//! реализации, а не переделкой цикла. Решение ADR-0046 — B2: мост на хосте держит ключ и
//! завершает TLS. Значит **комнате нужен только plain HTTP**, без rustls, без 1,24 МБ и без
//! C-тулчейна под musl. Этот модуль — вторая половина той экономии.
//!
//! Три исхода ответа, а не два: текст, «сценарий кончился» и ошибка. Смешивать последние два
//! нельзя — иначе «модель не ответила» станет неотличимо от «мы закончили».

use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

use serde_json::Value;

/// Формат ответа, который цикл умеет разбирать. Одна строка — одно решение.
pub const DEFAULT_SYSTEM: &str = "Ты — цикл харнесса в изолированной системе. Отвечай РОВНО одной строкой:\nTOOL <имя> <аргумент>   — выполнить инструмент\nDONE <итог>             — закончить\nИнструменты: list <каталог>; read <файл>; search <каталог> <подстрока>; seal <файл>; netprobe.\nНичего другого не пиши.";

/// Предел на ответ, чтобы плохой ответ не съел память.
pub const MAX_REPLY: usize = 64 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Reply {
    Text(String),
    End,
    Error(String),
    /// Ответ оборван лимитом токенов: это не «модель промолчала» и не ошибка формата.
    Truncated(String),
}

/// Сколько стоил запрос. Нужно бюджету цикла: «сколько шагов» — не единственный предел.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Usage {
    pub prompt_tokens: u64,
    pub completion_tokens: u64,
    /// Деньги, зачтённые в лимит подписки (поле allowance у провайдера).
    pub allowance: f64,
}

pub trait ModelLink {
    fn complete(&mut self, prompt: &str) -> Reply;

    /// Расход последнего запроса, если провайдер его сообщил. По умолчанию неизвестен.
    fn last_usage(&self) -> Option<Usage> {
        None
    }
}

/// Детерминированный провайдер: заранее заданные ответы. Нужен тестам и прогонам без сети.
pub struct Stub {
    replies: Vec<String>,
    index: usize,
}

impl Stub {
    pub fn new(replies: Vec<String>) -> Self {
        Stub { replies, index: 0 }
    }

    /// Сценарий: запечатать методологию, затем закончить.
    pub fn seal_method(method: &str) -> Self {
        Stub::new(vec![
            format!("TOOL seal {method}"),
            "DONE методология запечатана".to_string(),
        ])
    }

    /// Длинный сценарий: чтобы убийство ВМ попадало внутрь блока.
    pub fn seal_many(method: &str, steps: usize) -> Self {
        let mut replies: Vec<String> = (0..steps).map(|_| format!("TOOL seal {method}")).collect();
        replies.push("DONE готово".to_string());
        Stub::new(replies)
    }
}

impl ModelLink for Stub {
    fn complete(&mut self, _prompt: &str) -> Reply {
        match self.replies.get(self.index).cloned() {
            Some(text) => {
                self.index += 1;
                Reply::Text(text)
            }
            None => Reply::End,
        }
    }
}

/// Клиент к мосту: plain HTTP до `host:port`, никакого TLS — шифрование делает мост (ADR-0046).
///
/// Почему руками, а не через библиотеку: нужен ровно один запрос и один разбор; тянуть HTTP-стек
/// в комнату ради этого — та же ошибка, от которой мы ушли, отказавшись от TLS внутри.
pub struct HttpBridge {
    pub host: String,
    pub port: u16,
    pub token: String,
    pub model: String,
    pub path: String,
    pub timeout: Duration,
    /// Что сказать модели про формат ответа. Без этого она отвечает прозой, а цикл ждёт шаг.
    pub system: String,
    pub usage: Option<Usage>,
}

impl HttpBridge {
    pub fn new(host: &str, port: u16, token: &str, model: &str) -> Self {
        HttpBridge {
            host: host.to_string(),
            port,
            token: token.to_string(),
            model: model.to_string(),
            path: "/v1/chat/completions".to_string(),
            timeout: Duration::from_secs(180),
            system: DEFAULT_SYSTEM.to_string(),
            usage: None,
        }
    }

    fn body(&self, prompt: &str) -> String {
        let payload = serde_json::json!({
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 2000,
        });
        serde_json::to_string(&payload).unwrap_or_else(|_| "{}".to_string())
    }

    /// Один запрос к мосту. Ошибки типизированы текстом: что именно не так — видно в журнале.
    fn call(&mut self, prompt: &str) -> Result<String, String> {
        let body = self.body(prompt);
        let request = format!(
            "POST {} HTTP/1.1\r\nHost: {}:{}\r\nAuthorization: Bearer {}\r\n\
             Content-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            self.path,
            self.host,
            self.port,
            self.token,
            body.len(),
            body
        );

        let address = format!("{}:{}", self.host, self.port);
        let mut stream = TcpStream::connect(&address)
            .map_err(|error| format!("мост недоступен ({address}): {error}"))?;
        stream
            .set_read_timeout(Some(self.timeout))
            .map_err(|error| format!("таймаут не ставится: {error}"))?;
        stream
            .write_all(request.as_bytes())
            .map_err(|error| format!("запрос не отправлен: {error}"))?;

        let mut response = Vec::new();
        stream
            .read_to_end(&mut response)
            .map_err(|error| format!("ответ не прочитан: {error}"))?;
        if response.len() > MAX_REPLY * 16 {
            return Err(format!("ответ слишком большой: {} байт", response.len()));
        }
        let raw = String::from_utf8_lossy(&response).to_string();
        self.usage = parse_usage(&raw);
        parse_response(&raw)
    }
}

impl ModelLink for HttpBridge {
    fn last_usage(&self) -> Option<Usage> {
        self.usage
    }

    fn complete(&mut self, prompt: &str) -> Reply {
        match self.call(prompt) {
            Ok(text) => Reply::Text(text),
            Err(error) if error.starts_with("обрезано") => Reply::Truncated(error),
            Err(error) => Reply::Error(error),
        }
    }
}

/// Достать расход из тела ответа. Нет полей — расход неизвестен, а не ноль.
pub fn parse_usage(raw: &str) -> Option<Usage> {
    let (_, body) = raw.split_once("\r\n\r\n").or_else(|| raw.split_once("\n\n"))?;
    let value: Value = serde_json::from_str(body).ok()?;
    let usage = value.get("usage")?;
    let prompt_tokens = usage.get("prompt_tokens").and_then(|v| v.as_u64()).unwrap_or(0);
    let completion_tokens = usage
        .get("completion_tokens")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let allowance = usage
        .get("opencode")
        .and_then(|oc| oc.get("allowance"))
        .and_then(|v| v.as_f64())
        .or_else(|| usage.get("cost").and_then(|v| v.as_f64()))
        .unwrap_or(0.0);
    Some(Usage { prompt_tokens, completion_tokens, allowance })
}

/// Разобрать HTTP-ответ моста и достать текст ответа модели.
pub fn parse_response(raw: &str) -> Result<String, String> {
    let (head, body) = raw
        .split_once("\r\n\r\n")
        .or_else(|| raw.split_once("\n\n"))
        .ok_or_else(|| "ответ без заголовков".to_string())?;
    let status = head
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|code| code.parse::<u16>().ok())
        .ok_or_else(|| "нет кода ответа".to_string())?;
    if !(200..300).contains(&status) {
        let short: String = body.chars().take(200).collect();
        return Err(format!("мост вернул {status}: {short}"));
    }
    let value: Value = serde_json::from_str(body).map_err(|error| format!("не JSON: {error}"))?;

    // Порядок важен: сначала «оборвано ли», потом «есть ли текст». Рассуждающая модель может
    // истратить весь бюджет на reasoning и вернуть пустой content при finish_reason=length —
    // это обрезание, а не молчание (измерено: max_tokens=24 → length, content пуст, reasoning 24).
    let finish = value
        .get("choices")
        .and_then(|choices| choices.get(0))
        .and_then(|choice| choice.get("finish_reason"))
        .and_then(|reason| reason.as_str())
        .unwrap_or("");
    if finish == "length" {
        return Err("обрезано по лимиту токенов (finish_reason=length)".to_string());
    }

    value
        .get("choices")
        .and_then(|choices| choices.get(0))
        .and_then(|choice| choice.get("message"))
        .and_then(|message| message.get("content"))
        .and_then(|content| content.as_str())
        .map(|text| text.to_string())
        .ok_or_else(|| "в ответе нет choices[0].message.content".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write as _;
    use std::net::TcpListener;
    use std::thread;

    /// Крошечный сервер: один запрос, один ответ. Нужен, чтобы проверить клиент без сети.
    fn serve_once(response: &'static str) -> (u16, thread::JoinHandle<String>) {
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
    fn стаб_заканчивается_как_End_а_не_как_ошибка() {
        let mut stub = Stub::new(vec!["один".to_string()]);
        assert_eq!(stub.complete("p"), Reply::Text("один".to_string()));
        assert_eq!(stub.complete("p"), Reply::End);
    }

    #[test]
    fn разбор_ответа_достаёт_текст() {
        let raw = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n\
                   {\"choices\":[{\"message\":{\"content\":\"привет\"}}]}";
        assert_eq!(parse_response(raw).unwrap(), "привет");
    }

    #[test]
    fn разбор_ответа_видит_код_ошибки() {
        let raw = "HTTP/1.1 502 Bad Gateway\r\n\r\n{\"error\":\"upstream\"}";
        let error = parse_response(raw).unwrap_err();
        assert!(error.contains("502"), "{error}");
    }

    #[test]
    fn разбор_ответа_без_choices_это_ошибка() {
        let raw = "HTTP/1.1 200 OK\r\n\r\n{\"id\":\"x\"}";
        assert!(parse_response(raw).unwrap_err().contains("choices"));
    }

    #[test]
    fn мост_получает_наш_токен_и_модель_и_возвращает_текст() {
        let (port, handle) = serve_once(
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n\
             {\"choices\":[{\"message\":{\"content\":\"TOOL seal /x\"}}]}",
        );
        let mut link = HttpBridge::new("127.0.0.1", port, "local-tk", "deepseek-test");
        let reply = link.complete("сделай");
        assert_eq!(reply, Reply::Text("TOOL seal /x".to_string()));
        let request = handle.join().unwrap();
        assert!(request.contains("Authorization: Bearer local-tk"), "{request}");
        assert!(request.contains("\"model\":\"deepseek-test\""), "{request}");
        assert!(request.contains("\"content\":\"сделай\""), "{request}");
    }

    #[test]
    fn недоступный_мост_это_Error_а_не_End() {
        // Порт, на котором заведомо никто не слушает.
        let mut link = HttpBridge::new("127.0.0.1", 9, "t", "m");
        match link.complete("p") {
            Reply::Error(message) => assert!(message.contains("недоступен"), "{message}"),
            other => panic!("ожидалась ошибка, получено {other:?}"),
        }
    }
}
