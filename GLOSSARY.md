# Personal Agent

A terminal agent that answers a user by running a ReAct loop against a DeepSeek
model and executing bash commands in the user's working directory.

## Language

**Agent**:
The CLI program that owns the conversation and runs the ReAct loop. It is not
the model.
_Avoid_: Assistant, bot

**Turn**:
One user input together with everything the agent does until it produces a final
answer for that input.
_Avoid_: Request, exchange

**Step**:
One model API call plus any tool calls it requests and the observations returned
for them. A turn contains one or more steps.
_Avoid_: Iteration, round

**ReAct Loop**:
The control loop that repeats steps until the model requests no tool calls or the
step limit is reached.
_Avoid_: Agent loop

**Tool Call**:
The model's structured request to run a tool, made of a tool name and JSON
arguments.
_Avoid_: Function call

**Observation**:
The output of a tool call, returned to the model as the content of a tool message.
_Avoid_: Tool result, output

**Reasoning**:
The model's streamed `reasoning_content` for a step, shown to the user but kept
separate from the final answer.
_Avoid_: Thinking, chain of thought

**Conversation**:
The in-memory message history of the current CLI process. It ends when the
process exits.
_Avoid_: Session (implies persistence)

**Workspace**:
The current working directory in which bash commands run.
_Avoid_: Project root
