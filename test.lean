import LeanCopilot
import LeanCopilotTest

-- Test 1: Basic tactic suggestion
theorem add_zero (n : Nat) : n + 0 = n := by
  simp [Nat.zero_eq]


-- Test 2: Simple proof
theorem simple (n m : Nat) : n + m = m + n := by
  omega

-- Test 3: Search for complete proof
theorem search_test (n : Nat) : n * 1 = n := by
  search_proof

theorem if_even_then_divisible (n : Nat) (h : n % 2 = 0) : n % 2 = 0 := by
  call_gemini
