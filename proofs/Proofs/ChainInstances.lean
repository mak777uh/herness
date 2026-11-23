import Proofs.Composition

open Composition

/-!
# K9: конкретные инстансы proof-binding

Python-checker вычисляет subject_sha256 по канонической цепочке и сверяет sha256
с точными байтами `proofs/Proofs/ChainInstances.lean`. Lean-модель не хеширует:
здесь `ProofRef` — закрытая форма ссылки, а теоремы проверяют семантику наличия
proof-binding и покрытия методов на конкретных цепочках.

Граница: это `K9_model_checked`, не `K9_proven`; истинность доказательства и
соответствие Rust-кода модели не проверяются.
-/

namespace ChainInstances

/-- Строки digest/subject opaque в Lean; их проверяет bin/chain.py. -/
def modelProof (subject : String) : ProofRef :=
  ⟨"lean-instance", "proofs/Proofs/ChainInstances.lean",
   "0000000000000000000000000000000000000000000000000000000000000000", subject⟩

/-- Допустимая цепочка: downstream покрывает adjacent и имеет proof-binding. -/
def allowedChain : Chain :=
  ⟨⟨"adjacent", ["allowed.local"], ["GET", "POST"], some (modelProof "allowed-subject")⟩,
   [⟨"downstream", ["allowed.local"], ["GET", "POST"], some (modelProof "allowed-subject")⟩]⟩

/-- Положительный контроль: proof-binding и coverage вместе дают допустимую цепочку. -/
theorem declared_instance_ok : chainOk allowedChain = true := by
  decide

/-- Downstream без proof-binding. -/
def missingProofChain : Chain :=
  ⟨⟨"adjacent", ["allowed.local"], ["GET"], none⟩,
   [⟨"downstream", ["allowed.local"], ["GET"], none⟩]⟩

/-- Отсутствие proof-binding делает цепочку недопустимой. -/
theorem missing_instance_refused : chainOk missingProofChain = false := by
  decide

/-- Proof-binding есть, но downstream не покрывает метод adjacent. -/
def narrowedMethodsChain : Chain :=
  ⟨⟨"adjacent", ["allowed.local"], ["POST"], none⟩,
   [⟨"downstream", ["allowed.local"], ["GET"], some (modelProof "narrowed-subject")⟩]⟩

/-- Proof-binding не заменяет проверку покрытия методов. -/
theorem narrowed_instance_refused : chainOk narrowedMethodsChain = false := by
  decide

end ChainInstances
