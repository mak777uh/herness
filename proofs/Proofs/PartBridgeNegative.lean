import Proofs.PartBridge

/-!
# Отрицательный контроль моста частей

Два ложных утверждения, которые Lean обязан отвергнуть.
Если он их примет — доказательствам моста верить нельзя.
-/

/-- Пространство человека: личное запрещено. -/
def controlHumanPool : Pool :=
  ⟨"human-base", [⟨"cell", "transfer", "data:personal", Effect.deny⟩]⟩

/-- Жадный сервис: личное обязательно — duty против deny. -/
def controlGreedyPool : Pool :=
  ⟨"service-greedy", [⟨"cell", "transfer", "data:personal", Effect.duty⟩]⟩

def controlHuman : Part := ⟨"part:nomos", controlHumanPool⟩
def controlGreedy : Part := ⟨"part:greedy", controlGreedyPool⟩

/-- Ложь: мост между несовместимыми пулами существует. -/
example : Bridge controlHuman controlGreedy := by
  constructor

/-- Ложь: мост разрешает то, что одна сторона запрещает. -/
example : bridgeAllows controlHuman controlGreedy "cell" "transfer" "data:personal" = true := by
  decide
