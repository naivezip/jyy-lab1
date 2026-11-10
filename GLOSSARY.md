# Personal Agent

A terminal agent that answers a user by running a ReAct loop against a DeepSeek
model and using tools in the user's workspace.

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

**Tool**:
A named capability the model can call, described by a JSON schema and executed
by the agent.
_Avoid_: Function, plugin

**Tool Call**:
The model's structured request to run a tool, made of a tool name and JSON
arguments.
_Avoid_: Function call

**Read Tool**:
The tool that returns numbered lines from a text file in the workspace,
optionally paged by line range.
_Avoid_: Cat, viewer

**Write Tool**:
The tool that creates a new text file in the workspace. It never modifies an
existing file.
_Avoid_: Save, editor

**Edit Tool**:
The tool that replaces a range of lines in an existing text file in the
workspace.
_Avoid_: Patch, modify

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
The directory tree the agent treats as its home for file operations. Paths
outside it are not part of the agent's file domain; commands start here.
_Avoid_: Project root
