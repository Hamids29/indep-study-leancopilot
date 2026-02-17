import Lean
import LeanCopilot

open Lean Meta Elab Term Tactic

namespace LeanCopilotTest

/--
Pretty-print the current tactic state (mirrors LeanCopilot.getPpTacticState).
-/
private def getPpState : TacticM String := do
  let goals ← getUnsolvedGoals
  match goals with
  | []    => return "no goals"
  | [g]   => return (← Meta.ppGoal g).pretty
  | goals =>
    return (← goals.foldlM (init := "")
      (fun a b => do return s!"{a}\n\n{(← Meta.ppGoal b).pretty}")).trim

/--
Call the Gemini bridge server and return raw response text.
-/
private def callGeminiServer (proofState : String) : IO String := do
  let req := Lean.Json.mkObj [
    ("name", "gemini"),
    ("input", proofState),
    ("prefix", "")
  ]
  let reqStr := req.pretty 99999999999999999
  let out ← IO.Process.output {
    cmd := "curl"
    args := #["-s", "-X", "POST",
              "http://localhost:23338/generate",
              "-H", "accept: application/json",
              "-H", "Content-Type: application/json",
              "-d", reqStr]
  }
  if out.exitCode != 0 then
    throw $ IO.userError "Gemini server request failed. Is the server running on port 23338?"
  return out.stdout

/--
Parse the server response into an array of tactic strings.
Expected format: {"outputs": [{"output": "tactic", "score": 1.0}, ...]}
-/
private def parseResponse (resp : String) : IO (Array String) := do
  let some json := Lean.Json.parse resp |>.toOption
    | throw $ IO.userError s!"Failed to parse JSON response: {resp}"
  let some outputs := json.getObjVal? "outputs" |>.toOption
    | throw $ IO.userError s!"No 'outputs' field in response: {resp}"
  let some arr := outputs.getArr? |>.toOption
    | throw $ IO.userError s!"'outputs' is not an array: {resp}"
  let mut tactics : Array String := #[]
  for item in arr do
    if let some output := item.getObjVal? "output" |>.toOption then
      if let some tactic := output.getStr? |>.toOption then
        tactics := tactics.push tactic
  return tactics

-- Syntax declaration
syntax "call_gemini" : tactic

-- Elaboration rule
elab_rules : tactic
  | `(tactic | call_gemini) => do
    let state ← getPpState
    let resp ← callGeminiServer state
    let tactics ← parseResponse resp
    if tactics.isEmpty then
      logWarning "Gemini returned no suggestions."
    else
      let mut msg := "Gemini suggests:\n"
      for tactic in tactics do
        msg := msg ++ s!"  Try this: {tactic}\n"
      logInfo msg

end LeanCopilotTest
