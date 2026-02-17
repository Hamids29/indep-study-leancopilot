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

SYSTEM_PROMPT = """You are a Lean 4 proof assistant. Given a tactic state (proof goal), suggest tactics that could make progress or solve the goal.

Rules:
- Return ONLY a JSON array of tactic strings, nothing else.
- Each tactic should be a valid Lean 4 tactic.
- Suggest 1 to 5 tactics, ordered by likelihood of being correct.
- Do NOT include markdown formatting, code blocks, or explanations.

Example output:
["simp", "omega", "ring"]
"""


def call_gemini(proof_state: str) -> list[str]:
    """Call Gemini API with the proof state and return tactic suggestions."""
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{SYSTEM_PROMPT}\n\nTactic state:\n{proof_state}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 256,
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
        return ["sorry"]
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return ["sorry"]

    # Extract text from Gemini response
    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3].strip()
        tactics = json.loads(text)
        if isinstance(tactics, list):
            return [str(t) for t in tactics]
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Failed to parse Gemini response: {e}")
        print(f"Raw response text: {body}")

    return ["sorry"]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/generate":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length))

        proof_state = body.get("input", "")
        print(f"\n--- Proof state ---\n{proof_state}\n-------------------")

        tactics = call_gemini(proof_state)
        print(f"Suggestions: {tactics}")

        # Return in LeanCopilot ExternalGenerator format
        response = {
            "outputs": [
                {"output": tactic, "score": round(1.0 - i * 0.1, 2)}
                for i, tactic in enumerate(tactics)
            ]
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
