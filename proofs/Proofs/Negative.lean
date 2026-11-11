import Proofs.Policy

/-!
# Отрицательный контроль: Lean действительно проверяет

Если бы Lean принимал всё подряд, доказательства из `Policy.lean` ничего не стоили бы.
Здесь два утверждения, которые **обязаны** быть отвергнуты: файл **не должен** собираться.

Проверка: `lake build Proofs.Negative` обязан упасть с `unsolved goals`.
Если он собирается — значит проверка не работает, и доказательствам верить нельзя.

Почему `unsolved goals`, а не «ошибка типа»: Lean сначала принимает применение теоремы,
а потом видит, что цель `false = true` не закрывается. Это и есть отказ.
-/

/-- Ложь: запрет не сильнее разрешения. -/
example : policyAllows examplePolicy "read" "write" "file:/mnt/a.md" = true := by
  have h := deny_beats_allow examplePolicy "read" "write" "file:/mnt/a.md" (by decide)
  rw [h]

/-- Ложь: инструмент выполняет действие, которое политика не разрешает. -/
example : runTool examplePolicy "read" "write" "file:/mnt/a.md"
    = runTool examplePolicy "read" "read" "file:/mnt/a.md" := by
  have h := mediator_refuses examplePolicy "read" "write" "file:/mnt/a.md"
              (deny_beats_allow examplePolicy "read" "write" "file:/mnt/a.md" (by decide))
  rw [h]
