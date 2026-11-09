---------------------------- MODULE AgentLoop ----------------------------
(***************************************************************************)
(* A bounded model of the ReAct turn loop in                                 *)
(* src/personal_agent/agent.py.                                              *)
(*                                                                           *)
(* The model abstracts one model step as a sequence of distinct tool-call    *)
(* ids, which is the shape the OpenAI-compatible API returns.                *)
(*                                                                           *)
(* `ModelResponds` is Agent.run: stream one step and append the assistant    *)
(* message. `RunTool` is Agent.run's per-call loop plus Agent._run_tool:      *)
(* append exactly one tool observation for the current call. `StepLimit` is  *)
(* Agent.run's final Notice after max_steps. BashTool.run returns exactly    *)
(* one observation and never raises, so one RunTool step is one tool         *)
(* message in the real history.                                              *)
(***************************************************************************)

EXTENDS Naturals, Sequences, TLC

CONSTANTS
    MaxSteps,
    MaxCalls,
    CallIds

AllResponses == UNION { [1..n -> CallIds] : n \in 0..MaxCalls }
Responses == { response \in AllResponses :
                 \A i, j \in 1..Len(response) : i # j => response[i] # response[j] }

VARIABLES
    step,      \* number of assistant messages appended so far
    history,   \* messages appended during this turn
    pending,   \* tool-call ids of the current assistant message not yet answered
    phase      \* "model", "tools", "done", or "limit"

vars == <<step, history, pending, phase>>

Init ==
    /\ step = 0
    /\ history = <<>>
    /\ pending = <<>>
    /\ phase = "model"

ModelResponds(response) ==
    /\ phase = "model"
    /\ step < MaxSteps
    /\ history' = Append(history, [kind |-> "assistant", ids |-> response])
    /\ pending' = response
    /\ step' = step + 1
    /\ phase' = IF Len(response) = 0 THEN "done" ELSE "tools"

RunTool ==
    /\ phase = "tools"
    /\ Len(pending) > 0
    /\ history' = Append(history, [kind |-> "tool", id |-> Head(pending)])
    /\ pending' = Tail(pending)
    /\ step' = step
    /\ phase' = IF Len(Tail(pending)) = 0 THEN "model" ELSE "tools"

StepLimit ==
    /\ phase = "model"
    /\ step = MaxSteps
    /\ UNCHANGED <<step, history, pending>>
    /\ phase' = "limit"

Terminal ==
    /\ phase \in {"done", "limit"}
    /\ UNCHANGED vars

Next ==
    \/ \E response \in Responses : ModelResponds(response)
    \/ RunTool
    \/ StepLimit
    \/ Terminal

Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

(***************************************************************************)
(* Every assistant message with n tool calls is followed by exactly n        *)
(* tool messages, in call order, before the next assistant message. No       *)
(* tool message can appear without such an assistant message.                *)
(***************************************************************************)
RECURSIVE WellFormedFrom(_, _)
WellFormedFrom(h, j) ==
    IF j > Len(h) THEN TRUE
    ELSE
        LET m == h[j]
        IN IF m.kind = "assistant"
           THEN
               LET n == Len(m.ids)
               IN /\ j + n <= Len(h)
                  /\ \A k \in 1..n : h[j + k] = [kind |-> "tool", id |-> m.ids[k]]
                  /\ (j + n + 1 > Len(h) \/ h[j + n + 1].kind = "assistant")
                  /\ WellFormedFrom(h, j + n + 1)
           ELSE FALSE

(* The history only has to be well formed when it is handed to stream_step. *)
ApiHistoryWellFormed ==
    phase \in {"model", "done", "limit"} => WellFormedFrom(history, 1)

BoundedSteps == step <= MaxSteps

EventuallyTerminal == <> (phase \in {"done", "limit"})

=============================================================================
