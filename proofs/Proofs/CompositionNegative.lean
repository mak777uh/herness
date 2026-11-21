import Proofs.Composition

open Composition

/-!
# Отрицательный контроль K9

Три ложных утверждения, которые Lean обязан отвергнуть.
Если он их примет — модели композиции верить нельзя.
-/

/-- Граница первой комнаты. -/
def controlBound : Bound :=
  ⟨[Channel.read "/room", Channel.write "/room/work"]⟩

/-- Шаг чтения внутри комнаты. -/
def controlRead : Step := ⟨"read", [Channel.read "/room"]⟩

/-- Шаг записи внутри комнаты. -/
def controlWrite : Step := ⟨"write", [Channel.write "/room/work"]⟩

/-- Ложь: композиция двух шагов внутри границы выходит за границу. -/
example : within (comp controlRead controlWrite) controlBound = false := by
  decide

/-- Ложь: пошагово безопасные шаги дают безопасную композицию. -/
example : leaks (comp secretStep netStep) = false := by
  decide

/-- Цепочка с непроверенным downstream. -/
def controlChain : Chain :=
  ⟨⟨"adjacent", ["allowed.local"], true⟩,
   [⟨"downstream", ["allowed.local"], false⟩]⟩

/-- Ложь: цепочка с непроверенным downstream допустима. -/
example : chainOk controlChain = true := by
  decide
