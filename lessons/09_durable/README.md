# Lesson 9 - Durable execution: event log, replay, retries, idempotency

## The idea

An agent run is long (minutes), costs money at every step, and calls things
that fail. The process running it **will** die some day: deploy, out of
memory, node loss. Durable execution means: the run survives the process.

Lesson 7 saved the **state** (the message list) after every step. A workflow
engine saves the **history** instead:

1. All side effects (LLM calls, tool calls) go through `ctx.step(name, fn)`.
2. Each finished step is appended to a log: `{"step": name, "result": ...}`.
3. After a crash, run the **same function again**. Finished steps return the
   logged result and do not run (`replay`). Real work starts at the first
   step with no result.

`lab/durable.py` is this engine in ~70 lines. Three rules follow from it:

| Rule | Why |
| --- | --- |
| Workflow code must be **deterministic** | Replay must ask for the same steps in the same order. No `random`, no clock, no I/O outside a step |
| Steps are **at-least-once** | A crash after the effect but before the log write runs the step again. Side effects need an **idempotency key** |
| Step results must be **serializable and small** | They live in the log forever and are read on every replay |

## Run it

```sh
uv run lessons/09_durable/run.py          # from scratch, scenarios A-D
uv run lessons/09_durable/run.py C        # just one
uv run lessons/09_durable/temporal_run.py --dev-server   # the same on Temporal
```

`--dev-server` lets the Temporal SDK download its dev server binary and start
it on `127.0.0.1` (in memory, random port). To use your own server, set
`TEMPORAL_ADDRESS=localhost:7233` instead.

## Results

Workflow: `plan` (LLM) -> `search:0`, `search:1` (tool) -> `answer` (LLM).

**A. Crash and replay.**

| Run | Steps run | Steps replayed | LLM calls | Searches |
| --- | --- | --- | --- | --- |
| 1 (crash after `search:0`) | 2 | 0 | 1 | 1 |
| 2 (same run id) | 2 | 2 | +1 | +1 |
| 3 (already finished) | 0 | 4 | +0 | +0 |

Total: 2 LLM calls and 2 searches, the same as a run with no crash. Run 3
shows a free side effect of the design: a finished workflow is **idempotent
as a whole**. Calling it again returns the same answer and costs nothing.

**B. Retries.** A tool that times out twice: with `retries=1` the workflow
fails; with `retries=3` and exponential backoff it works on attempt 3. The
retry lives in the engine, not in every tool.

**C. Idempotency.** The process dies after the order reached the exchange but
before the log write. On replay the step runs again.

| Idempotency key | Orders on the exchange |
| --- | --- |
| no | **2** |
| yes (`run_id:position:name`) | 1 |

No engine can give "exactly once" for an outside system. It gives
at-least-once plus a stable key. The outside system must remember the key.

**D. Determinism.** New code that asks for `search:0` first, on an old log
that starts with `plan`: `NonDeterminism: log has 'plan' at 0, code asked
'search:0'`. So a deploy can break runs that are in flight. Fixes: version
the workflow (old runs finish on old code), or guard the new branch with a
version marker written to the log.

**Temporal** (`temporal_run.py`). The same workflow. Worker 1 is killed
inside the first `search` (the work is done, the result never reaches the
server). Worker 2 finishes the run.

| Activity | Attempts (from the workflow history) |
| --- | --- |
| `price` (fails twice by design) | 3 |
| `plan` | 1 |
| `search` (2 calls) | 3: the first call ran twice |
| `answer` | 1 |

35 history events. `plan` did not run again on worker 2: its result was in
the history. The killed `search` ran twice: at-least-once, as in C. The run
took ~85 s, and 30 s of that was waiting: the server only learns that a
worker died when the `start_to_close_timeout` fires. Long activities should
**heartbeat** with a short heartbeat timeout.

| From scratch | Temporal |
| --- | --- |
| `ctx.step(name, fn)` | `workflow.execute_activity(fn, ...)` |
| `data/runs/<id>.jsonl` | event history on the server |
| call the function again | a worker replays the history |
| `retries`, `backoff` | `RetryPolicy` |
| `NonDeterminism` | non-determinism error; `workflow.patched()` for versions |
| one process, one file | many workers, task queues, timers, signals, queries |

## What I would do in production

- LLM and tool calls are **activities**. The agent loop is the **workflow**.
- Big payloads (tool outputs, documents) go to a blob store. The history
  keeps only a reference. Temporal limits history size (~50 MB / 51k events).
- Very long agent sessions use **continue-as-new**: start a fresh history
  with the current state, so replay stays fast.
- Human approval = wait for a **signal**. The workflow sleeps for days at no
  cost.
- Every activity that moves money gets an idempotency key from the workflow.

## Review questions

**Q: What is durable execution?**
> The run survives the process. The engine logs the result of every step.
> After a crash, a worker runs the workflow code again and reads finished
> steps from the log, so no work is repeated and no state is lost.

**Q: Checkpointing state vs replaying history - what is the difference?**
> A checkpoint stores a snapshot of the state; you resume from it. Replay
> stores the result of each step and rebuilds the state by running the code
> again. Replay needs deterministic code, but local variables, loops and
> waits all survive without you saving them by hand, and the history is a
> full audit log.

**Q: Why must workflow code be deterministic? What breaks it?**
> Replay must reach the same steps in the same order. `random`, the wall
> clock, reading env or network outside an activity, iterating a set, or a
> code change all break it. LLM calls are non-deterministic, so they must be
> activities: the log keeps the one answer the model gave.

**Q: Does Temporal give exactly-once execution?**
> No. Workflow state transitions are exactly-once, but an activity can run
> more than once (worker dies before it reports). So activities must be
> idempotent: pass a key, and let the other system drop duplicates.

**Q: How do you deploy a workflow change while runs are in flight?**
> Either pin old runs to old code (worker versioning, new task queue), or
> keep both paths in the code behind a version marker (`patched`) that is
> recorded in the history. Remove the old path when no old run is left.

**Q: When is a workflow engine too much?**
> Short requests (seconds) with no side effects: a retry by the client is
> enough. Use an engine when a run is long, costly to repeat, waits for
> humans or timers, or has side effects that must not happen twice.
