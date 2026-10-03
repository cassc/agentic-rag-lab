# Cheat sheet - agentic RAG, harnesses, evals, agent runtime

All concepts on one page. Each item: what it is, one trade-off, one key
takeaway. Lesson numbers point to runnable code.

---

## 1. RAG basics (lessons 1-2)

| Term | Plain meaning |
| --- | --- |
| RAG | Find relevant text first, then let the LLM answer from it. |
| Chunk | A small piece of a document, the unit you search. |
| Embedding | A vector that captures meaning. Close vectors = similar meaning. |
| Dense search | Nearest vectors (cosine). Good at meaning. |
| BM25 | Keyword search. Good at exact IDs (`-1021`, endpoint names). |
| Hybrid | Both, merged with RRF (rank-based fusion). |
| Reranker | Cross-encoder that scores (question, chunk) together. Precise, slower. |
| ANN / HNSW | Approximate nearest-neighbour index, for millions of vectors. |
| Grounding | Every claim comes from a retrieved chunk, with a citation. |

**Takeaway:** "Bi-encoder to recall, cross-encoder to rank, and a golden set to
prove each step helped."

## 2. Agentic RAG

**Naive RAG** retrieves once with the user's words. **Agentic RAG** lets the
model control retrieval: *whether* to retrieve, *what* to search, *how many
times*, and *when to stop*.

| Pattern | What it does | Cost / risk |
| --- | --- | --- |
| Query decomposition | Split "A and B?" into sub-questions | More calls |
| Multi-hop | Answer of hop 1 builds the query of hop 2 | Errors compound across hops |
| Adaptive retrieval | Decide if retrieval is needed at all (simple questions skip it) | Wrong skip = hallucination |
| **CRAG** (Corrective RAG) | A grader labels retrieved chunks correct / ambiguous / wrong; if weak, rewrite the query or use another source | Grader errors; extra latency |
| **Self-RAG** | Model emits reflection signals: need retrieval? is this chunk relevant? is my answer supported? | Original version needs a fine-tuned model; prompt-based versions approximate it |
| ReAct | Loop: think -> act (tool call) -> observe -> think | Can loop forever without limits |
| Retrieve-reflect-refine | Draft answer, check it against sources, retrieve again for gaps | Needs a stop condition |
| HyDE | Generate a fake answer, embed *that* to search | Fake answer can mislead |
| Multi-agent retrieval | Several retrievers/agents for different sources (docs, account data, market data), then merge | Coordination cost |

**Always name the controls:** max iterations, token/cost budget, timeout,
and a "not found" answer when evidence is weak.

**Takeaway:** "Start with hybrid + rerank and measure. Add agentic steps
only for the question types that fail - usually multi-fact questions - because
each loop adds latency and cost."

**Our numbers:** single retrieval: single-hop hit@5 1.00 (hybrid), multi-hop
only 0.40. That gap is the business case for agentic RAG.
Lesson 3 on 5 multi-hop questions: single k=5 3/5 correct, k=10 4/5,
decomposition 4/5, iterative loop 5/5 at ~2.4 LLM calls/question (it stops
early when one hop is enough). Lesson: try bigger k before adding a loop.
Lesson 4 (CRAG) on 25 answerable + 5 unanswerable: naive 22/25 and 5/5
refused; CRAG 23/25 and 5/5, at 2.2x LLM calls. A strict grounding prompt
already did most of the work; the grader's own errors (same topic, wrong
fact) are the limit.
Lesson 5 (prompted Self-RAG) on 35: baseline 33/35, self-RAG 31/35 at 3.3x
calls. Verify-and-fix repaired 2 incomplete answers, but adaptive retrieval
skipped 7/35 doc questions and the model answered from memory. For a domain
assistant, default to always retrieving. Grounded != complete.

## 3. Agent harness (runtime)

The harness is everything around the model that makes it an agent.

| Piece | What it means |
| --- | --- |
| Agent loop | Model calls a tool -> runtime runs it -> result goes into context -> repeat until done or a limit |
| Tool design | Clear schemas, small tools, error messages the model can act on, idempotent where possible |
| Context engineering | Choose what goes in the window: system prompt, tools, retrieved data, memory, history |
| Compaction | Summarize old turns when the window fills. "Context rot" = quality drops as context grows |
| KV cache / prompt caching | Keep the prompt prefix stable (system, tools) and append at the end, so the provider reuses cached work. Editing early context breaks the cache |
| Memory | Short-term = context. Long-term = files or a store the agent reads/writes. Risk: stale memory |
| Skills | Packaged instructions + scripts loaded only when relevant (saves context) |
| MCP | Standard protocol to expose tools/data to any agent. Binance ships an MCP Server |
| Subagents / multi-agent | Delegate a task to a fresh context; parallel work; isolates noise. Costs more tokens |
| Plan / execute | Plan first, then run steps; re-plan on failure |
| Session recovery | Checkpoint state after each step; resume after a crash; replay for debugging |
| Sandbox isolation | Run code/tools in a container with limits, per session |
| Multi-tenant runtime | Many users' sessions on shared infra: isolation, quotas, no data leaks between tenants |
| Middleware / hooks | Code that runs before/after each tool call: permissions, logging, redaction, human approval |
| Observability | Trace every step: tokens, cost, latency per tool, errors |
| Prompt injection | Retrieved text or tool output may contain instructions. Treat it as data, never as commands |

**Binance-specific safety:** Agent OS runs agents in isolated sub-accounts,
with no withdrawals to external addresses and scoped permissions. Note: "the
guardrail stops theft, not bad trades - so you still need limits, approval for
risky actions, and evals."

**Our numbers (lessons 6-7):** native tool-calling agent 5/5 multi-hop at 2.2
steps; it combined live filters and docs ("0.00001 BTC at 50,000 fails
NOTIONAL: 0.5 < 5"). Crash after step 1, then resume: no repeated work.
Order hook denied unapproved and over-limit orders. The injection was not
obeyed, but the hook would have blocked it anyway. Compaction on a long
task: no compaction took 6 steps and 51k tokens; clearing old outputs made
the agent forget and loop until the budget ran out (12 steps, no answer);
notes then clear took 4 steps and 12k tokens.

## 4. Evaluation

| Level | Metric examples |
| --- | --- |
| Retrieval | hit@k / recall@k, MRR, nDCG, precision@k |
| Answer (RAG) | faithfulness / groundedness, answer relevance, context precision/recall (RAGAS names) |
| End to end | task success rate, latency, cost per task |
| Trajectory | were the steps sensible? wasted tool calls? unsafe actions? |

- **Golden set:** real user questions + expected sources/answers, versioned.
  Ours: 35 questions (5 multi-hop, 5 unanswerable), labelled by doc + key phrase.
- **LLM-as-judge:** cheap, scalable; biased (position, length, self-preference).
  Calibrate on a small human-labelled set.
- **Non-determinism:** run several trials. pass@k = at least one of k works.
  pass^k = all k work (reliability - what users feel).
- **Regression in CI:** run evals on every prompt, model, or tool change.
- **Online:** A/B tests, user corrections, escalations, thumbs down. Turn
  production failures into new golden-set rows.
- **Public benchmarks:** SWE-bench (coding), tau-bench (tool-agent-user with
  policies), GAIA (general assistant), BrowseComp (hard web search).
  Contamination risk: the model may have seen the test.
- **Look at misses, not just averages.** Our bigger reranker raised MRR but
  lost one question.

**Our numbers (lesson 8):** strict judge 0.94 agreement (kappa 0.89) vs
rubric judge 1.00 on 18 labels (caveat: same author for labels and rubric).
pass@1 = pass@3 = pass^3 = 1.00 means the benchmark is saturated, so add harder
cases. Regression gate: baseline.json + tolerances, exit 1 in CI.

## 5. Working with coding agents

- Features worth knowing: skills, subagents, MCP, hooks.
- Workflow: write a spec, give context, let the agent draft, review every
  change before merge, keep tests honest.
- Failure modes seen: invented APIs, over-confident edits, lost context in
  long sessions, tests weakened to pass, drifting from instructions.
- Taste: agents are great at boilerplate, search, first drafts, unfamiliar
  stacks; weak at knowing what they don't know. Verification is your job.

## 6. Design exercise: crypto support agent

"Design an agent that answers user questions from docs and account data."

1. **Sources:** help docs + API docs (RAG), account data (tools with the
   user's scoped token), market data (tools).
2. **Router:** classify - doc question / account question / action request.
3. **Retrieval:** hybrid + rerank; decomposition for multi-fact questions;
   CRAG grader with a "not found -> escalate to human" path.
4. **Tools:** read-only by default. Anything that moves funds needs explicit
   user confirmation (hook) and hard limits.
5. **Safety:** prompt-injection defence on retrieved text; PII redaction in
   logs; per-tenant isolation.
6. **Evals:** golden set per intent; groundedness judge; task success;
   latency p95; cost per conversation. Run in CI.
7. **Feedback loop:** escalations and thumbs-down -> labelled -> new eval
   rows -> fix -> re-run.

## 7. Agent runtime at scale (lessons 9-17)

The runtime is what lets many agents run for a long time and survive
failure. Full picture: [docs/design/agent-runtime.md](docs/design/agent-runtime.md).

| Term | Plain meaning | Trade-off / rule |
| --- | --- | --- |
| Durable execution | Log the result of every step; after a crash, run the code again and read finished steps from the log (replay) | Workflow code must be deterministic |
| Activity | A step with side effects (LLM call, tool call). Runs at-least-once | Needs an idempotency key |
| Idempotency key | A stable id for one side effect, so a repeat is dropped | The other system must remember it |
| Workflow versioning | Old runs finish on old code; new code behind a version marker | A deploy can break in-flight runs |
| LLM gateway | One service between agents and providers: failover, retries, quotas, cost | One more hop; must not be a single point of failure |
| Retry vs fallback | Retry fixes short errors; only another provider fixes an outage | Never retry a 400/401 |
| Circuit breaker | After N failures, skip the provider for a cooldown | Stops paying the timeout on every request |
| Structured output | Schema in the prompt + validate + repair round | Valid is not correct |
| Time to first token | What the user feels. Thinking delays it | Turn thinking off for simple steps |
| Working memory / session state / long-term memory | Context window / run progress / facts across sessions | Different lifetimes, different stores |
| Memory update | The writer sees old facts and replaces them by id | Append-only goes stale |
| Tenant scope | Filter by tenant in the store, from the token | Never a choice of the model |
| Supervisor / workers | A lead agent calls worker agents as tools | Budgets multiply down the tree |
| Handoff | Control moves to another agent with the conversation | Information lost at the handoff |
| Queue + workers | API answers 202 at once; stateless workers pull jobs | At-least-once delivery |
| Backpressure | Bound the backlog, answer 429 + Retry-After | A queue moves the wait, it adds no capacity |
| Dead-letter queue | Where a job goes after N failed attempts | Alert on it |
| Event sourcing | Store every change as an event; state = fold over events | Needs snapshots for long streams |
| CQRS | Writes append events; reads use views built from them | Read models lag a little |
| Optimistic concurrency | Append only if the version is what you last saw | The stale writer must retry |
| Trace / span | One tree per run; one node per LLM or tool call | Pass the context across threads and queues |
| Tail sampling | Decide after the run: keep errors and slow runs | Needs a collector that buffers |
| Latency budget | Split the target time over the steps; pass the deadline down | Degrade on purpose when it runs out |
| MCP server | Tools as a service, one protocol (`list_tools`, `call_tool`) | A dependency you must review |
| MCP gateway + registry | One entry: which servers exist, who may call what, audit | Hiding a tool is not a permission |
| Tool poisoning / rug pull | Tool descriptions are untrusted text in your prompt; they can change | Pin a fingerprint, block on change |
| Runtime interface | Your own `run() -> result`; frameworks are adapters | Keep it thin |
| Contract test | The same tests for every adapter, through the interface | Plus the same evals |
| Admission control | Limits per tenant at the API | Fair queueing is the better fix |

**Takeaway:** "The model is one part. The runtime decides if an agent
product is reliable: every step is logged and replayable, every side effect
has an idempotency key, every limit is in code, every run has a trace, and
every tenant has a quota."

**Our numbers:**

- **9 Durable:** crash after step 2, replay: 2 LLM calls + 2 searches in
  total, same as no crash. Crash before the log write: 2 orders without an
  idempotency key, 1 with. Temporal: killed worker -> `plan` ran once,
  `search` ran twice; 30 s lost waiting for the activity timeout (use
  heartbeats).
- **10 Gateway:** flaky provider: 9/20 -> 18/20 with retries -> 20/20 with
  fallback. Outage: retries 0/20, fallback 20/20. Breaker: 20 s -> 4 s lost
  over 10 requests. Routing: cheap model 12/12, strong model 12/12 with
  25-40% more tokens - routing would only add cost. Structured: loose prompt 0/10
  valid, 10/10 after repair; schema in prompt 10/10 first try. First token:
  7-12 s with thinking, 0.6-0.8 s without.
- **11 Memory:** no memory 1/12; full history 12/12 at 271 tokens; facts
  append-only 9/12 (all misses were changed facts); facts with update 12/12
  at 110 tokens; no user scope 7/12 with a leak and an overwritten limit.
- **12 Multi-agent:** single agent 8/8 at 4.7k tokens; supervisor + 2
  workers 7/8 at 36-58k tokens. Failures were coordination (step limits),
  and runs varied a lot (10.5 vs 14.4 LLM calls per task).
- **13 Events:** 16 workers behind a provider limit of 4 = as fast as 4.
  No backlog limit: p95 wait 2.8 s and growing; limit 20: 0.4 s, half
  refused. Plain consumer: 60 side effects for 50 jobs; idempotent: 50.
- **14 Observability:** LLM = 87% of run time; LLM call p50 1.3 s, p95
  9.3 s. Head sampling 25% kept 0 of 2 interesting traces; tail kept 2.
- **15 MCP:** 3 tools ~470 schema tokens per LLM call, 28 tools ~3,431.
  Protocol overhead ~2 ms. Hidden tool called by name: denied at the
  gateway. Changed tool description: server blocked by fingerprint.
- **16 Frameworks:** own loop 10/10, LangGraph 10/10, same steps. The
  framework adds checkpoints and pause/resume, not quality.
- **17 Service:** 300 runs at once: p95 7.1 s with no limit, 1.0 s with a
  backlog limit of 40 (260 refused). 5 retried POSTs: 5 runs without an
  idempotency key, 1 with. Small tenant behind a big one: 3.1 s, with a
  tenant limit 0.56 s.

## 8. Design exercise: agent runtime for hundreds of agents

"Design the platform that runs our agents."

1. **API:** `POST /runs` -> 202 + id, idempotency key, SSE events, 429 when
   full, approve and cancel endpoints.
2. **Execution:** workflow engine (Temporal). Agent loop = workflow; LLM and
   tool calls = activities with idempotency keys. Stateless workers.
3. **Gateways:** LLM gateway (failover, quotas, cost) and MCP gateway
   (registry, roles, audit). No keys in agents.
4. **State:** run history in the engine; status and idempotency keys in
   DynamoDB; cache and counters in Redis; memory in Postgres + vectors, by
   tenant; big payloads in S3.
5. **Scale:** autoscale workers on queue backlog and wait time, capped by
   provider quota. Separate pools for chat and batch.
6. **Tenants:** identity from the token, quotas at admission, fair queues,
   every store keyed by tenant.
7. **Observability:** one trace from API to tool; tokens and cost per
   tenant; SLOs; online evals on sampled traces.
8. **Delivery:** Terraform, GitHub Actions with an eval gate, ArgoCD canary.
   Prompts and tool schemas are releases.
9. **Failure:** name each one and its answer - worker death, provider
   outage, rate limit, poison run, agent loop, injection, bad deploy.
