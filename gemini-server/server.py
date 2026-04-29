"""
Gemini API bridge server for LeanCopilot.

4-sketch + refinement approach with full traceability.
Runs 4 diverse Gemini attempts in parallel, refines sorry results,
and emits rich terminal logs showing exactly what ByT5/Loogle contributed.

Usage:
    export GEMINI_API_KEY="your-key-here"
    python server.py
"""

import os
import re
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error
import urllib.parse
from dotenv import load_dotenv

load_dotenv("../.env")

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

PORT = 23338
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
)

# Always-injected premises regardless of retrieval results.
ALWAYS_AVAILABLE = [
    "inferInstance  -- discharge any typeclass goal automatically",
    "le_rfl         -- prove x ≤ x",
    "le_refl        -- prove x ≤ x (alternative)",
    "Kernel.comp_assoc  -- (κ ∘ₖ η) ∘ₖ P = κ ∘ₖ (η ∘ₖ P)",
    "iInf_le_of_le  -- iInf_le_of_le witness h : ⨅ i, f i ≤ f witness (requires explicit witness)",
    "iInf_le        -- iInf_le i : ⨅ i, f i ≤ f i",
]

# ──────────────────────────────────────────────────────────────────────────────
# 4 Sketch configurations  (diverse temperatures + prompting angles)
# ──────────────────────────────────────────────────────────────────────────────

SKETCHES = [
    {
        "id": "A",
        "name": "DIRECT",
        "temperature": 0.10,
        "hint": (
            "Use the most direct, minimal tactic sequence. "
            "Prefer a single tactic (omega/ring/simp/exact) if possible."
        ),
    },
    {
        "id": "B",
        "name": "EXPLORATORY",
        "temperature": 0.65,
        "hint": (
            "Consider several proof strategies (simp, omega, exact, apply, ring, linarith) "
            "and pick whichever best matches the goal shape."
        ),
    },
    {
        "id": "C",
        "name": "STEP-BY-STEP",
        "temperature": 0.30,
        "hint": (
            "Break the proof into small steps using `have` intermediates. "
            "Be explicit and structured — spell out every subgoal."
        ),
    },
    {
        "id": "D",
        "name": "AUTOMATION",
        "temperature": 0.50,
        "hint": (
            "Lean heavily on automation first: try simp_all, aesop, decide, omega, norm_num "
            "before anything manual. Only fall back to explicit lemmas if automation fails."
        ),
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Lean 4 theorem prover using Mathlib.

CRITICAL RULES — follow these before generating any tactic:

1. NEVER invent lemma names. Only use names explicitly listed in [VALID PREMISES] or
   [LOCAL THEOREMS]. If you cannot find the right lemma there, use `sorry`.

2. TYPECLASS GOALS: Always discharge with `inferInstance`. Never invent names like
   `IsMarkovKernel.comp` or `Kernel.instIsMarkovKernel` — they do not exist.

3. REFLEXIVITY GOALS: Use `le_rfl` or `rfl`. Never invent a named lemma for this.

4. When in doubt between two similar lemma names, prefer the one with more arguments
   (e.g. `iInf_le_of_le` over `iInf_le`) as Lean requires explicit witnesses.

Given a proof state, respond with a [PROOF] block followed by a [REASON] block.

MANDATORY FORMAT:

[PROOF]
<tactic 1>
<tactic 2>
...
[END]
[REASON]
<one or two sentences explaining why this tactic works>
[END]

If you cannot prove the goal:
[PROOF]
sorry
[END]
[REASON]
Goal is too complex to close automatically.
[END]

The FIRST line of your response MUST be "[PROOF]". Do NOT write any text before [PROOF].

STRICT RULES FOR [PROOF]:
- Every line must be a bare Lean 4 tactic — no comments, no English, no explanations.
- Do NOT write `--` comments inside [PROOF].
- Do NOT write `by` as a standalone word.
- Output at most 15 tactic lines.

VALID LEAN 4 TACTICS — use only these:
  omega
  ring
  simp
  simp_all
  simp [lemma1, lemma2]
  simp_rw [lemma1]
  linarith
  linarith [h1, h2]
  nlinarith
  norm_num
  decide
  native_decide
  rfl
  trivial
  assumption
  contradiction
  exact <term>
  apply <lemma>
  refine <term>
  intro <names>
  intros
  constructor
  left
  right
  use <term>
  cases <expr>
  rcases <expr> with <pattern>
  obtain <pattern> := <expr>
  induction <expr> with | <case> => <tactic> | <case> => <tactic>
  have <name> : <type> := by <tactic>
  rw [<lemma>]
  rw [← <lemma>]
  inferInstance
  ext
  funext
  push_neg
  field_simp
  ring_nf
  norm_cast
  gcongr
  positivity
  aesop
  · <tactic>
  <;> <tactic>
  calc <expr> _ = <expr> := by <tactic>

FORBIDDEN — these are NOT Lean 4 tactics:
  auto, tauto, reflexivity, simpl, destruct, Qed, Proof.
  Any English sentence or phrase

EXAMPLE 1 — simple arithmetic:
[PROOF]
linarith
[END]
[REASON]
The goal is a linear inequality so linarith closes it directly from the hypotheses.
[END]

EXAMPLE 2 — case split:
[PROOF]
rcases Nat.even_or_odd n with ⟨k, hk⟩ | ⟨k, hk⟩
· left; omega
· right; omega
[END]
[REASON]
Split on even/odd cases; in each branch omega closes the arithmetic goal.
[END]

EXAMPLE 3 — exact lemma:
[PROOF]
exact List.append_assoc l1 l2 l3
[END]
[REASON]
This is directly list append associativity from Mathlib.
[END]

EXAMPLE 4 — induction:
[PROOF]
induction n with
| zero => simp
| succ n ih =>
  simp [List.sum_range_succ]
  omega
[END]
[REASON]
Induct on n; the base case is trivial and the inductive step follows from the range sum lemma.
[END]

EXAMPLE 5 — typeclass discharge with inferInstance:
[PROOF]
exact iInf_le_of_le (κ ∘ₖ η) (iInf_le_of_le inferInstance le_rfl)
[END]
[REASON]
The witness is κ ∘ₖ η; the IsMarkovKernel instance is inferred automatically via inferInstance rather than naming a nonexistent lemma.
[END]

EXAMPLE 6 — cannot prove:
[PROOF]
sorry
[END]
[REASON]
Goal is too complex to close automatically.
[END]"""

# ──────────────────────────────────────────────────────────────────────────────
# Prose / tactic filtering helpers  (unchanged from original)
# ──────────────────────────────────────────────────────────────────────────────

_PROSE_PATTERNS = [
    re.compile(r'\.$'),
    re.compile(r'\b(the|this|we|since|because|note|first|then|now|so)\b', re.I),
    re.compile(r'^[A-Z][a-z]'),
]
_PROSE_STARTERS = {
    "the", "this", "we", "note", "since", "because", "first", "then",
    "now", "so", "here", "thus", "therefore", "proof", "qed",
}


def clean_tactic_line(line: str) -> str:
    idx = line.find("--")
    if idx >= 0:
        line = line[:idx]
    line = line.rstrip()
    inner = line.strip()
    if inner.startswith("`") and inner.endswith("`") and inner.count("`") == 2:
        line = inner[1:-1]
    return line


def is_lean_tactic_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("·") or stripped.startswith("<;>") or stripped.startswith("|"):
        return True
    if line.startswith("  ") or line.startswith("\t"):
        return True
    first_word = stripped.split()[0].lower().strip("`.,:")
    if first_word in _PROSE_STARTERS:
        return False
    for pat in _PROSE_PATTERNS:
        if pat.search(stripped):
            return False
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Loogle retrieval
# ──────────────────────────────────────────────────────────────────────────────

def extract_loogle_queries(proof_state: str) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []

    for m in re.finditer(r'\b([A-Z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9_]*)+)\b', proof_state):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            results.append(name)

    goal_line = ""
    for line in proof_state.splitlines():
        if "⊢" in line:
            goal_line = line.split("⊢", 1)[1].strip()
            break
    for m in re.finditer(r'\b([a-z][A-Za-z0-9]{3,})\b', goal_line):
        fn = m.group(1)
        for ns in ("List", "Nat", "Finset", "MeasureTheory"):
            candidate = f"{ns}.{fn}"
            if candidate not in seen:
                seen.add(candidate)
                results.append(candidate)

    _LEAN_KEYWORDS = {
        "Type", "Prop", "Sort", "True", "False", "And", "Or", "Not",
        "Iff", "Eq", "Ne", "Nat", "Int", "Real", "Bool", "List",
        "Option", "Prod", "Sum", "Unit", "Empty", "Sigma", "Subtype",
    }
    if not results:
        for m in re.finditer(r':\s*([A-Z][A-Za-z0-9]{3,})\b', proof_state):
            name = m.group(1)
            if name not in seen and name not in _LEAN_KEYWORDS:
                seen.add(name)
                results.append(name)

    return results[:5]


def loogle_query(proof_state: str) -> tuple[list[str], list[str], list[str]]:
    """
    Query Loogle for Mathlib lemmas.
    Returns (lemma_strings, queries_used, raw_names).
    """
    queries = extract_loogle_queries(proof_state)
    if not queries:
        _trace("[LOOGLE] No qualified identifiers found in proof state — skipping")
        return [], [], []

    _trace(f"[LOOGLE] Queries extracted from proof state: {queries}")
    all_lemmas: list[str] = []
    raw_names:  list[str] = []
    seen_names: set[str]  = set()

    for query in queries[:2]:
        try:
            url = f"https://loogle.lean-lang.org/json?q={urllib.parse.quote(query)}"
            _trace(f"[LOOGLE] → GET {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "lean-copilot-gemini/1.0"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            hits = (data.get("hits") or [])[:6]
            _trace(f"[LOOGLE] ← {len(hits)} hits for '{query}':")
            for hit in hits:
                name = hit.get("name", "")
                typ  = hit.get("type", "").strip()
                if name and name not in seen_names:
                    seen_names.add(name)
                    entry = f"{name} : {typ}"
                    all_lemmas.append(entry)
                    raw_names.append(name)
                    _trace(f"         {entry[:100]}")
        except Exception as e:
            _trace(f"[LOOGLE] Query '{query}' failed: {e}")

    _trace(f"[LOOGLE] Total retrieved: {len(all_lemmas)} unique lemmas")
    return all_lemmas[:15], queries, raw_names


# ──────────────────────────────────────────────────────────────────────────────
# Trace / logging helpers  (thread-safe, pretty-printed)
# ──────────────────────────────────────────────────────────────────────────────

_trace_lock = threading.Lock()


def _trace(msg: str) -> None:
    with _trace_lock:
        print(msg, flush=True)


def _banner(title: str, width: int = 70) -> None:
    bar = "─" * width
    _trace(f"\n{bar}")
    _trace(f"  {title}")
    _trace(bar)


def _section(title: str, width: int = 60) -> None:
    _trace(f"\n{'━' * width}")
    _trace(f"  {title}")
    _trace('━' * width)


# ──────────────────────────────────────────────────────────────────────────────
# Gemini API — single call
# ──────────────────────────────────────────────────────────────────────────────

def _call_gemini_api(user_message: str, temperature: float) -> str:
    """Raw Gemini API call. Returns the text response string."""
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 8192,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GEMINI_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    body = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            parts = body["candidates"][0]["content"]["parts"]
            if not any("text" in p and not p.get("thought", False) for p in parts):
                raise KeyError("no non-thought text part")
            break
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(f"Gemini HTTP {e.code}: {err}") from e
        except (KeyError, IndexError):
            _trace(f"[Gemini] Empty response on attempt {attempt + 1}, retrying…")
        except Exception as e:
            raise RuntimeError(f"Gemini error: {e}") from e

    parts = body["candidates"][0]["content"]["parts"]
    text_parts = [p["text"] for p in parts if "text" in p and not p.get("thought", False)]
    if not text_parts:
        raise ValueError("No non-thought text parts found in Gemini response")
    return "\n".join(text_parts).strip()


# ──────────────────────────────────────────────────────────────────────────────
# Parse Gemini text → tactic lines + reasoning
# ──────────────────────────────────────────────────────────────────────────────

def _parse_gemini_text(text: str) -> tuple[list[str], str]:
    """
    Parse [PROOF]…[END] and [REASON]…[END] from Gemini response.
    Returns (proof_lines, reasoning).
    """
    reasoning = ""
    if "[REASON]" in text:
        after_reason = text.split("[REASON]", 1)[1]
        end_idx = after_reason.find("[END]")
        reasoning = after_reason[:end_idx].strip() if end_idx != -1 else after_reason.strip()

    if "[PROOF]" in text:
        proof_section = text.split("[PROOF]", 1)[1].strip()
        for terminator in ["[END]", "[REASONING]"]:
            if terminator in proof_section:
                proof_section = proof_section.split(terminator, 1)[0].strip()
    elif "```" in text:
        parts = text.split("```")
        proof_section = parts[1] if len(parts) >= 2 else parts[0]
    else:
        if "[REASONING]" in text:
            proof_section = text.split("[REASONING]", 1)[1]
        else:
            proof_section = text

    if "```" in proof_section:
        parts = proof_section.split("```")
        proof_section = parts[1] if len(parts) >= 2 else parts[0]
        if "\n" in proof_section:
            first_line, rest = proof_section.split("\n", 1)
            if first_line.strip().isalpha():
                proof_section = rest

    proof_lines = []
    for line in proof_section.splitlines():
        cleaned = clean_tactic_line(line)
        if not cleaned.strip():
            continue
        s = cleaned.strip()
        if s.startswith("[") and s.endswith("]"):
            break
        if not is_lean_tactic_line(cleaned):
            _trace(f"  [filter] dropping: {s!r}")
            continue
        proof_lines.append(cleaned)

    return proof_lines, reasoning


# ──────────────────────────────────────────────────────────────────────────────
# Build the user message for a sketch
# ──────────────────────────────────────────────────────────────────────────────

def _build_user_message(
    proof_state: str,
    defs_block: str,
    final_premises_block: str,
    local_block: str,
    sketch_hint: str,
    single_step: bool,
    prev_attempt: str | None = None,
    lean_error: str = "",
) -> str:
    prev_section = ""
    if prev_attempt:
        prev_section = f"""
[PREVIOUS ATTEMPT — returned sorry or failed]
{prev_attempt}
[INSTRUCTION] The above attempt did NOT work. Try a completely different approach.
"""
    error_section = ""
    if lean_error:
        error_section = f"""
[LEAN ERROR — Lean rejected your previous proof attempt with this error]
{lean_error}
[You MUST fix this specific error. Do NOT repeat the same tactic that caused it.]
"""
    return f"""[PROPOSITION]
{proof_state}

[PROOF STATE]
{proof_state}

[DEFINITIONS — custom types and definitions from this file]
{defs_block}

[VALID PREMISES — relevant Mathlib lemmas (ByT5 + Loogle), use only these names]
{final_premises_block}

[LOCAL THEOREMS — proven earlier in this file, use these by name when applicable]
{local_block}
{error_section}
[SKETCH STRATEGY] {sketch_hint}
{prev_section}
{"[INSTRUCTION] Output EXACTLY ONE tactic line. Do not output a multi-step proof." if single_step else ""}""".strip()


# ──────────────────────────────────────────────────────────────────────────────
# Traceability analysis: did ByT5 / Loogle actually influence Gemini?
# ──────────────────────────────────────────────────────────────────────────────

def _analyse_impact(
    gemini_text: str,
    byt5_names: list[str],
    loogle_names: list[str],
    sketch_id: str,
    log: list[str],
) -> None:
    """Append impact analysis lines to log buffer.
    Uses word-boundary matching so 'a' doesn't match inside every word."""
    def _mentioned(name: str) -> bool:
        return bool(re.search(r'\b' + re.escape(name) + r'\b', gemini_text))

    used_byt5     = [n for n in byt5_names   if _mentioned(n)]
    unused_byt5   = [n for n in byt5_names   if not _mentioned(n)]
    used_loogle   = [n for n in loogle_names if _mentioned(n)]
    unused_loogle = [n for n in loogle_names if not _mentioned(n)]

    log.append(f"\n  [IMPACT ANALYSIS — Sketch {sketch_id}]")
    if byt5_names:
        if used_byt5:
            log.append(f"  ByT5  ✓ USED    : {used_byt5}")
        else:
            log.append(f"  ByT5  ✗ NOT USED (provided {len(byt5_names)} premises, none appeared in output)")
        if unused_byt5:
            log.append(f"  ByT5  ~ ignored : {unused_byt5[:6]}")
    else:
        log.append("  ByT5  : (no premises provided)")

    if loogle_names:
        if used_loogle:
            log.append(f"  Loogle ✓ USED    : {used_loogle}")
        else:
            log.append(f"  Loogle ✗ NOT USED (provided {len(loogle_names)} lemmas, none appeared in output)")
        if unused_loogle:
            log.append(f"  Loogle ~ ignored : {unused_loogle[:6]}")
    else:
        log.append("  Loogle : (no results)")


# ──────────────────────────────────────────────────────────────────────────────
# Run one sketch (initial attempt + optional refinement)
# ──────────────────────────────────────────────────────────────────────────────

def run_sketch(
    sketch: dict,
    proof_state: str,
    local_block: str,
    defs_block: str,
    final_premises_block: str,
    byt5_names: list[str],
    loogle_names: list[str],
    single_step: bool,
    lean_error: str = "",
) -> tuple[str, str, str, str]:
    """
    Run one sketch: initial call, then one refinement if result is sorry.
    lean_error: Lean elaboration error from a previous attempt (empty on first call).
    Buffers all log output and returns it as a string for atomic printing.
    Returns (proof_str, reasoning, display_text, log_output).
    """
    sid   = sketch["id"]
    sname = sketch["name"]
    temp  = sketch["temperature"]
    hint  = sketch["hint"]

    # All output goes here — printed atomically by the caller
    buf: list[str] = []
    W = 60
    buf.append(f"\n{'━' * W}")
    buf.append(f"  SKETCH {sid} — {sname}  (temperature={temp})")
    buf.append('━' * W)

    # ── Initial attempt ──
    if lean_error:
        buf.append(f"\n  [LEAN ERROR CONTEXT — passing to Gemini]\n    {lean_error}")
    user_msg = _build_user_message(
        proof_state, defs_block, final_premises_block, local_block,
        hint, single_step, lean_error=lean_error,
    )
    buf.append(f"\n  [PROMPT TO GEMINI — Sketch {sid}]")
    for line in user_msg.splitlines():
        buf.append(f"    {line}")

    try:
        raw = _call_gemini_api(user_msg, temp)
    except Exception as e:
        buf.append(f"  [Sketch {sid}] API error: {e}")
        return "sorry", str(e), f"Sketch {sid} error: {e}", "\n".join(buf)

    buf.append(f"\n  [GEMINI RAW OUTPUT — Sketch {sid}]")
    for line in raw.splitlines():
        buf.append(f"    {line}")

    proof_lines, reasoning = _parse_gemini_text(raw)
    buf.append(f"\n  [PARSED TACTICS — Sketch {sid}]: {proof_lines}")
    _analyse_impact(raw, byt5_names, loogle_names, sid, buf)

    is_sorry = not proof_lines or (len(proof_lines) == 1 and proof_lines[0].strip() == "sorry")

    # ── Refinement pass (if initial was sorry) ──
    if is_sorry:
        buf.append(f"\n  [Sketch {sid}] Initial result was sorry — running REFINEMENT PASS…")
        prev_attempt = "\n".join(proof_lines) if proof_lines else "sorry"
        user_msg_refined = _build_user_message(
            proof_state, defs_block, final_premises_block, local_block,
            hint, single_step, prev_attempt=prev_attempt,
        )
        buf.append(f"\n  [REFINED PROMPT — Sketch {sid}] (showing new section only)")
        buf.append(f"    [PREVIOUS ATTEMPT] {prev_attempt!r}")
        buf.append("    [INSTRUCTION] Try a completely different approach.")

        try:
            raw2 = _call_gemini_api(user_msg_refined, min(temp + 0.2, 1.0))
        except Exception as e:
            buf.append(f"  [Sketch {sid}] Refinement API error: {e}")
        else:
            buf.append(f"\n  [REFINED GEMINI OUTPUT — Sketch {sid}]")
            for line in raw2.splitlines():
                buf.append(f"    {line}")

            proof_lines2, reasoning2 = _parse_gemini_text(raw2)
            buf.append(f"\n  [REFINED PARSED TACTICS — Sketch {sid}]: {proof_lines2}")
            _analyse_impact(raw2, byt5_names, loogle_names, f"{sid}-refined", buf)

            is_sorry2 = not proof_lines2 or (
                len(proof_lines2) == 1 and proof_lines2[0].strip() == "sorry"
            )
            if not is_sorry2:
                buf.append(f"  [Sketch {sid}] Refinement SUCCEEDED ✓")
                proof_lines = proof_lines2
                reasoning   = reasoning2
                raw         = raw2
            else:
                buf.append(f"  [Sketch {sid}] Refinement also returned sorry ✗")

    proof_str = "\n".join(proof_lines) if proof_lines else "sorry"
    display   = f"=== Sketch {sid} ({sname}, temp={temp}) ===\n{raw}"
    return proof_str, reasoning, display, "\n".join(buf)


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point: 4 sketches in parallel
# ──────────────────────────────────────────────────────────────────────────────

def generate_four_sketches(
    proof_state: str,
    local_lemmas: str,
    local_defs: str,
    retrieved_premises: str,
    single_step: bool,
    lean_error: str = "",
) -> tuple[list[tuple[str, str]], str]:
    """
    Run 4 diverse sketches in parallel, refine sorry results.
    Returns ([(proof, reasoning), ...], full_display_text).
    """
    _banner("GEMINI PROOF SEARCH — 4 SKETCHES + REFINEMENT")
    if lean_error:
        _trace(f"\n[LEAN ERROR FROM PREVIOUS ATTEMPT]\n{lean_error}\n")

    # ── Print proof state ──
    _trace("\n[PROOF STATE]")
    _trace(proof_state)

    # ── ByT5 (from LeanCopilot retriever, already computed in Lean) ──
    _section("RETRIEVAL — ByT5 (LeanCopilot)")
    byt5_block = retrieved_premises.strip() if retrieved_premises.strip() else "(none)"
    byt5_names: list[str] = []
    if byt5_block not in ("(none)", "(unavailable)"):
        # Only keep lines whose prefix before ':' is a valid Lean qualified identifier
        # (e.g. "List.perm_insertionSort"). Rejects continuation lines like "a", "insertionSort r (a"
        _LEAN_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')
        for line in byt5_block.splitlines():
            before_colon = line.split(":")[0].strip()
            if _LEAN_IDENT.match(before_colon) and len(before_colon) > 2:
                byt5_names.append(before_colon)
        _trace(f"  ByT5 provided {len(byt5_names)} valid premises:")
        for entry in byt5_block.splitlines():
            _trace(f"    {entry[:110]}")
    else:
        _trace(f"  ByT5: {byt5_block}")

    # ── Loogle ──
    _section("RETRIEVAL — Loogle (live Mathlib search)")
    try:
        loogle_lemmas, _loogle_queries, loogle_names = loogle_query(proof_state)
    except Exception as e:
        _trace(f"  [LOOGLE] Unexpected error: {e}")
        loogle_lemmas, loogle_names = [], []

    loogle_block = "\n".join(loogle_lemmas) if loogle_lemmas else "(none retrieved)"

    # ── Merge premises ──
    seen_names: set[str] = set()
    merged: list[str] = list(ALWAYS_AVAILABLE)
    for entry in ALWAYS_AVAILABLE:
        seen_names.add(entry.split()[0].strip())
    for line in (byt5_block + "\n" + loogle_block).splitlines():
        name = line.split(":")[0].strip()
        if name and name not in seen_names and name not in ("(none)", "(unavailable)"):
            seen_names.add(name)
            merged.append(line)
    final_premises_block = "\n".join(merged) if merged else "(none)"

    _section("MERGED PREMISES (ALWAYS_AVAILABLE + ByT5 + Loogle)")
    _trace(f"  Total: {len(merged)} entries")
    for entry in merged:
        _trace(f"    {entry[:110]}")

    local_block = local_lemmas.strip() if local_lemmas.strip() else "(none)"
    defs_block  = local_defs.strip()   if local_defs.strip()   else "(none)"

    # ── Run 4 sketches in parallel, buffer their logs ──
    _section("RUNNING 4 SKETCHES IN PARALLEL — logs printed in order below")
    results_by_id: dict[str, tuple[str, str, str, str]] = {}

    def _run(sketch):
        return sketch["id"], run_sketch(
            sketch, proof_state, local_block, defs_block,
            final_premises_block, byt5_names, loogle_names, single_step,
            lean_error=lean_error,
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_run, s): s["id"] for s in SKETCHES}
        for future in as_completed(futures):
            sid, result = future.result()
            results_by_id[sid] = result

    # Print each sketch's buffered log atomically in fixed order (A→B→C→D)
    for sketch in SKETCHES:
        sid = sketch["id"]
        _proof_str, _reasoning, _display, log_output = results_by_id[sid]
        _trace(log_output)

    # ── Summary ──
    _banner("SUMMARY — 4 SKETCHES")
    outputs = []
    display_parts = []
    for sketch in SKETCHES:
        sid = sketch["id"]
        proof_str, reasoning, display, _log = results_by_id[sid]
        is_sorry = proof_str.strip() == "sorry"
        icon = "✗ sorry" if is_sorry else "✓"
        _trace(f"  Sketch {sid} ({sketch['name']:12s}): {icon}  {proof_str[:80].strip()!r}")
        outputs.append((proof_str, reasoning))
        display_parts.append(display)

    non_sorry = [(p, r) for p, r in outputs if p.strip() != "sorry"]
    sorry_only = [(p, r) for p, r in outputs if p.strip() == "sorry"]
    final_outputs = non_sorry + sorry_only  # put good results first
    _trace(f"\n  {len(non_sorry)} non-sorry suggestions, {len(sorry_only)} sorry")

    full_display = "\n\n".join(display_parts)
    return final_outputs, full_display


# ──────────────────────────────────────────────────────────────────────────────
# HTTP handler
# ──────────────────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/generate":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length))

        proof_state        = body.get("input", "")
        local_lemmas       = body.get("localLemmas", "")
        local_defs         = body.get("localDefs", "")
        retrieved_premises = body.get("retrievedPremises", "")
        single_step        = body.get("singleStep", False)
        lean_error         = body.get("leanError", "")

        tactics, display = generate_four_sketches(
            proof_state, local_lemmas, local_defs, retrieved_premises, single_step,
            lean_error=lean_error,
        )

        response = {
            "outputs": [
                {
                    "output":    proof,
                    "score":     round(1.0 - i * 0.05, 2),
                    "reasoning": reasoning,
                }
                for i, (proof, reasoning) in enumerate(tactics)
            ],
            "display": display,
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, format, *args):
        _trace(f"[server] {format % args}")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    server = ThreadingHTTPServer(("localhost", PORT), Handler)
    _trace(f"Gemini bridge server running on http://localhost:{PORT}")
    _trace(f"API key: {'(not set)' if not GEMINI_API_KEY else GEMINI_API_KEY[:10] + '...'}")
    _trace("Mode: 4 sketches (DIRECT/EXPLORATORY/STEP-BY-STEP/AUTOMATION) + refinement")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _trace("\nShutting down.")
        server.server_close()
