-- import Cslib.Algorithms.Lean.MergeSort.MergeSort
-- import LeanCopilotTest
-- import Mathlib.Data.Nat.Log

-- set_option autoImplicit false

-- open Cslib.Algorithms.Lean.TimeM

-- variable {α : Type} [LinearOrder α]

-- theorem mergeSort_correct_and_timed (xs : List α) :
--     List.Pairwise (· ≤ ·) ⟪mergeSort xs⟫ ∧ ⟪mergeSort xs⟫ ~ xs ∧
--     (mergeSort xs).time ≤ xs.length * Nat.clog 2 xs.length := by
--   constructor
--   · exact mergeSort_sorted xs
--   constructor
--   · exact mergeSort_perm xs
--   · have h1 : (mergeSort xs).time ≤ timeMergeSortRec xs.length :=
--       mergeSort_time_le xs
--     have h2 : timeMergeSortRec xs.length ≤ xs.length * Nat.clog 2 xs.length :=
--       timeMergeSortRec_le xs.length
--       call_gemini
