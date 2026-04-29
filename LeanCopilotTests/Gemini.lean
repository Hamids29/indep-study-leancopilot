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
      (fun a b => do return s!"{a}\n\n{(← Meta.ppGoal b).pretty}")).trimAscii.toString

/--
Collect names and pretty-printed types of theorems proven so far in the current file.
Uses `env.constants.map₂` which holds only declarations from the file being elaborated.
-/
private def getLocalLemmas : TacticM String := do
  let env ← getEnv
  let mut lines : Array String := #[]
  for (name, ci) in env.constants.map₂ do
    if let .thmInfo ti := ci then
      let nameStr := name.toString
      if nameStr.startsWith "_" then continue
      let typeStr ← Meta.ppExpr ti.type
      lines := lines.push s!"{nameStr} : {typeStr.pretty}"
  if lines.isEmpty then return "(none)"
  return "\n".intercalate lines.toList

/--
Collect definitions (defnInfo) from the current file's environment.
-/
private def getLocalDefs : TacticM String := do
  let env ← getEnv
  let mut lines : Array String := #[]
  for (name, ci) in env.constants.map₂ do
    if let .defnInfo di := ci then
      let nameStr := name.toString
      if nameStr.startsWith "_" then continue
      let typeStr ← Meta.ppExpr di.type
      lines := lines.push s!"{nameStr} : {typeStr.pretty}"
  if lines.isEmpty then return "(none)"
  return "\n".intercalate lines.toList

/--
Retrieve relevant Mathlib premises using LeanCopilot's ByT5 retriever.
Falls back to "(unavailable)" if embeddings are not initialized.
-/
private def getRetrievedPremises (state : String) : TacticM String := do
  logInfo s!"[ByT5 INPUT]\n{state}"
  try
    let premises ← LeanCopilot.retrieve state
    let mut lines : Array String := #[]
    for pi in premises do
      try
        let info ← getConstInfo pi.name.toName
        let typeStr ← Meta.ppExpr info.type
        lines := lines.push s!"{pi.name} : {typeStr.pretty}"
      catch _ =>
        lines := lines.push pi.name
    if lines.isEmpty then return "(none)"
    let result := "\n".intercalate lines.toList
    logInfo s!"[ByT5 OUTPUT — {lines.size} premises]\n{result}"
    return result
  catch _ =>
    return "(unavailable)"

/--
Call the Gemini bridge server and return raw response text.
Set `singleStep := true` to request exactly one tactic (used by call_gemini_auto).
-/
private def callGeminiServer (proofState : String) (localLemmas : String)
    (localDefs : String) (retrievedPremises : String) (singleStep : Bool := false)
    (leanError : String := "") : IO String := do
  let req := Lean.Json.mkObj [
    ("name", "gemini"),
    ("input", proofState),
    ("prefix", ""),
    ("localLemmas", localLemmas),
    ("localDefs", localDefs),
    ("retrievedPremises", retrievedPremises),
    ("singleStep", singleStep),
    ("leanError", leanError)
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

-- Internal tactic (core implementation)
syntax "call_gemini_core" : tactic

-- Public term-mode macro: `call_gemini` after `:=` expands to `by call_gemini_core`
macro "call_gemini" : term => `(by call_gemini_core)

-- Public tactic-mode macro: `call_gemini` inside a `by` block
macro "call_gemini" : tactic => `(tactic| call_gemini_core)

-- Elaboration rule
open Lean.Meta.Tactic.TryThis in
elab_rules : tactic
  | `(tactic | call_gemini_core) => do
    let state ← getPpState
    -- Nothing to prove
    if state == "no goals" then
      addSuggestions (← getRef)
        #[{ suggestion := SuggestionText.string "sorry", postInfo? := some "-- no goals" }]
      return
    -- Try to reach Gemini; fall back to sorry on any error
    let suggestions : Array Suggestion ←
      try
        let localLemmas ← getLocalLemmas
        let localDefs ← getLocalDefs
        let retrievedPremises ← getRetrievedPremises state
        let resp ← callGeminiServer state localLemmas localDefs retrievedPremises
        let results ← parseResponse resp
        if results.isEmpty then
          pure #[{ suggestion := SuggestionText.string "sorry",
                   postInfo? := some "-- Gemini returned no suggestions" }]
        else
          -- Show reasoning in the infoview for the first result
          let firstReasoning := results[0]!.2
          if !firstReasoning.isEmpty then
            logInfo s!"Gemini reasoning:\n{firstReasoning}"
          pure (results.map fun (proof, reasoning) =>
            { suggestion := SuggestionText.string proof,
              postInfo? := if reasoning.isEmpty then none
                           else some s!" -- {reasoning}" })
      catch e =>
        let msg ← e.toMessageData.toString
        logWarning s!"call_gemini: {msg}"
        pure #[{ suggestion := SuggestionText.string "sorry",
                 postInfo? := some s!"-- error: {msg}" }]
    addSuggestions (← getRef) suggestions

/--
Iterative tactic: calls Gemini one step at a time, applies each tactic,
checks the resulting goal state, and repeats until solved or maxSteps is reached.
-/
syntax "call_gemini_auto" : tactic

elab_rules : tactic
  | `(tactic | call_gemini_auto) => do
    let maxSteps := 10
    for step in List.range maxSteps do
      let goals ← getUnsolvedGoals
      if goals.isEmpty then break
      let state ← getPpState
      let localLemmas ← getLocalLemmas
      let localDefs    ← getLocalDefs
      let retrieved    ← getRetrievedPremises state
      -- Request a single tactic from the server
      let resp ← callGeminiServer state localLemmas localDefs retrieved true
      let results ← parseResponse resp
      if results.isEmpty then
        logWarning "call_gemini_auto: no suggestion returned"
        break
      let (tacticStr, reasoning) := results[0]!
      let reasoningNote := if reasoning.isEmpty then "" else s!" — {reasoning}"
      logInfo s!"[step {step + 1}] {tacticStr}{reasoningNote}"
      -- Parse tactic string into syntax
      match Lean.Parser.runParserCategory (← getEnv) `tactic tacticStr with
      | .error msg =>
        logWarning s!"call_gemini_auto: parse error: {msg}"
        break
      | .ok stx =>
        -- Try applying; restore state on failure and stop
        let saved ← saveState
        try
          evalTactic stx
        catch e =>
          restoreState saved
          logWarning s!"call_gemini_auto: step {step + 1} failed: {← e.toMessageData.toString}"
          break
    -- Report if goals remain
    if !(← getUnsolvedGoals).isEmpty then
      logWarning "call_gemini_auto: could not fully solve the goal"

/--
Recursive tactic: calls Gemini, tries to apply the proof, and if Lean rejects it
feeds the exact error message back to Gemini and tries again.
Repeats up to maxRounds times. Each round Gemini sees what it tried and why it failed.
-/
syntax "call_gemini_recursive" : tactic

elab_rules : tactic
  | `(tactic | call_gemini_recursive) => do
    let maxRounds := 5
    let mut leanError : String := ""
    for round in List.range maxRounds do
      if (← getUnsolvedGoals).isEmpty then break
      let state      ← getPpState
      let localLemmas ← getLocalLemmas
      let localDefs   ← getLocalDefs
      let retrieved   ← getRetrievedPremises state
      -- Log what we are sending to Gemini this round
      if leanError.isEmpty then
        logInfo s!"[recursive round {round + 1}] Calling Gemini…"
      else
        logInfo s!"[recursive round {round + 1}] Retrying with Lean error:\n{leanError}"
      -- Call server, passing back the Lean error from the previous round (empty on first call)
      let resp ← callGeminiServer state localLemmas localDefs retrieved false leanError
      let results ← parseResponse resp
      if results.isEmpty then
        logWarning s!"[recursive round {round + 1}] No suggestion returned — stopping"
        break
      -- Use the first non-sorry suggestion
      let (tacticStr, reasoning) := results[0]!
      logInfo s!"[recursive round {round + 1}] Gemini suggests:\n{tacticStr}"
      if !reasoning.isEmpty then
        logInfo s!"[recursive round {round + 1}] Reasoning: {reasoning}"
      -- Apply each line of the proof in sequence, collecting the first error
      let lines := tacticStr.splitOn "\n" |>.filter (·.trimAscii.toString.length > 0)
      let mut errorThisRound : String := ""
      for line in lines do
        if (← getUnsolvedGoals).isEmpty then break
        match Lean.Parser.runParserCategory (← getEnv) `tactic line with
        | .error msg =>
          errorThisRound := s!"Parse error on `{line}`: {msg}"
          logWarning s!"[recursive round {round + 1}] {errorThisRound}"
          break
        | .ok stx =>
          let saved ← saveState
          try
            evalTactic stx
          catch e =>
            restoreState saved
            errorThisRound := s!"Tactic `{line}` failed: {← e.toMessageData.toString}"
            logWarning s!"[recursive round {round + 1}] {errorThisRound}"
            break
      if errorThisRound.isEmpty then
        -- All lines applied without error
        if (← getUnsolvedGoals).isEmpty then
          logInfo s!"[recursive round {round + 1}] SOLVED ✓"
        -- else goals remain, next round will call Gemini fresh on new state
        leanError := ""
      else
        -- Pass this error to Gemini on the next round
        leanError := errorThisRound
    if !(← getUnsolvedGoals).isEmpty then
      logWarning "call_gemini_recursive: could not fully solve the goal"

end LeanCopilotTest
