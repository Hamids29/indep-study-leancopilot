/-
Test file for `call_gemini` using only Mathlib.
No cslib, no TimeM, no custom monad -- just standard Mathlib theorems.
Replace each `call_gemini` with your tactic and check if it closes the goal.
-/
import LeanCopilot
import LeanCopilotTest
import Mathlib

open Nat (clog)

/-!
## Tier 1 — Arithmetic basics
These should be closed by `omega` or `simp`. Sanity check your setup.
-/

/-- TIER 1a: basic nat inequality -/
theorem test_nat_add_le (n : ℕ) : n ≤ n + 1 := by
  call_gemini
  -- Expected: omega

/-- TIER 1b: multiplication distributes over addition -/
theorem test_mul_add (a b c : ℕ) : a * (b + c) = a * b + a * c := by
  call_gemini
  -- Expected: ring

/-- TIER 1c: floor division bound -/
theorem test_div_le (n : ℕ) : n / 2 ≤ n := by
  call_gemini
  -- Expected: omega

/-- TIER 1d: sum of halves equals whole -/
theorem test_half_sum (n : ℕ) : n / 2 + (n + 1) / 2 = n := by
  call_gemini
  -- Expected: omega

/-!
## Tier 2 — Ceiling log2 properties
These are the exact lemmas used in the mergeSort time bound.
-/

/-- TIER 2a: clog 2 of 1 is 0 -/
theorem test_clog_one : clog 2 1 = 0 := by
  call_gemini
  -- Expected: simp [Nat.clog]

/-- TIER 2b: clog is monotone -/
theorem test_clog_mono (n m : ℕ) (h : n ≤ m) : clog 2 n ≤ clog 2 m := by
  call_gemini
  -- Expected: exact Nat.clog_monotone h

/-- TIER 2c: clog of half is at most clog n - 1 (for n > 1) -/
theorem test_clog_half (n : ℕ) (h : n > 1) : clog 2 (n / 2) ≤ clog 2 n - 1 := by
  call_gemini
  -- Expected: uses Nat.clog_monotone and Nat.clog_of_one_lt

/-- TIER 2d: clog of ceil half is at most clog n - 1 (for n > 1) -/
theorem test_clog_ceil_half (n : ℕ) (h : n > 1) : clog 2 ((n + 1) / 2) ≤ clog 2 n - 1 := by
  call_gemini
  -- Expected: Nat.clog_of_one_lt one_lt_two h

/-!
## Tier 3 — List permutation and sorting
-/

/-- TIER 3a: a list is a permutation of itself -/
theorem test_perm_refl (l : List ℕ) : l ~ l := by
  call_gemini
  -- Expected: exact List.Perm.refl l

/-- TIER 3b: permutation is symmetric -/
theorem test_perm_symm (l1 l2 : List ℕ) (h : l1 ~ l2) : l2 ~ l1 := by
  call_gemini
  -- Expected: exact h.symm

/-- TIER 3c: permutation preserves length -/
theorem test_perm_length (l1 l2 : List ℕ) (h : l1 ~ l2) : l1.length = l2.length := by
  call_gemini
  -- Expected: exact h.length_eq

/-- TIER 3d: take and drop reconstruct the original list -/
theorem test_take_drop (n : ℕ) (l : List ℕ) : l.take n ++ l.drop n = l := by
  call_gemini
  -- Expected: exact List.take_append_drop n l

/-- TIER 3e: Mathlib's List.merge output is a permutation of the concatenation -/
theorem test_merge_perm (l1 l2 : List ℕ) : List.merge l1 l2 ~ l1 ++ l2 := by
  call_gemini
  -- Expected: exact List.merge_perm_append l1 l2

/-!
## Tier 4 — The core algebraic inequality
The mathematical heart of the n*log(n) bound. Pure nat arithmetic and clog.
-/

/-- TIER 4: key inequality for merge sort time complexity -/
theorem test_nlogn_recurrence (n : ℕ) (h : n > 1) :
    (n / 2) * clog 2 (n / 2) +
    ((n + 1) / 2) * clog 2 ((n + 1) / 2) + n ≤
    n * clog 2 n := by
  call_gemini
  -- Expected approach:
  -- have h1 : clog 2 (n / 2) ≤ clog 2 n - 1 := ...
  -- have h2 : clog 2 ((n + 1) / 2) ≤ clog 2 n - 1 := ...
  -- have h3 : n / 2 + (n + 1) / 2 = n := by omega
  -- nlinarith or calc using h1, h2, h3
