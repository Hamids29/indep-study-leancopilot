import LeanCopilotTest
import Mathlib.Data.List.Sort

/-!
Testing `call_gemini` on insertion sort lemmas that only depend on Mathlib.
-/

open List

-- theorem insertionSort_permutation (l : List α) (le : α → α → Bool) :
--     (l.insertionSort (fun x y => le x y = true)).Perm l := by
--   call_gemini  -- replaces: List.perm_insertionSort _ _

-- theorem insertionSort_sorted
--     (l : List α) (le : α → α → Bool)
--     [Std.Total (fun x y => le x y = true)]
--     [IsTrans α (fun x y => le x y = true)] :
--     (l.insertionSort (fun x y => le x y = true)).Pairwise (fun x y => le x y = true) := by
--   call_gemini  -- replaces: List.pairwise_insertionSort _ _

-- lemma insertionSort_length (l : List α) (le : α → α → Bool) :
--     (l.insertionSort (fun x y => le x y = true)).length = l.length := by
--   call_gemini  -- replaces: List.length_insertionSort _ _

-- theorem insertionSort_eq_of_sorted {α : Type*} (le : α → α → Bool)
--     [Std.Total (fun x y => le x y = true)]
--     [IsTrans α (fun x y => le x y = true)]
--     (l : List α)
--     (h : List.Pairwise (fun x y => le x y = true) l) :
--     insertionSort (fun x y => le x y = true) l = l := by
--   call_gemini_recursive


-- theorem orderedInsert_preserves_sorted {α : Type*} (le : α → α → Bool)
--     [Std.Total (fun x y => le x y = true)]
--     [IsTrans α (fun x y => le x y = true)]
--     (a : α) (l : List α)
--     (h : List.Pairwise (fun x y => le x y = true) l) :
--     List.Pairwise (fun x y => le x y = true)
--       (List.orderedInsert (fun x y => le x y = true) a l) := by
--   call_gemini_recursive

-- theorem insertionSort_join {α : Type*} (le : α → α → Bool)
--     [Std.Total (fun x y => le x y = true)]
--     [IsTrans α (fun x y => le x y = true)]
--     (ls : List (List α)) :
--     (ls.map (fun l => insertionSort (fun x y => le x y = true) l)).join ~
--     ls.join := by
--   call_gemini_recursive

theorem insertionSort_unique {α : Type*} (le : α → α → Bool)
    [Std.Total (fun x y => le x y = true)]
    [IsTrans α (fun x y => le x y = true)]
    (hanti : ∀ x y : α, le x y = true → le y x = true → x = y)
    (l₁ l₂ : List α)
    (hperm : l₁ ~ l₂)
    (hsorted1 : List.Pairwise (fun x y => le x y = true) l₁)
    (hsorted2 : List.Pairwise (fun x y => le x y = true) l₂) :
    l₁ = l₂ := by
  call_gemini_recursive

theorem insertionSort_eq_iff_perm {α : Type*} (le : α → α → Bool)
    [Std.Total (fun x y => le x y = true)]
    [IsTrans α (fun x y => le x y = true)]
    (hanti : ∀ x y : α, le x y = true → le y x = true → x = y)
    (l₁ l₂ : List α) :
    insertionSort (fun x y => le x y = true) l₁ =
    insertionSort (fun x y => le x y = true) l₂ ↔ l₁ ~ l₂ := by
  call_gemini_recursive
