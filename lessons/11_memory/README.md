# Lesson 11 - Memory and state: what an agent keeps between sessions

## The idea

The model keeps nothing between calls. Everything it "knows" about a user
must be put into the context again, every time. So memory is a **selection
problem**, like RAG: of all that was ever said, which few lines go into this
call?

Keep three layers apart. They have different lifetimes and different stores:

| Layer | Lifetime | Example | Store |
| --- | --- | --- | --- |
| Working memory | one run | the message list, tool outputs | context window, checkpoint (lessons 7, 9) |
| Session state | one conversation | step, budget used, pending approval | workflow history, Redis, DynamoDB |
| Long-term memory | across sessions | "max order 500 USDT", "prices in USD" | database + vector index, per user |

Long-term memory has kinds too: **semantic** (facts about the user),
**episodic** (what happened in past runs), **procedural** (how to do a task -
prompts, skills). This lesson builds semantic memory in `lab/memory.py`
(~60 lines):

- **write**: after a session, an LLM turns the transcript into operations:
  `add` a fact, or `update` an old one by id.
- **read**: embed the question, return that user's top 3 facts.
- **scope**: every row has a user; reads and updates only touch that user.

## Run it

```sh
uv run lessons/11_memory/run.py
```

4 users, 11 short sessions (`users.json`), 12 questions asked "later". 5 of
the answers changed during the sessions (EUR -> USD, UTC+8 -> UTC+1, ...).
One question has no answer for that user.

## Results

| Strategy | Correct | Prompt tokens/question |
| --- | --- | --- |
| no memory | 1/12 | 77 |
| full history in the prompt | 12/12 | 271 |
| facts, append only (27 rows) | 9/12 | 109 |
| facts, with update (17 rows) | **12/12** | **110** |
| facts, with update, no user scope (10 rows) | 7/12 | 122 |

**Full history works - while it is small.** 271 tokens is nothing. But it
grows with every session and never stops; a user with 200 sessions does not
fit. Start with it, and measure when it stops being cheap.

**Append-only memory goes stale.** All 3 misses are facts that changed.
For alice's currency the store returned three rows: "prices in USD", "prices
in EUR", "accountant wants USD". The model saw a conflict and answered
"unknown". For bob it picked the old timezone, for dave the old limit (50,
not 200 USDT) - a stale limit on a trading agent is a real risk.

**Update fixes it.** The writer sees the existing memories and replaces the
old fact. 17 rows, not 27, and 12/12 at 40% of the full-history tokens.

**No user scope is a data leak and data damage.** With one shared pool:

- dave asked for his display currency. He never set one. The agent said
  "USD" - alice's preference.
- dave's "raise my limit to 200" **overwrote alice's limit**. The row became
  "capped at 500 USDT (raised from 200)", so dave got 500.
- The writer merged users into 10 rows; alice's and carol's own facts were
  lost ("unknown").

Tenant scope must be a filter in the store, set by the runtime from the
authenticated user. It must never be a choice the model makes.

## Context engineering

Memory is one input among several. The window has a fixed budget; decide what
each part gets, and put stable parts first so the prompt cache keeps hitting
(lesson 7):

```
system prompt + tool schemas     stable, cached
long-term memories (top k)       per user, small
retrieved documents              per question
recent turns                     newest
notes / summary of older turns   from compaction
```

## What I would do in production

- Write memory **after** the session, in the background (a queue job, lesson
  13). It must not add latency to the answer.
- Store the source with each fact (session id, time). Keep old versions, mark
  them replaced: you need this to debug "why did the agent think that?".
- Give facts a time to live, or a last-confirmed date. Old facts get checked
  again or dropped.
- Never store secrets or raw PII as memory. Give the user a way to see and
  delete their memories.
- **Memory poisoning:** memory is written from untrusted text. A prompt
  injection that lands in memory comes back in every later session. Limits
  and permissions stay in code (lesson 7 hooks), never in memory alone.
- Evaluate it like retrieval: a golden set of (sessions, question, answer),
  with changed facts and "unknown" cases.

## Review questions

**Q: What kinds of memory does an agent have?**
> Working memory is the context window for one run. Session state is the
> run's progress (step, budget, approvals), kept in a checkpoint or workflow
> history. Long-term memory survives sessions: semantic (facts), episodic
> (past runs), procedural (how-to). Each has its own lifetime and store.

**Q: Why not just put the whole history in the prompt?**
> It works while small - in my test it scored 12/12. But it grows without
> limit, costs tokens on every call, and quality drops as the context
> grows. Extracted facts gave the same 12/12 at 40% of the tokens, and that
> cost stays flat as sessions add up.

**Q: What is the main failure of a simple memory store?**
> Stale facts. If you only append, the old and the new fact are both
> retrieved and the model picks one or gives up (9/12 in my test, all 3
> misses were changed facts). The write step must update: show the writer
> the existing memories and let it replace by id.

**Q: How do you keep memory safe in a multi-tenant system?**
> Scope every row by tenant and user, and enforce it in the store query from
> the authenticated identity - not in the prompt. Without scope my test
> leaked one user's preference to another and let one user's update
> overwrite another user's limit.

**Q: What are the risks of long-term memory?**
> Stale facts, cross-tenant leaks, stored PII, and memory poisoning (an
> injected instruction saved once is replayed forever). Also drift: nobody
> can explain the agent's behaviour unless each memory keeps its source.

**Q: Where do state and memory live in a scaled runtime?**
> Session state in the workflow engine or a fast key-value store (Redis,
> DynamoDB) keyed by session id, so any worker can pick up the run. Long-term
> memory in a database with a vector index (Postgres + pgvector, OpenSearch),
> partitioned by tenant. Workers stay stateless.
