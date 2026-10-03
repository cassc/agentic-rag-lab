# Lesson 12 - Multi-agent: when it helps, what it costs, how it fails

## The idea

One agent has one context window. Everything it reads stays there, and
quality drops as the window fills. A second agent is a **second, clean
window**: give it a sub-task, get back only the result.

That is the whole reason for multi-agent. The price: every worker must be
told the task again (it starts with nothing), and every handoff is a place
where information is lost or changed.

`lab/multi.py` (~50 lines) is the simplest useful shape, **agents as tools**:

```
supervisor (no tools of its own)
  |- docs_agent     (search_docs)
  |- market_agent   (get_price, get_symbol_filters)
```

A worker is a normal agent loop (`lab/loop.py`). To the supervisor it looks
like a tool with one argument, `task`. The supervisor sees only the worker's
final answer, not its searches.

| Pattern | Shape | Use when |
| --- | --- | --- |
| Supervisor / workers | one lead delegates, workers report back | sub-tasks are independent |
| Handoff (swarm) | agent A gives the whole conversation to agent B | different stages or skills, one active at a time |
| Pipeline | fixed order A -> B -> C | the steps are known in advance (that is a workflow, lesson 9) |
| Debate / review | one writes, one checks | the check is cheap and catches real errors (lesson 5) |

## Run it

```sh
uv run lessons/12_multi_agent/run.py      # A, B, C
uv run lessons/12_multi_agent/run.py B    # just one
```

8 tasks: the 5 multi-hop doc questions, plus 3 that need docs **and** live
market data.

## Results

| Setup | Correct | LLM calls/task | Tokens/task | Seconds/task |
| --- | --- | --- | --- | --- |
| single agent, all 3 tools | **8/8** | **2.2** | **4.7k** | 18 |
| team, full brief (run 1) | 7/8 | 14.4 | 58k | 23 |
| team, full brief (run 2) | 7/8 | 10.5 | 36k | 21 |
| team, 4-word brief | 8/8 | 7.8 | 14k | 11 |
| team, workers one by one (run 1) | 7/8 | 9.4 | 31k | 26 |
| team, workers one by one (run 2) | 8/8 | 8.6 | 28k | 22 |

**The single agent won.** Same or better score, at 1/8 to 1/12 of the
tokens. These tasks are small: two or three lookups fit easily in one
window, so a second window buys nothing and every handoff costs.

**Where the tokens went.** The supervisor wrote long briefs ("return all
live trading filters... I need: for PRICE_FILTER: minPrice, maxPrice..."),
each worker then ran its own loop, and each worker call re-sends its system
prompt and tool schemas.

**The failures were coordination failures, not knowledge failures:**

- Run 1: the supervisor kept delegating again and hit its step limit. No
  answer, 6 supervisor steps of worker runs paid for.
- Run 2: a worker hit **its** step limit, reported nothing useful, and the
  supervisor answered "Not in the sources" for a question the single agent
  got right.
- One run: the supervisor's "answer" was a report about how it delegated,
  not the answer.

**The thin brief did not hurt - it helped.** I expected a 4-word brief to
lose context. It scored 8/8 at a quarter of the tokens. The briefs became
short search queries ("NOTIONAL filter rule", "BTCUSDT live filter values"),
workers did one lookup each, and the supervisor kept the question and did
the reasoning itself. A thin handoff fails when the worker needs the detail
to do its job; here it did not. Don't copy a rule ("always write full
briefs") - measure it on your tasks.

**Run to run, the team changes a lot.** Same code, same tasks, temperature
0: 14.4 vs 10.5 calls per task, 58k vs 36k tokens. The single agent: 2.2
both times. More agents = more model decisions = more variance. Evaluate
with several trials (pass^k, lesson 8).

**Parallel workers barely helped here** (23 vs 26 s, 21 vs 22 s: inside the
noise). Few turns had two workers at once, and LLM latency dominates.

**Context isolation was small too.** The supervisor's largest prompt was
~2.5-3.2k tokens against ~3.0-3.2k for the single agent, because workers
sent back long answers. With the short brief it was 1.6k.

## The budget multiplies

Supervisor 6 steps x up to 2 workers per step x 4 steps each = **up to 54
LLM calls** for one question, from limits that each look small. A tree of
agents needs **one budget for the whole tree** (tokens, calls, wall time),
passed down and counted at every level.

## When multi-agent is worth it

- The task is wide: many independent sub-tasks that each read a lot (research
  over 20 sources). Workers read in parallel and return summaries.
- The context would overflow or rot in one window.
- Different trust levels: a worker with read-only tools reads untrusted web
  text; the agent that can move funds never sees it (lesson 7).
- Different owners: teams ship their own agents behind a stable contract.

Not worth it: tasks that fit one window, tightly coupled steps (each needs
the full result of the last), or latency-sensitive paths.

## Review questions

**Q: Why use more than one agent at all?**
> For a clean context per sub-task, for parallel work, and for isolation
> (tools, trust, ownership). Not for "more intelligence": it is the same
> model. In my test one agent beat the team on score, cost and speed,
> because the tasks fit one window.

**Q: What are the typical failure modes of multi-agent systems?**
> Lost or changed information at the handoff. Loops and ping-pong (delegate
> again and again). Budget blow-up: limits multiply down the tree. A worker
> fails quietly and the lead trusts the bad report. Duplicate work. Higher
> variance between runs. Errors that are hard to trace without a trace tree
> across agents.

**Q: How do you design the handoff?**
> The worker starts with nothing, so the brief must hold what it needs: the
> goal, the limits, the format of the result. But longer is not better - in
> my test long briefs made workers do more than needed. Ask for a short,
> structured result. Keep the reasoning in one place.

**Q: How do you control cost and loops in an agent tree?**
> One budget for the whole tree, passed to every worker. Step limits at each
> level. Detect repeated identical delegations. A deadline that is passed
> down. Stop conditions in code, not in the prompt.

**Q: How would you evaluate single vs multi-agent?**
> Same tasks, same judge, several trials. Compare correctness, tokens, LLM
> calls, latency and variance. Read the failed runs. Start with one agent
> and add workers only for the task types where it fails.

**Q: Supervisor or handoff - what is the difference?**
> With a supervisor, control comes back: workers are like function calls and
> the lead writes the answer. With a handoff, control moves: the next agent
> owns the conversation. Supervisor suits independent sub-tasks; handoff
> suits stages (triage -> specialist).
