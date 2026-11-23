module

/-!
# K9: композиция сохраняет границы

Модель композиции инструментов и цепочки мостов (docs/CONSTITUTION-v0-2026-11-16.md, K9).

Три вопроса:
  1. Складываются ли замыкания шагов без выхода за границу?
  2. Достаточно ли пошаговой проверки?
  3. Что делает исполнитель, если композиция утекает?

Ответы:
  T1 — объединение замыканий внутри границы;
  T2 — нет: чтение секрета и сеть по отдельности не утекают, вместе — утекают;
  T3 — исполнитель отказывает при утечке; T4 — исполняет без утечки;
  T5/T6 — downstream-мост без доказательства делает цепочку недопустимой;
  T7 — пустое покрытие методов downstream при непустом adjacent — отказ (V1).

Граница модели: проверяются объявленные замыкания, а не поведение кода.
Это `K9_model_checked`, а не `K9_proven`.
-/

namespace Composition

/-- Канал, который шаг может затронуть. -/
public inductive Channel where
  | read (path : String)
  | write (path : String)
  | net (dest : String)
  | secret (name : String)
  deriving DecidableEq, Repr

/-- Шаг: инструмент или мост с объявленным замыканием. -/
public structure Step where
  id : String
  closure : List Channel
  deriving Repr

/-- Граница: каналы, разрешённые на границе первой комнаты. -/
public structure Bound where
  allowed : List Channel
  deriving Repr

/-- Канал входит в границу. -/
public def permitted (b : Bound) (c : Channel) : Bool :=
  b.allowed.contains c

/-- Шаг не выходит за границу: каждый его канал разрешён. -/
public def within (s : Step) (b : Bound) : Bool :=
  s.closure.all (fun c => permitted b c)

/-- Последовательная композиция: замыкания складываются. -/
public def comp (a b : Step) : Step :=
  ⟨a.id ++ ";" ++ b.id, a.closure ++ b.closure⟩

/-! ## T1. Композиция внутри границы остаётся внутри -/

public theorem comp_within (a b : Step) (bd : Bound)
    (ha : within a bd = true) (hb : within b bd = true) :
    within (comp a b) bd = true := by
  unfold within at ha hb
  unfold within comp
  show (a.closure ++ b.closure).all (fun c => permitted bd c) = true
  rw [List.all_append, ha, hb]
  rfl

/-! ## T2. Пошаговой проверки недостаточно -/

/-- Шаг читает секрет. -/
public def readsSecret (s : Step) : Bool :=
  s.closure.any (fun c => match c with
    | .secret _ => true
    | _ => false)

/-- Шаг отправляет наружу (в сеть). -/
public def sendsExternal (s : Step) : Bool :=
  s.closure.any (fun c => match c with
    | .net _ => true
    | _ => false)

/-- Утечка: в одном замыкании есть и секрет, и сеть. -/
public def leaks (s : Step) : Bool :=
  readsSecret s && sendsExternal s

/-- Чтение секрета. -/
public def secretStep : Step :=
  ⟨"read-secret", [Channel.secret "key"]⟩

/-- Отправка наружу. -/
public def netStep : Step :=
  ⟨"send", [Channel.net "allowed.local"]⟩

/-- T2: по отдельности шаги не утекают, а их композиция утекает.
    Это контрпример к «K9 следует из пошаговой проверки». -/
public theorem leak_created_by_composition :
    leaks secretStep = false ∧ leaks netStep = false ∧
    leaks (comp secretStep netStep) = true := by
  decide

/-! ## T3/T4. Исполнитель отказывает при утечке -/

/-- Исход исполнения композиции. -/
public inductive Outcome where
  | performed
  | refused
  deriving DecidableEq, Repr

/-- Исполнитель: композиция с утечкой не исполняется. -/
public def runChain (s : Step) : Outcome :=
  if leaks s then Outcome.refused else Outcome.performed

/-- T3: утечка — отказ. -/
public theorem runChain_refuses_leak (s : Step) (h : leaks s = true) :
    runChain s = Outcome.refused := by
  simp [runChain, h]

/-- T4: без утечки — исполнение. -/
public theorem runChain_performs_safe (s : Step) (h : leaks s = false) :
    runChain s = Outcome.performed := by
  simp [runChain, h]

/-! ## T5/T6. Цепочка мостов: без доказательства — отказ -/

/-- Объявление моста: адреса, которые он пропускает, и доказан ли он. -/
public structure Bridge where
  id : String
  destinations : List String
  methods : List String
  proven : Bool
  deriving Repr

/-- Цепочка: adjacent-мост и downstream-мосты. -/
public structure Chain where
  adjacent : Bridge
  downstream : List Bridge
  deriving Repr

/-- Все downstream-мосты доказаны. -/
public def allProven (bs : List Bridge) : Bool :=
  bs.all (fun b => b.proven)

/-- Adjacent-мост форвардит адрес, и downstream его пропускает. -/
public def forwards (adj : Bridge) (b : Bridge) : Bool :=
  adj.destinations.all (fun d => b.destinations.contains d)

/-- Downstream обязан покрывать каждый метод adjacent (coverage, V1). -/
public def forwardsMethods (adj : Bridge) (b : Bridge) : Bool :=
  adj.methods.all (fun m => b.methods.contains m)

/-- Цепочка допустима: все downstream доказаны, форвардят адреса и покрывают методы adjacent. -/
public def chainOk (c : Chain) : Bool :=
  allProven c.downstream && c.downstream.all (forwards c.adjacent)
    && c.downstream.all (forwardsMethods c.adjacent)

/-- T5: непроверенный downstream делает цепочку недопустимой. -/
public theorem unproven_refused (c : Chain) (h : allProven c.downstream = false) :
    chainOk c = false := by
  simp [chainOk, h]

/-- T6: допустимая цепочка требует доказательства у всех downstream. -/
public theorem chainOk_all_proven (c : Chain) (h : chainOk c = true) :
    allProven c.downstream = true := by
  simp only [chainOk, Bool.and_eq_true] at h
  exact h.1.1

/-- T7: пустое покрытие методов downstream при непустом adjacent — отказ. -/
public theorem methods_coverage_refused (c : Chain) (b : Bridge)
    (hb : b ∈ c.downstream) (he : b.methods = []) (ha : c.adjacent.methods ≠ []) :
    chainOk c = false := by
  have hfb : forwardsMethods c.adjacent b = false := by
    show c.adjacent.methods.all (fun m => b.methods.contains m) = false
    cases hd : c.adjacent.methods with
    | nil => exact absurd hd ha
    | cons head tail => simp [he]
  have hnot : ¬ (c.downstream.all (forwardsMethods c.adjacent) = true) := by
    intro htrue
    have h1 := (List.all_eq_true (l := c.downstream)
      (p := forwardsMethods c.adjacent)).mp htrue b hb
    simp [hfb] at h1
  cases hh : c.downstream.all (forwardsMethods c.adjacent) with
  | false => simp [chainOk, hh]
  | true => exact absurd hh hnot

end Composition
