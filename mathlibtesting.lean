-- /-
-- Test file for `call_gemini` using only Mathlib.
-- No cslib, no TimeM, no custom monad -- just standard Mathlib theorems.
-- Replace each `call_gemini` with your tactic and check if it closes the goal.
-- -/
-- import LeanCopilot
-- import LeanCopilotTest
-- import Mathlib

-- open Nat (clog)
-- open scoped List

-- /-!
-- ## Tier 1 — Arithmetic basics
-- These should be closed by `omega` or `simp`. Sanity check your setup.
-- -/

-- /-- basic nat inequality -/
-- theorem test_nat_add_le (n : ℕ) : n ≤ n + 1 := by
--   call_gemini
--   -- Expected: omega

-- /--  multiplication distributes over addition -/
-- theorem test_mul_add (a b c : ℕ) : a * (b + c) = a * b + a * c := by
--   call_gemini
--   -- Expected: ring

-- /--  floor division bound -/
-- theorem test_div_le (n : ℕ) : n / 2 ≤ n := by
--   call_gemini
--   -- Expected: omega

-- /--  sum of halves equals whole -/
-- theorem test_half_sum (n : ℕ) : n / 2 + (n + 1) / 2 = n := by
--   call_gemini
--   -- Expected: omega


-- /-- clog 2 of 1 is 0 -/
-- theorem test_clog_one : clog 2 1 = 0 := by
--   call_gemini
--   -- Expected: simp [Nat.clog]

-- /--  clog is monotone -/
-- theorem test_clog_mono (n m : ℕ) (h : n ≤ m) : clog 2 n ≤ clog 2 m := by
--   call_gemini
--   -- Expected: exact Nat.clog_monotone h

-- /--  clog of ceil half is at most clog n - 1 (for n > 1) -/
-- theorem test_clog_ceil_half (n : ℕ) (h : n > 1) : clog 2 ((n + 1) / 2) ≤ clog 2 n - 1 := by
--   call_gemini

--   -- Expected: Nat.clog_of_one_lt one_lt_two h
--   -- --⏺ This is a different issue from the empty response problem — Gemini IS responding
--   --  but only with reasoning, never writing [PROOF]. This happens because it's a
--   -- hard Mathlib-specific goal requiring Nat.clog_of_one_lt which Gemini doesn't
--   -- know about, so it gives up without committing to a proof.

-- /-!
-- ## Tier 3 — List permutation and sorting
-- -/

-- /--  a list is a permutation of itself -/
-- theorem test_perm_refl (l : List ℕ) : l ~ l := by
--   exact List.Perm.refl l
--   -- Expected: exact List.Perm.refl l


-- example (a b c : ℝ) : a * (b * c) = b * (a * c) := by
--   ring
--   -- Expected: ring

-- example (n : ℕ) (h1 : n > 10) (h2 : n < 20) : n * 2 > 15 := by
-- linarith
