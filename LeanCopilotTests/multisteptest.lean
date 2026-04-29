-- /-
-- Multi-step lemma tests for `call_gemini`.
-- Each theorem requires multiple tactic steps to prove.
-- The expected proof is shown so you can compare what Gemini generates.
-- -/
-- import Lean
-- import LeanCopilot
-- import LeanCopilotTest
-- import Mathlib

-- open Nat (clog)

-- /-!
-- ## Test 1 — Simple two step
-- Requires intro then omega. Good warmup.
-- -/

-- /-- If n > 5 then n > 3. Needs two steps: intro the hypothesis then close. -/
-- theorem test_two_step (n : ℕ) (h : n > 5) : n > 3 := by
--   call_gemini
--   /-
--   Expected:
--     have h2 : 3 < 5 := by omega
--     omega
--   Or simply:
--     omega
--   -/

-- /-!
-- ## Test 2 — Three step chain of inequalities
-- Requires building intermediate facts before closing.
-- -/

-- /-- n/2 + (n+1)/2 = n, then use it to bound something. -/
-- theorem test_three_step (n : ℕ) (h : n ≥ 4) : n / 2 ≥ 2 := by
--   call_gemini
--   /-
--   Expected:
--     have h1 : 4 / 2 = 2 := by norm_num
--     have h2 : n / 2 ≥ 4 / 2 := Nat.div_le_div_right h
--     omega
--   -/

-- /-!
-- ## Test 3 — Induction
-- Requires setting up induction explicitly. This is a real multi-step proof.
-- -/

-- /-- Sum of first n naturals equals n*(n+1)/2, stated as 2 * sum = n*(n+1) -/
-- theorem test_sum_formula (n : ℕ) : 2 * (List.range n).sum = n * (n - 1) + n := by
--   call_gemini
--   /-
--   Expected:
--     induction n with
--     | zero => simp
--     | succ n ih =>
--       simp [List.sum_range_succ]
--       omega
--   -/

-- /-!
-- ## Test 4 — Cases then arithmetic
-- Requires splitting on even/odd then handling each case.
-- -/

-- /-- For any n, either n/2 + n/2 = n or n/2 + n/2 = n - 1 -/
-- theorem test_div_cases (n : ℕ) : n / 2 + n / 2 = n ∨ n / 2 + n / 2 = n - 1 := by
--   call_gemini
--   /-
--   Expected:
--     rcases Nat.even_or_odd n with ⟨k, hk⟩ | ⟨k, hk⟩
--     · left; omega
--     · right; omega
--   -/

-- /-!
-- ## Test 5 — Using have to build up a clog bound
-- This mirrors exactly what happens inside the mergeSort complexity proof.
-- Requires chaining two have statements then combining them.
-- -/

-- /-- For n ≥ 2, n/2 * clog 2 (n/2) + (n+1)/2 * clog 2 ((n+1)/2) ≤ n * (clog 2 n - 1) -/
-- theorem test_clog_split (n : ℕ) (hn : n ≥ 2) :
--     n / 2 * clog 2 (n / 2) + (n + 1) / 2 * clog 2 ((n + 1) / 2) ≤
--     n * (clog 2 n - 1) := by
--   call_gemini
--   /-
--   Expected:
--     have h1 : clog 2 (n / 2) ≤ clog 2 n - 1 := by
--       apply Nat.le_trans _ (Nat.clog_monotone (Nat.div_le_self n 2))
--       simp [Nat.clog_of_one_lt one_lt_two hn]
--     have h2 : clog 2 ((n + 1) / 2) ≤ clog 2 n - 1 := by
--       simp [Nat.clog_of_one_lt one_lt_two hn]
--     have h3 : n / 2 + (n + 1) / 2 = n := by omega
--     calc n / 2 * clog 2 (n / 2) + (n + 1) / 2 * clog 2 ((n + 1) / 2)
--         ≤ n / 2 * (clog 2 n - 1) + (n + 1) / 2 * (clog 2 n - 1) := by
--             apply Nat.add_le_add
--             · exact Nat.mul_le_mul_left _ h1
--             · exact Nat.mul_le_mul_left _ h2
--       _ = (n / 2 + (n + 1) / 2) * (clog 2 n - 1) := by ring
--       _ = n * (clog 2 n - 1) := by rw [h3]
--   -/

-- /-!
-- ## Test 6 — Full multi-step list permutation proof
-- Requires fun_induction style reasoning about List.merge.
-- The hardest test in this file.
-- -/

-- /-- append is associative for lists -/
-- theorem test_append_assoc (l1 l2 l3 : List ℕ) :
--     l1 ++ l2 ++ l3 = l1 ++ (l2 ++ l3) := by
--   call_gemini
--   /-
--   Expected:
--     exact List.append_assoc l1 l2 l3
--   -/

-- /-- If l1 ~ l2 and l3 ~ l4 then l1 ++ l3 ~ l2 ++ l4 -/
-- theorem test_perm_append (l1 l2 l3 l4 : List ℕ)
--     (h1 : l1 ~ l2) (h2 : l3 ~ l4) : l1 ++ l3 ~ l2 ++ l4 := by
--   call_gemini
--   /-
--   Expected:
--     exact List.Perm.append h1 h2
--   -/

-- /-- If l ~ l1 ++ l2 and l1 ~ l3 then l ~ l3 ++ l2 -/
-- theorem test_perm_chain (l l1 l2 l3 : List ℕ)
--     (h1 : l ~ l1 ++ l2) (h2 : l1 ~ l3) : l ~ l3 ++ l2 := by
--   call_gemini
--   /-
--   Expected:
--     calc l ~ l1 ++ l2 := h1
--       _ ~ l3 ++ l2 := List.Perm.append h2 (List.Perm.refl l2)
--   -/

-- example (n : ℕ) (h1 : n > 10) (h2 : n < 20) : n * 2 > 15 ∧ n * 2 < 45 := by
-- call_gemini
