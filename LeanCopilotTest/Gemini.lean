import Lean
import LeanCopilot
import Lean.Meta.Tactic.TryThis

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
Parse the server response into an array of (proof, reasoning) pairs.
Expected format: {"outputs": [{"output": "proof", "score": 1.0, "reasoning": "..."}, ...]}
-/
private def parseResponse (resp : String) : IO (Array (String × String)) := do
  let some json := Lean.Json.parse resp |>.toOption
    | throw $ IO.userError s!"Failed to parse JSON response: {resp}"
  let some outputs := json.getObjVal? "outputs" |>.toOption
    | throw $ IO.userError s!"No 'outputs' field in response: {resp}"
  let some arr := outputs.getArr? |>.toOption
    | throw $ IO.userError s!"'outputs' is not an array: {resp}"
  let mut results : Array (String × String) := #[]
  for item in arr do
    if let some output := item.getObjVal? "output" |>.toOption then
      if let some proof := output.getStr? |>.toOption then
        let reasoning := item.getObjVal? "reasoning" |>.toOption
          |>.bind (·.getStr? |>.toOption) |>.getD ""
        results := results.push (proof, reasoning)
  return results

-- Syntax declaration
syntax "call_gemini" : tactic

-- Elaboration rule
open Lean.Meta.Tactic.TryThis in
elab_rules : tactic
  | `(tactic | call_gemini) => do
    let state ← getPpState
    let resp ← callGeminiServer state
    let results ← parseResponse resp
    if results.isEmpty then
      logWarning "Gemini returned no suggestions."
    else
      let suggestions : Array Suggestion := results.map fun (proof, reasoning) =>
        { suggestion := SuggestionText.string proof,
          postInfo? := if reasoning.isEmpty then none else some s!"\n-- {reasoning}" }
      addSuggestions (← getRef) suggestions

end LeanCopilotTest
