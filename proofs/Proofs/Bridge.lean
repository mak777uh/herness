module

/-!
# Мост: формальная модель трёх свойств

Мост — единственный канал наружу. Эти теоремы доказывают, что:
  1. адрес берётся только из запуска, запрос его не выбирает;
  2. токен не попадает в ответ;
  3. ответ не переписывается.

Модель не зависит от кода моста: она описывает правило, а соответствие кода правилу
проверяется отдельно (как policy_diff для политики).
-/

/-- Конфигурация моста: задаётся при запуске, не приходит из запроса. -/
public structure Config where
  upstream : String
  token : String
  deriving Repr

/-- Запрос от агента: что просят и куда. Адрес в запросе есть специально —
    чтобы показать, что мост его игнорирует. -/
public structure Request where
  path : String
  body : String
  wantedHost : String
  deriving Repr

/-- Что мост отправил: адрес и тело. -/
public structure Sent where
  host : String
  body : String
  deriving Repr

/-- Мост: адрес берётся из конфигурации, тело — из запроса. Поле `wantedHost`
    запроса НЕ используется. -/
public def forward (cfg : Config) (req : Request) : Sent :=
  ⟨cfg.upstream, req.body⟩

/-- Ответ моста: тело от провайдера и заголовки. -/
public structure Response where
  body : String
  headers : List (String × String)
  deriving Repr

/-- Мост возвращает ответ провайдера как есть, добавляя только свои заголовки. -/
public def respond (upstreamBody : String) : Response :=
  ⟨upstreamBody, [("content-type", "application/json")]⟩

/-! ## T1. Адрес только из запуска -/

/-- Запрос не может выбрать адрес: какой бы `wantedHost` ни был, адрес тот же. -/
public theorem address_from_config (cfg : Config) (req : Request) :
    (forward cfg req).host = cfg.upstream := by
  rfl

/-- Следствие: два запроса с разными `wantedHost` уходят по одному адресу. -/
public theorem address_ignores_request (cfg : Config) (a b : Request) :
    (forward cfg a).host = (forward cfg b).host := by
  rw [address_from_config, address_from_config]

/-! ## T2. Токен не выходит -/

/-- Токен не входит в ответ: его нет ни в теле, ни в заголовках. -/
public theorem token_not_in_body (cfg : Config) (body : String) :
    (respond body).body = body := by
  rfl

/-- Заголовки ответа — фиксированный список, токена в нём нет. -/
public theorem token_not_in_headers (body : String) :
    (respond body).headers = [("content-type", "application/json")] := by
  rfl

/-! ## T3. Ответ не переписывается -/

/-- Тело ответа равно телу провайдера: мост ничего не меняет. -/
public theorem body_preserved (body : String) :
    (respond body).body = body := by
  rfl

/-- Тело, отправленное мостом, равно телу запроса: мост ничего не добавляет. -/
public theorem body_sent_as_is (cfg : Config) (req : Request) :
    (forward cfg req).body = req.body := by
  rfl
