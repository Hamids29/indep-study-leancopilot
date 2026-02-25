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
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

SYSTEM_PROMPT = """You are an expert at proving theorems in Lean 4.
You will be given a proof state (hypotheses and goal) in a user message.
Write your reasoning in a section called [REASONING], then write a [PROOF] section containing only valid Lean 4 tactic lines.
Rules:
- Use only Lean 4 tactic syntax (e.g. simp, ring, omega, exact, rfl, linarith, induction, cases, apply, intro, constructor).
- Do NOT use Coq syntax (no 'reflexivity', 'simpl', 'auto', 'destruct', bullet '-').
- Do NOT write 'by', 'Proof.', 'Qed.', or any Lean declaration syntax.
- Each line in [PROOF] should be a single tactic that can be placed inside a 'by' block.
- Output at most 5 tactics."""


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
            "maxOutputTokens": 1024,
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GEMINI_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"Gemini API error {e.code}: {error_body}")
        return [("sorry", "error contacting Gemini")], user_message.rstrip() + "\n\n[REASONING]\n(error contacting Gemini)"
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return [("sorry", "error contacting Gemini")], user_message.rstrip() + "\n\n[REASONING]\n(error contacting Gemini)"

    # Extract text from Gemini response
    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"Raw Gemini response:\n{text}")

        # Build full display: structured prompt + Gemini's full response
        full_display = user_message.rstrip() + "\n\n" + text

        # Extract reasoning from [REASONING] section
        reasoning = ""
        if "[REASONING]" in text:
            after_reasoning = text.split("[REASONING]", 1)[1]
            reasoning_end = after_reasoning.find("[PROOF]")
            if reasoning_end != -1:
                reasoning = after_reasoning[:reasoning_end].strip()
            else:
                reasoning = after_reasoning.strip()

        # Extract proof lines from [PROOF] section
        if "[PROOF]" in text:
            proof_section = text.split("[PROOF]", 1)[1].strip()
        elif "[REASONING]" in text:
            proof_section = text.split("[REASONING]", 1)[1].strip()
        else:
            proof_section = text

        # Strip markdown code fences if present
        if "```" in proof_section:
            parts = proof_section.split("```")
            proof_section = parts[1] if len(parts) >= 2 else parts[0]
            if "\n" in proof_section:
                first_line, rest = proof_section.split("\n", 1)
                if first_line.strip().isalpha():
                    proof_section = rest

        # Collect proof lines, stop at next section header
        proof_lines = []
        for line in proof_section.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                break
            proof_lines.append(stripped)

        if proof_lines:
            # Return the whole proof as ONE suggestion, reasoning as separate field
            proof = "\n".join(proof_lines)
            return [(proof, reasoning)], full_display
    except (KeyError, IndexError) as e:
        print(f"Failed to parse Gemini response: {e}")
        print(f"Raw response: {body}")

    return [("sorry", "failed to parse Gemini response")], user_message.rstrip() + "\n\n[REASONING]\n(failed to parse Gemini response)"


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
