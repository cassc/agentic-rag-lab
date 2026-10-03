# Lesson 16 - Frameworks: evaluate, wrap, and migrate

## The idea

Agent frameworks change fast and none of them has won. If your product code
calls a framework everywhere, a framework change is a rewrite. If it calls
**your own small interface**, a framework is one adapter you can swap.

```python
class Runtime(Protocol):
    def run(self, question: str) -> Result: ...     # answer, steps, tokens, trace
```

`lab/runtime.py` (~90 lines) has two adapters behind it:

- `Scratch`: the loop from lesson 6 (`lab/loop.py`).
- `LangGraph`: the same agent as a LangGraph `StateGraph`.

Both use the same model client and the same tool functions, so any
difference in the numbers comes from the runtime.

The LangGraph version, in words: **state** is a dict (`msgs`, `steps`,
`tokens`). **Nodes** are functions that return an update to the state.
**Edges** say which node runs next; a conditional edge decides in code. A
**checkpointer** saves the state after every node.

```
START -> model --(tool calls?)--> tools -> model -> ... -> END
              '--(risky tool)--> approval (pause) -> tools
```

## Run it

```sh
uv run lessons/16_framework/run.py      # A, B, C
```

## Results

**A. Contract tests.** Four things every runtime must do, tested through
the interface only:

| Test | scratch | langgraph |
| --- | --- | --- |
| returns a `Result` with an answer | pass | pass |
| stops at the step limit | pass | pass |
| a tool error does not crash the run | pass | pass |
| the trace names the tools used | pass | pass |

**B. Side by side** (5 multi-hop + 5 single-hop questions, same judge):

| Runtime | Correct | Steps/q | Tokens/q | Seconds/q |
| --- | --- | --- | --- | --- |
| scratch | 10/10 | 2.1 | 3,678 | 4.4 |
| langgraph | 10/10 | 2.1 | 3,957 | 4.5 |

No real difference - as expected. **The framework does not make the model
smarter.** Same model, same tools, same prompts -> same behaviour. (The 8%
token gap is run-to-run noise: both send the same messages.) So choose a
framework for what it gives around the model, not for answer quality.

**C. What the framework gives for free.** With a checkpointer and
`interrupt_before`, 10 lines give human approval:

```
paused before node ('approval',); waiting call: place_order {"symbol": "BTCUSDT", ...}
checkpoints saved so far: 3
resumed: tools run ['place_order']   (6 checkpoints in the thread)
```

The run stopped before the risky tool, the state was saved, and
`invoke(None, thread)` continued it. With a database checkpointer the
resume can happen days later in another process. In lesson 7 I wrote this
by hand (checkpoint + hook); in lesson 9 Temporal gave it through signals.

## What you get, what you pay

| | Own loop | LangGraph |
| --- | --- | --- |
| Lines for this agent | ~40 (`loop.py`) | ~60 (adapter) + the framework |
| Checkpoint, resume, pause for human | write it (lessons 7, 9) | built in |
| Streaming of steps, graph drawing, state history | write it | built in |
| Control over each message and token | full | full here (plain functions as nodes), less with prebuilt agents |
| New dependencies | 0 | `langgraph`, `langchain-core`, and their release cycle |
| Debugging | your code | your code + the framework's (reducers, channels, recursion limit) |
| Durable execution across crashes | Temporal (lesson 9) | checkpointer per node; side effects inside a node can still run twice |

## The frameworks named in the job text, in one line each

| Framework | Core idea | Fits |
| --- | --- | --- |
| LangGraph | explicit graph + shared state + checkpoints | workflows you want to control and resume |
| OpenAI Agents SDK | agents, handoffs, guardrails, built-in tracing | quick handoff-style agents |
| CrewAI | roles and tasks in a "crew" | role-play style pipelines, fast demos |
| AutoGen | agents that talk to each other in a conversation | research, multi-agent chat patterns |
| Semantic Kernel | plugins + planners, strong .NET / enterprise ties | Microsoft stacks |

## How I would evaluate a framework

1. **Write the task down first:** which runs, how long, which failures
   matter (resume? approval? streaming? multi-tenant?).
2. **Port one real agent** behind the interface (this lesson). A hello-world
   tells you nothing.
3. **Run the same evals** on both (lesson 8): quality, tokens, latency,
   variance.
4. **Break it:** kill the process in the middle, make a tool fail, hit the
   step limit, run 100 at once. Read what it does.
5. **Look inside:** can I see and change the exact messages sent to the
   model? Can I plug in my gateway (lesson 10), my tracing (lesson 14), my
   checkpoint store?
6. **Look around it:** release pace and breaking changes, licence, how much
   of it I would have to own if it were dropped tomorrow.

## How I would migrate

1. Put the interface in front of the old runtime. No behaviour change.
2. Write contract tests and the eval set against the interface.
3. Build the new adapter until the tests and evals pass.
4. **Shadow run:** send real traffic to both, serve the old answer, compare
   (for read-only tasks only - side effects must not run twice).
5. Move traffic in steps (1% -> 10% -> 50%) behind a flag, per tenant or
   per task type. Watch the dashboards (lesson 14).
6. In-flight runs finish on the old runtime. Remove it when none are left
   (the same rule as workflow versions, lesson 9).

## Review questions

**Q: Framework or your own loop?**
> The loop itself is ~40 lines; that is not the hard part. The hard parts
> are state, resume, approval, streaming, tracing. Use a framework when it
> gives you those and lets you see every message. Write your own when you
> need full control or the framework hides the prompt. Either way, keep
> product code behind your own interface.

**Q: Why an abstraction layer over agent frameworks?**
> Portability and stability. Frameworks change fast; a thin interface
> (run, result, trace, events) makes a framework one adapter. It also
> gives one place for tracing, budgets and policy. Keep it thin: if it
> grows into its own framework, you have the same problem again.

**Q: What does LangGraph add over a while loop?**
> An explicit state machine: typed state, nodes, edges, and a checkpoint
> after every node. From that you get resume, pause for a human, state
> history ("time travel"), and streaming of steps. In my test it scored
> the same as the loop (10/10 both) - the gain is operations, not quality.

**Q: How do you prove a port is correct?**
> Contract tests on the interface (limits, errors, trace) and the same
> eval set on both sides with several trials. Then a shadow run on real
> traffic. "It answered my test question" is not proof.

**Q: What are the risks of depending on a framework?**
> Breaking changes, hidden prompts and retries, hidden token cost, hard
> debugging through layers, and lock-in of your state format (checkpoints
> written by one version must be readable by the next).
