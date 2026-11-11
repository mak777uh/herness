module

/-!
# Политика посредника: три теоремы из docs/VERIFICATION-SPEC.md

Формальная модель политики инструментов herness. Модель не зависит от Rust-кода:
она описывает правило, а соответствие кода правилу доказывается отдельно.

Правило: кто не назван — тот не может. Запрет сильнее разрешения.

**Почему `public`.** В Lean 4.36 с модульной системой объявления по умолчанию приватны
для модуля. Чтобы теоремы были видны снаружи (в `Negative.lean` и в отчёте), каждое
объявление помечено `public`.
-/

public inductive Effect where
  | allow
  | deny
  deriving DecidableEq, Repr

/-- Одно правило политики: инструмент, действие, ресурс, эффект. -/
public structure Rule where
  tool : String
  action : String
  resource : String
  effect : Effect
  deriving Repr

/-- Совпадает ли правило с запросом. В модели — точное совпадение строк:
    тонкости шаблонов (`**`, сегменты) проверяются тестами, а не доказываются. -/
public def ruleMatches (rule : Rule) (tool action resource : String) : Bool :=
  rule.tool == tool && rule.action == action && rule.resource == resource

/-- Политика — список правил. -/
public abbrev Policy := List Rule

/-- Подходит ли под запрос хоть одно правило с эффектом `allow`. -/
public def hasAllow (p : Policy) (tool action resource : String) : Bool :=
  p.any (fun r => ruleMatches r tool action resource && r.effect == Effect.allow)

/-- Подходит ли под запрос хоть одно правило с эффектом `deny`. -/
public def hasDeny (p : Policy) (tool action resource : String) : Bool :=
  p.any (fun r => ruleMatches r tool action resource && r.effect == Effect.deny)

/-- Посредник: разрешено тогда и только тогда, когда есть allow и нет deny.
    Дословная модель `policy_allows` из core-rs/src/loopmod.rs. -/
public def policyAllows (p : Policy) (tool action resource : String) : Bool :=
  hasAllow p tool action resource && !hasDeny p tool action resource

/-! ## T1. Запрет сильнее разрешения -/

/-- Если есть подходящее правило `deny`, посредник отказывает — сколько бы ни было `allow`. -/
public theorem deny_beats_allow (p : Policy) (tool action resource : String)
    (h : hasDeny p tool action resource = true) :
    policyAllows p tool action resource = false := by
  unfold policyAllows
  rw [h]
  simp

/-- Тот же факт в форме отрицания. -/
public theorem deny_means_not_allowed (p : Policy) (tool action resource : String)
    (h : hasDeny p tool action resource = true) :
    ¬ (policyAllows p tool action resource = true) := by
  rw [deny_beats_allow p tool action resource h]
  simp

/-! ## T2. Нет неявных разрешений -/

/-- Если ни одно правило не разрешает запрос, посредник отказывает. -/
public theorem no_allow_means_denied (p : Policy) (tool action resource : String)
    (h : hasAllow p tool action resource = false) :
    policyAllows p tool action resource = false := by
  unfold policyAllows
  rw [h]
  simp

/-- Следствие: пустая политика ничего не разрешает. -/
public theorem empty_policy_denies (tool action resource : String) :
    policyAllows [] tool action resource = false := by
  apply no_allow_means_denied
  simp [hasAllow]

/-! ## T3. Посредник реализует политику -/

/-- Результат попытки выполнить действие. -/
public inductive Outcome where
  | performed
  | refused
  deriving DecidableEq, Repr

/-- Модель инструмента: он выполняет действие только если политика разрешает. -/
public def runTool (p : Policy) (tool action resource : String) : Outcome :=
  if policyAllows p tool action resource then Outcome.performed else Outcome.refused

/-- Если политика не разрешает, инструмент отказывает и действие не выполняется. -/
public theorem mediator_refuses (p : Policy) (tool action resource : String)
    (h : policyAllows p tool action resource = false) :
    runTool p tool action resource = Outcome.refused := by
  unfold runTool
  rw [h]
  rfl

/-- Если политика разрешает, инструмент выполняет действие. -/
public theorem mediator_performs (p : Policy) (tool action resource : String)
    (h : policyAllows p tool action resource = true) :
    runTool p tool action resource = Outcome.performed := by
  unfold runTool
  rw [h]
  rfl

/-! ## Примеры на настоящей форме политики -/

/-- Фрагмент политики: чтение разрешено, запись запрещена на том же ресурсе. -/
public def examplePolicy : Policy :=
  [ ⟨"read", "read", "file:/mnt/a.md", Effect.allow⟩
  , ⟨"read", "write", "file:/mnt/a.md", Effect.deny⟩ ]

/-- Чтение разрешено. -/
example : hasAllow examplePolicy "read" "read" "file:/mnt/a.md" = true := by
  decide

/-- Запись запрещена: deny есть, значит посредник отказывает. -/
example : policyAllows examplePolicy "read" "write" "file:/mnt/a.md" = false := by
  apply deny_beats_allow
  decide

/-- Запрос, которого нет в политике, получает отказ. -/
example : policyAllows examplePolicy "read" "net" "net:1.1.1.1" = false := by
  apply no_allow_means_denied
  decide

/-- Инструмент отказывает, когда политика не разрешает. -/
example : runTool examplePolicy "read" "write" "file:/mnt/a.md" = Outcome.refused := by
  apply mediator_refuses
  apply deny_beats_allow
  decide
