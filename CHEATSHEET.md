# Cheat sheet - agentic RAG, harnesses, evals

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
