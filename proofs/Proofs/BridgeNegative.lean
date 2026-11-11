import Proofs.Bridge

/-!
# Отрицательный контроль для моста

Два ложных утверждения, которые Lean обязан отвергнуть.
Если он их примет — доказательствам моста верить нельзя.
-/

/-- Ложь: запрос выбирает адрес. -/
example (cfg : Config) (req : Request) : (forward cfg req).host = req.wantedHost := by
  rw [address_from_config]

/-- Ложь: мост переписывает тело. -/
example (body : String) : (respond body).body = body ++ "!" := by
  rw [body_preserved]
