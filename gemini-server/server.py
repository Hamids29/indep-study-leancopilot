"""
Gemini API bridge server for LeanCopilot.

Receives proof state from Lean, sends it to Google Gemini,
and returns tactic suggestions in LeanCopilot's expected format.

Usage:
    export GEMINI_API_KEY="your-key-here"
    python server.py
"""

import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv("../.env")

PORT = 23338
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

SYSTEM_PROMPT = """You are an expert Lean 4 theorem prover.
Given a proof state, you MUST respond with exactly two sections: [REASONING] then [PROOF].

MANDATORY FORMAT:

[REASONING]
<one or two sentences max explaining which tactic you chose and why>
[PROOF]
<tactic 1>
<tactic 2>
...

If you cannot prove the goal, you MUST still write:
[PROOF]
sorry

A response with no [PROOF] block is INVALID. Always include [PROOF].

STRICT RULES FOR [PROOF]:
- Every line must be a bare Lean 4 tactic — no comments, no English, no explanations.
- Do NOT write `--` comments inside [PROOF].
- Do NOT write `by` as a standalone word.
- Output at most 6 tactic lines.

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
[REASONING]
n > 5 implies n > 3 by linear arithmetic.
[PROOF]
linarith

EXAMPLE 2 — case split:
[REASONING]
Split on even/odd then close with omega.
[PROOF]
rcases Nat.even_or_odd n with ⟨k, hk⟩ | ⟨k, hk⟩
· left; omega
· right; omega

EXAMPLE 3 — exact lemma:
[REASONING]
This is list append associativity.
[PROOF]
exact List.append_assoc l1 l2 l3

EXAMPLE 4 — induction:
[REASONING]
Prove by induction on n. Base case is trivial; inductive step uses the range sum lemma.
[PROOF]
induction n with
| zero => simp
| succ n ih =>
  simp [List.sum_range_succ]
  omega

EXAMPLE 5 — case split with rcases:
[REASONING]
Split on even/odd, then close each subgoal with omega.
[PROOF]
rcases Nat.even_or_odd n with ⟨k, hk⟩ | ⟨k, hk⟩
· left; omega
· right; omega

EXAMPLE — ceiling log half:
[PROOF]
exact Nat.clog_monotone (Nat.div_le_self _ _) |>.trans (Nat.clog_of_one_lt Nat.one_lt_two h)


EXAMPLE 6 — chained have statements:
[REASONING]
Build intermediate facts then combine.
[PROOF]
have h1 : clog 2 (n / 2) ≤ clog 2 n - 1 := Nat.clog_of_one_lt one_lt_two hn
have h2 : n / 2 + (n + 1) / 2 = n := by omega
nlinarith [h1, h2]

EXAMPLE 7 — cannot prove:
[REASONING]
This goal is too hard to close automatically.
[PROOF]
sorry"""


# Allowlist of words that can legitimately start a Lean 4 tactic.
# Anything NOT starting with one of these (or `·`, `<;>`) is treated as prose.
_TACTIC_STARTERS = {
    "omega", "ring", "ring_nf", "simp", "simp_all", "simp_rw",
    "linarith", "nlinarith", "norm_num", "norm_cast",
    "decide", "native_decide",
    "rfl", "trivial", "assumption", "contradiction", "exfalso",
    "exact", "apply", "refine", "intro", "intros", "revert",
    "constructor", "left", "right", "use", "exists",
    "cases", "rcases", "obtain", "induction", "fun_induction",
    "have", "let", "show", "suffices", "calc",
    "rw", "rewrite", "ext", "funext",
    "push_neg", "push_cast", "field_simp",
    "gcongr", "positivity", "aesop", "tauto",
    "fin_cases", "interval_cases", "linear_combination",
    "abel", "group", "ring_nf", "norm_cast", "mod_cast",
    "ac_rfl", "congr", "unfold", "change", "convert",
    "sorry", "admit",
    # common Mathlib tactics
    "by_contra", "by_cases", "contrapose", "absurd",
    "split", "split_ifs", "if_pos", "if_neg",
}


def clean_tactic_line(line: str) -> str:
    """Strip inline -- comments and markdown formatting; preserve leading whitespace."""
    # Remove inline -- comment
    idx = line.find("--")
    if idx >= 0:
        line = line[:idx]
    line = line.rstrip()
    # Strip surrounding backticks Gemini sometimes wraps single tactics in, e.g. `ring`
    inner = line.strip()
    if inner.startswith("`") and inner.endswith("`") and inner.count("`") == 2:
        line = inner[1:-1]
    return line


def is_lean_tactic_line(line: str) -> bool:
    """Return True only if the line starts with a known Lean 4 tactic keyword."""
    stripped = line.strip()
    if not stripped:
        return False
    # Focused subgoal bullets and tactic combinators are valid
    if stripped.startswith("·") or stripped.startswith("<;>") or stripped.startswith("@"):
        return True
    # Allow continuation lines for structured tactics (indented under induction/cases/calc)
    if line.startswith("  ") or line.startswith("\t"):
        # Indented lines are assumed to be tactic continuations
        return True
    first_word = stripped.split()[0].strip("`").rstrip("!?")
    return first_word in _TACTIC_STARTERS


def call_gemini(proof_state: str) -> tuple[list[str], str]:
    """Call Gemini API with the proof state and return (tactic suggestions, full display text)."""
    user_message = f"""[PROPOSITION]
{proof_state}

[CURRENT CODE]


[PROOF STATE]
{proof_state}

[DEFINITIONS]


[PROVEN THEOREMS/LEMMAS]
"""

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_message}],
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048,
        },

    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GEMINI_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # Retry up to 3 times — Gemini 2.5 Flash sometimes returns empty parts on first attempt
    body = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            # Check if we got actual text content before accepting
            _ = body["candidates"][0]["content"]["parts"][0]["text"]
            break  # success
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            print(f"Gemini API error {e.code}: {error_body}")
            return [("sorry", "error contacting Gemini")], user_message.rstrip() + "\n\n[REASONING]\n(error contacting Gemini)"
        except (KeyError, IndexError):
            print(f"[retry] Empty response on attempt {attempt + 1}, retrying...")
        except Exception as e:
            print(f"Error calling Gemini: {e}")
            return [("sorry", "error contacting Gemini")], user_message.rstrip() + "\n\n[REASONING]\n(error contacting Gemini)"

    # Extract text from Gemini response
    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as e:
        print(f"[parse] Failed to extract text after retries: {e}")
        return [("sorry", "failed to parse Gemini response")], user_message.rstrip() + "\n\n[REASONING]\n(failed to parse Gemini response)"

    print(f"=== Raw Gemini response ===\n{text}\n===========================")

    full_display = user_message.rstrip() + "\n\n" + text

    try:
        # Extract reasoning (between [REASONING] and [PROOF])
        reasoning = ""
        if "[REASONING]" in text:
            after_reasoning = text.split("[REASONING]", 1)[1]
            reasoning_end = after_reasoning.find("[PROOF]")
            reasoning = after_reasoning[:reasoning_end].strip() if reasoning_end != -1 else after_reasoning.strip()

        # Only trust the [PROOF] section
        if "[PROOF]" not in text:
            print("[parse] No [PROOF] section — returning sorry")
            return [("sorry", "no [PROOF] section in response")], full_display

        proof_section = text.split("[PROOF]", 1)[1].strip()

        # Strip markdown code fences if present
        if "```" in proof_section:
            parts = proof_section.split("```")
            proof_section = parts[1] if len(parts) >= 2 else parts[0]
            if "\n" in proof_section:
                first_line, rest = proof_section.split("\n", 1)
                if first_line.strip().isalpha():
                    proof_section = rest

        # Collect proof lines:
        #   1. clean_tactic_line strips inline -- comments, keeps leading whitespace
        #   2. is_lean_tactic_line runs on the CLEANED line (so first-word check sees no comment)
        proof_lines = []
        for line in proof_section.splitlines():
            cleaned = clean_tactic_line(line)   # strip comment, keep indent
            if not cleaned.strip():             # skip blank / comment-only lines
                continue
            if cleaned.strip().startswith("[") and cleaned.strip().endswith("]"):
                break
            if not is_lean_tactic_line(cleaned):
                print(f"[filter] dropping: {cleaned.strip()!r}")
                continue
            proof_lines.append(cleaned)

        print(f"[parse] Extracted proof lines: {proof_lines}")

        if proof_lines:
            proof = "\n".join(proof_lines)
            return [(proof, reasoning)], full_display

    except Exception as e:
        print(f"[parse] Exception during proof extraction: {e}")
        print(f"[parse] text was:\n{text}")

    return [("sorry", "failed to parse Gemini response")], full_display


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/generate":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length))

        proof_state = body.get("input", "")
        print(f"\n--- Proof state ---\n{proof_state}\n-------------------")

        tactics, display = call_gemini(proof_state)
        print(f"Suggestions: {tactics}")

        # Return in LeanCopilot ExternalGenerator format, plus full display text
        response = {
            "outputs": [
                {"output": proof, "score": round(1.0 - i * 0.1, 2), "reasoning": reasoning}
                for i, (proof, reasoning) in enumerate(tactics)
            ],
            "display": display,
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, format, *args):
        print(f"[server] {format % args}")


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), Handler)
    print(f"Gemini bridge server running on http://localhost:{PORT}")
    print(f"API key: {GEMINI_API_KEY[:10]}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
