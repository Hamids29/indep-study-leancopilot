# LeanCopilot + Gemini: AI-Assisted Theorem Proving in Lean 4

A research testbed that integrates **Google Gemini** with **[LeanCopilot](https://github.com/lean-dojo/LeanCopilot)** to build an AI proof assistant for Lean 4. The system gives Gemini rich context — proof state, local lemmas, definitions, and semantically retrieved Mathlib premises — then iterates using Lean's own error messages as feedback.

This was built as an independent study project exploring neural-assisted formal mathematics.

---

## What This Project Does

When you're proving a theorem in Lean 4, you call one of the custom tactics defined here (`call_gemini`, `call_gemini_auto`, or `call_gemini_recursive`). The tactic:

1. Captures your current **proof state** (goals, hypotheses)
2. Pulls **local lemmas and definitions** from your file
3. Uses **LeanCopilot's ByT5 neural retriever** to find semantically relevant Mathlib premises
4. Queries **Loogle** (live Mathlib search) for additional lemma candidates
5. Sends all of this to **Gemini 2.5 Flash** via a local Python bridge server
6. Gemini generates proof tactic suggestions in parallel (4 sketches with different strategies)
7. The best suggestion is inserted into your proof (or fed back to Gemini if it fails)

```
Lean file
   │
   ├─ proof state ──────────────────────────────────────────┐
   ├─ local lemmas/defs                                      │
   └─ LeanCopilot ByT5 retrieval                            ▼
                                                 gemini-server/server.py
                                                      │
                                          ┌───────────┴───────────┐
                                          │    Loogle search       │
                                          │    4 parallel sketches │
                                          │    Gemini 2.5 Flash    │
                                          └───────────┬───────────┘
                                                      │
                                          tactic suggestion(s)
                                                      │
                                                 Lean infoview
```

---

## Prerequisites and Dependencies

### 1. Set up LeanCopilot

Follow the full setup guide at the **[LeanCopilot repository](https://github.com/lean-dojo/LeanCopilot)**. In particular you need:

- **Lean 4 v4.28.0** (the exact version in `lean-toolchain`)
- **[elan](https://github.com/leanprover/elan)** — the Lean version manager
- **[Lake](https://github.com/leanprover/lake)** — Lean's package manager (ships with elan)
- **ctranslate2** — native library for ByT5 inference (LeanCopilot's README covers installation for macOS/Linux/Windows)
- **curl** must be available at runtime (used to call the local server)

LeanCopilot's build downloads the ByT5 model weights (~200 MB) on first use.

### 2. Gemini API Key

Get a free API key from [Google AI Studio](https://aistudio.google.com/) and set it as an environment variable:

```bash
export GEMINI_API_KEY="your-key-here"
```

Or create a `.env` file in the project root (already in `.gitignore`):

```
GEMINI_API_KEY=your-key-here
```

### 3. Python dependencies

```bash
cd gemini-server
pip install google-generativeai requests python-dotenv
```

Python 3.9+ is required.

---

## Getting Started

### Step 1: Clone and build

```bash
git clone https://github.com/Hamids29/indep-study-leancopilot
cd indep-study-leancopilot
lake update       # resolves and downloads all Lean dependencies
lake build        # compiles everything (~10–20 min first time due to Mathlib)
```

### Step 2: Start the Gemini bridge server

```bash
cd gemini-server
python server.py
```

The server listens on `localhost:23338`. Keep it running in a separate terminal while you prove things.

### Step 3: Open a Lean file and use the tactics

In VS Code with the Lean 4 extension, open any `.lean` file and use one of the three tactics:

```lean
import LeanCopilotTest.Gemini

-- Single-shot: shows Gemini's suggestion in the infoview, falls back to sorry
example (n : ℕ) : n ≤ n + 1 := by
  call_gemini

-- Iterative: calls Gemini up to 10 times, applying tactics step by step
example (a b c : ℕ) : a * (b + c) = a * b + a * c := by
  call_gemini_auto

-- Error-feedback loop: if Gemini fails, feeds Lean's error back for self-correction
theorem insertionSort_unique (l1 l2 : List ℕ) (h : List.Sorted (· ≤ ·) l1)
    (h2 : List.Sorted (· ≤ ·) l2) (h3 : l1.insertionSort (· ≤ ·) = l2.insertionSort (· ≤ ·)) :
    l1 = l2 := by
  call_gemini_recursive
```

Suggestions appear in the **Lean Infoview** panel with the proof attempt and Gemini's reasoning.

---

## Project Structure

```
.
├── LeanCopilotTest/
│   ├── Gemini.lean          # Core tactic engine — the main contribution
│   └── Basic.lean           # Minimal placeholder module
├── gemini-server/
│   └── server.py            # Python bridge to Gemini API (~860 lines)
├── test_insertion_sort.lean  # Active: insertion sort correctness proofs
├── mathlibtesting.lean       # Arithmetic + list theorem tests (reference)
├── multisteptest.lean        # Multi-step proof templates (reference)
├── mergersort.lean           # WIP: mergesort complexity proof
├── test2.lean                # WIP: probability theory / measure kernels
├── lakefile.toml             # Lake package config
├── lean-toolchain            # Pins Lean 4 v4.28.0
└── .github/workflows/        # CI: lean-action checks every push
```

---

## The Three Tactics

### `call_gemini` — Single-shot suggestion

Calls Gemini once and displays up to 4 suggestions in the infoview. Does **not** apply any tactic automatically — you pick what to use. Falls back to `sorry` if the server is unreachable.

Best for: exploring what Gemini thinks will work, inspecting reasoning, quick lookups.

```lean
example : 2 + 2 = 4 := by call_gemini
```

### `call_gemini_auto` — Sequential application (up to 10 steps)

Calls Gemini repeatedly, applying each returned tactic to the proof state, until the proof closes or a tactic fails. Each step is logged to the infoview with Gemini's reasoning.

Best for: straightforward theorems that require several standard tactics in sequence.

```lean
theorem mul_comm_example (a b : ℕ) : a * b = b * a := by call_gemini_auto
```

### `call_gemini_recursive` — Error-feedback loop (up to 5 rounds)

If a tactic attempt fails, the exact Lean error message is sent back to Gemini so it can correct itself. This is the most powerful tactic for hard goals.

Best for: complex proofs, cases where standard automation fails, proofs requiring specific Mathlib lemmas.

```lean
theorem insertionSort_eq_iff_perm (l1 l2 : List ℕ) :
    l1.insertionSort (· ≤ ·) = l2.insertionSort (· ≤ ·) ↔
    l1.insertionSort (· ≤ ·) ~ l2.insertionSort (· ≤ ·) := by
  call_gemini_recursive
```

---

## How the Server Works

`gemini-server/server.py` exposes a single endpoint: `POST /generate`.

**Input (JSON):**

| Field | Description |
|-------|-------------|
| `input` | Pretty-printed proof state (goals + hypotheses) |
| `localLemmas` | Theorems proved earlier in the same file |
| `localDefs` | Definitions from the same file |
| `retrievedPremises` | ByT5 semantic matches from Mathlib |
| `singleStep` | Whether to return just one tactic or a full proof |
| `leanError` | Lean's error message from a failed prior attempt |

**Output (JSON):**

```json
{
  "outputs": [
    {"output": "omega", "score": 0.95, "reasoning": "The goal is linear arithmetic..."},
    ...
  ],
  "display": "human-readable summary"
}
```

**Retrieval pipeline:** The server runs Loogle queries on identifiers extracted from the proof state, merges those results with the ByT5 premises Lean already computed, deduplicates, and presents the combined set to Gemini as context.

**4-sketch diversity:** Every request spawns 4 parallel Gemini calls with different temperature and strategy settings:

| Sketch | Strategy | Temperature |
|--------|----------|-------------|
| A (DIRECT) | Minimal single tactic | 0.10 |
| B (EXPLORATORY) | Considers multiple approaches | 0.65 |
| C (STEP-BY-STEP) | Breaks into `have` subgoals | 0.30 |
| D (AUTOMATION) | Tries `simp_all`/`aesop` first | 0.50 |

Results are ranked: non-`sorry` answers first, then by confidence score.

---

## Lean Tactics You Can Use in Proofs

Beyond the AI tactics, these are the standard Lean 4 / Mathlib tactics that Gemini is instructed to use and that appear throughout the test files:

| Tactic | Use case |
|--------|----------|
| `omega` | Linear arithmetic over integers and naturals |
| `ring` | Polynomial ring equalities |
| `linarith` | Linear arithmetic with hypotheses |
| `nlinarith` | Nonlinear arithmetic |
| `simp` | Simplification using a lemma set |
| `simp_all` | Simplify everything with all hypotheses |
| `aesop` | General purpose search-based automation |
| `exact` | Close goal with a specific term |
| `apply` | Apply a lemma to reduce the goal |
| `refine` | Partially apply with holes |
| `induction` | Structural induction |
| `rcases` / `cases` | Case analysis / pattern matching |
| `constructor` | Split conjunction or existential goals |
| `intro` | Introduce universally quantified variables |
| `have` | Introduce intermediate lemmas |
| `calc` | Chain equalities/inequalities step by step |
| `gcongr` | Monotone congruence closure |
| `norm_num` | Concrete numeric computations |
| `decide` | Decidable propositions by computation |
| `tauto` | Propositional tautologies |
| `use` | Provide a witness for existentials |
| `rw` / `rw [← ...]` | Rewrite with equalities (forward / backward) |
| `push_neg` | Push negations through quantifiers |
| `contrapose` | Proof by contrapositive |
| `inferInstance` | Discharge typeclass goals automatically |

---

## What We Proved (and Attempted)

### Working proofs (`test_insertion_sort.lean`)

- `insertionSort_unique` — if two sorted lists have the same insertion sort, they are equal
- `insertionSort_eq_iff_perm` — two inputs yield the same sorted output iff they are permutations of each other

These use `call_gemini_recursive` and draw on Mathlib's `List.Sorted` and `List.Perm` API.

### Reference test suite (`mathlibtesting.lean`)

Exercises for:
- Basic inequalities (`n ≤ n + 1`, `mul_add`)
- Ceiling log base 2 bounds (`Nat.clog`)
- List permutation reflexivity

### Multi-step templates (`multisteptest.lean`)

Commented-out proof skeletons covering:
- Two-step `intro` + `omega`
- Three-step inequality chains
- Induction + case splits
- Complex `Nat.clog` bounds (needed for mergesort analysis)

### Work in progress

- **`mergersort.lean`** — aims to prove that `mergeSort` produces a sorted permutation in ≤ n·log₂(n) comparisons. Stalls on `Nat.clog` lemmas.
- **`test2.lean`** — probability theory (measure kernels, risk functions). High difficulty; needs deeper Mathlib Probability API work.

---

## Where to Continue

If you want to build on this project, here are the most promising directions:

### 1. Complete the mergesort complexity proof
`mergersort.lean` is the natural next target. The key lemmas needed are around `Nat.clog_le_log` and relating the recursive call count to `Nat.clog`. LeanCopilot's ByT5 retrieval already pulls relevant premises — the gap is getting the induction structure right.

### 2. Upgrade to a smarter retry strategy
`call_gemini_recursive` currently retries up to 5 times with the raw Lean error. A better approach would be to parse the error, identify which hypothesis or lemma name is wrong, and do targeted Loogle lookups before retrying.

### 3. Add VS Code UI / keybindings
Right now the tactics are called inline in Lean files. A VS Code extension command that inserts `call_gemini_recursive` at the cursor and shows a diff of what was inserted would make the workflow much smoother.

### 4. Replace Gemini with a local model
`server.py` is decoupled from the specific LLM. Replacing `_call_gemini_api` with a local model endpoint (e.g., LLaMA or DeepSeek-Prover via Ollama) would make the system fully offline and potentially faster.

### 5. Evaluate on MiniF2F or ProofNet benchmarks
The infrastructure is in place to run batch evaluation. Adapting `server.py` to take a benchmark file and produce pass rates would give a proper comparison against other LLM-based provers.

### 6. Finer proof-state encoding
Currently the proof state is sent as a plain string. Structured encoding (separate fields for each hypothesis, goal type, universe level) could help Gemini reason more reliably about complex goals.

---

## Related Work

- **[LeanCopilot](https://github.com/lean-dojo/LeanCopilot)** — the foundation this project builds on. Provides ByT5 premise retrieval and the tactic suggestion infrastructure.
- **[Mathlib4](https://github.com/leanprover-community/mathlib4)** — the Lean 4 math library we prove things about.
- **[Loogle](https://loogle.lean-lang.org/)** — live Mathlib search by type signature, used in the retrieval pipeline.
- **[LeanDojo](https://github.com/lean-dojo/LeanDojo)** — benchmark and tooling for neural theorem proving in Lean.
- **[DeepSeek-Prover](https://github.com/deepseek-ai/DeepSeek-Prover-V1.5)** — SOTA LLM fine-tuned specifically for Lean proofs.

---

## License

MIT
