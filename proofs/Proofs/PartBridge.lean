module

/-!
# Мост между частями: невозможность соединения по построению

Видение (docs/VISION-0001-harness-as-cell.md §4): если пулы законов несовместимы,
мост не проверяется при соединении — его просто нет. В модели это зависимый тип:
значение `Bridge a b` содержит доказательство совместимости пулов, и без доказательства
значение не построить.

Правило совместимости — клетка O/F матрицы nomos: duty («обязан») против deny
(«запрещено») на одном (subject, action, resource). allow+deny — не конфликт:
запрет сильнее разрешения.

Модель не зависит от кода проверяльщика: соответствие bin/part_contract.py модели
проверяется сверкой (PartBridgeDiff), как policy_diff для политики.
-/

/-- Эффект правила пула: разрешено, запрещено, обязан. -/
public inductive Effect where
  | allow
  | deny
  | duty
  deriving DecidableEq, Repr

/-- Правило пула законов. -/
public structure Rule where
  subject : String
  action : String
  resource : String
  effect : Effect
  deriving DecidableEq, Repr

/-- Пул законов пространства. -/
public structure Pool where
  id : String
  rules : List Rule
  deriving Repr

/-- Часть (ячейка) с принятым пулом. -/
public structure Part where
  id : String
  pool : Pool
  deriving Repr

/-- Одна цель: subject, action, resource. -/
public def sameTarget (r s : Rule) : Bool :=
  r.subject == s.subject && r.action == s.action && r.resource == s.resource

/-- Пара duty/deny на одной цели — противоречие: мост не может и исполнить обязанность,
    и соблюсти запрет. -/
public def clashes (r s : Rule) : Bool :=
  sameTarget r s &&
    ((r.effect == Effect.duty && s.effect == Effect.deny) ||
     (r.effect == Effect.deny && s.effect == Effect.duty))

/-- Вычислимая проверка совместимости пулов: нет ни одной пары duty/deny. -/
public def compatCheck (a b : Pool) : Bool :=
  !(a.rules.any (fun ra => b.rules.any (fun rb => clashes ra rb)))

/-- Мост между частями. Значение нельзя построить без доказательства совместимости:
    если пулы несовместимы, тип пуст — моста нет. Это не проверка при соединении,
    а невозможность соединения. -/
public structure Bridge (a b : Part) where
  compat : compatCheck a.pool b.pool = true

/-- Политика моста — объединение правил обоих пулов. -/
public def bridgeRules (a b : Part) : List Rule :=
  a.pool.rules ++ b.pool.rules

/-- Есть ли в пуле разрешение на запрос. -/
public def hasAllow (p : List Rule) (subject action resource : String) : Bool :=
  p.any (fun r => r.subject == subject && r.action == action && r.resource == resource &&
    r.effect == Effect.allow)

/-- Есть ли в пуле запрет на запрос. -/
public def hasDeny (p : List Rule) (subject action resource : String) : Bool :=
  p.any (fun r => r.subject == subject && r.action == action && r.resource == resource &&
    r.effect == Effect.deny)

/-- Мост пропускает поток, только если есть allow и нет deny ни в одном из пулов. -/
public def bridgeAllows (a b : Part) (subject action resource : String) : Bool :=
  hasAllow (bridgeRules a b) subject action resource &&
    !hasDeny (bridgeRules a b) subject action resource

/-! ## T1. Несовместимые пулы — моста нет -/

/-- Если пулы несовместимы, значение типа `Bridge a b` невозможно:
    оно несло бы доказательство `compatCheck = true`, а проверка даёт `false`. -/
public theorem no_bridge_of_incompatible (a b : Part)
    (h : compatCheck a.pool b.pool = false) : Bridge a b → False := by
  intro br
  have hcontra : true = false := br.compat.symm.trans h
  exact Bool.noConfusion hcontra

/-! ## Вспомогательное: запрет в части остаётся запретом в объединении -/

/-- Запрет в левом пуле остаётся запретом в объединении. -/
public theorem hasDeny_append_left (l₁ l₂ : List Rule) (subject action resource : String)
    (h : hasDeny l₁ subject action resource = true) :
    hasDeny (l₁ ++ l₂) subject action resource = true := by
  unfold hasDeny at h ⊢
  rw [List.any_eq_true] at h ⊢
  obtain ⟨r, hr, hcond⟩ := h
  exact ⟨r, List.mem_append_left _ hr, hcond⟩

/-- Запрет в правом пуле остаётся запретом в объединении. -/
public theorem hasDeny_append_right (l₁ l₂ : List Rule) (subject action resource : String)
    (h : hasDeny l₂ subject action resource = true) :
    hasDeny (l₁ ++ l₂) subject action resource = true := by
  unfold hasDeny at h ⊢
  rw [List.any_eq_true] at h ⊢
  obtain ⟨r, hr, hcond⟩ := h
  exact ⟨r, List.mem_append_right _ hr, hcond⟩

/-! ## T2. Запрет переживает мост -/

/-- Если одна сторона запрещает запрос, мост отказывает — сколько бы ни было allow
    у другой стороны. -/
public theorem deny_survives (a b : Part) (subject action resource : String)
    (h : hasDeny a.pool.rules subject action resource = true) :
    bridgeAllows a b subject action resource = false := by
  have hden : hasDeny (bridgeRules a b) subject action resource = true :=
    hasDeny_append_left a.pool.rules b.pool.rules subject action resource h
  unfold bridgeAllows
  rw [hden]
  simp

/-! ## T3. Мост разрешает — ни одна сторона не запрещает -/

/-- Если мост пропускает запрос, ни в одном из пулов нет запрета на него. -/
public theorem bridge_allow_no_deny (a b : Part) (subject action resource : String)
    (h : bridgeAllows a b subject action resource = true) :
    hasDeny a.pool.rules subject action resource = false ∧
    hasDeny b.pool.rules subject action resource = false := by
  have hunion : hasDeny (bridgeRules a b) subject action resource = false := by
    unfold bridgeAllows at h
    cases hd : hasDeny (bridgeRules a b) subject action resource with
    | false => rfl
    | true =>
      rw [hd] at h
      simp at h
  constructor
  · cases heq : hasDeny a.pool.rules subject action resource with
    | false => rfl
    | true =>
      exfalso
      have ht := hasDeny_append_left a.pool.rules b.pool.rules subject action resource heq
      have hf : hasDeny (a.pool.rules ++ b.pool.rules) subject action resource = false := hunion
      rw [hf] at ht
      exact Bool.noConfusion ht
  · cases heq : hasDeny b.pool.rules subject action resource with
    | false => rfl
    | true =>
      exfalso
      have ht := hasDeny_append_right a.pool.rules b.pool.rules subject action resource heq
      have hf : hasDeny (a.pool.rules ++ b.pool.rules) subject action resource = false := hunion
      rw [hf] at ht
      exact Bool.noConfusion ht
