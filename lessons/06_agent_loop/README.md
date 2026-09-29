# Lesson 6 - The agent loop and tool calling

Diagram: `L6_AgentLoop` in [docs/diagrams](../../docs/diagrams/README.md).

## The idea

An agent is an LLM in a loop with tools:

```
messages = [system, user]
repeat (max N steps):
    response = LLM(messages, tool schemas)
    if no tool call: return response          # the final answer
    for each tool call: run it, append the result as a "tool" message
```

That's the whole ReAct pattern (reason -> act -> observe) with native
function calling. The loop in `run.py` is ~20 lines. Frameworks (LangGraph,
AgentScope, OpenAI Agents SDK) add state, streaming, and tracing on top of
the same loop.

## Tools (`lab/tools.py`)

| Tool | Source | Why |
| --- | --- | --- |
| `search_docs(query)` | hybrid retrieval over the docs | rules, definitions |
| `get_price(symbol)` | live public Binance API | current values |
| `get_symbol_filters(symbol)` | live `exchangeInfo` | the actual limits for a symbol |
| `place_order(...)` | **dry run only** | used in lesson 7 to show permission hooks |

Each tool = a JSON schema (what the model sees) + a Python function. Good tool
design: one clear job, a description that says *when* to use it, and errors
returned as text so the model can recover (the loop never crashes on a bad
call).

## Run it

```sh
uv run lessons/06_agent_loop/run.py
```

## Results

**Live tasks** (combine docs + live data):

| Task | Tools used | Result |
| --- | --- | --- |
| BTCUSDT price + smallest price step | price, filters, docs | 0.01 tick size, cites PRICE_FILTER |
| Would 0.00001 BTC at 50,000 pass? | filters + 3 doc searches (parallel) | No: notional 0.5 < live minNotional 5, cites NOTIONAL rule |
| Trailing stop with trailingDelta 5 on ETHUSDT? | docs, filters, price | No: live min is 10 BIPS; 5 BIPS = 0.05% |
| Filters for FAKECOINUSDT | 2 tool errors, then docs | Explains HTTP 400 and error -1121 BAD_SYMBOL; didn't crash |

**Multi-hop golden set**: 5/5 correct, 2.2 steps and 2.2 searches per question.
Compare lesson 3: the hand-written iterative loop also got 5/5 at 2.4 calls.
Native tool calling does the same with less code, and the model writes
precise queries itself ("X-MBX-ORDER-COUNT header", "recvWindow maximum").

Things to notice in the traces:
- **Parallel tool calls**: in one step the model asked for filters and three
  doc searches at once.
- **Error recovery**: on FAKECOINUSDT both market calls failed; the model
  read the error, searched the docs for the error code, and explained it.
- **The step limit** is the only thing guaranteeing termination.

## Review questions

**Q: Walk me through an agent loop.**
> Send the conversation plus tool schemas to the model. If it returns tool
> calls, run them, append each result as a tool message with the call's id,
> and call the model again. When it returns text with no tool call, that's
> the answer. Wrap it all in a max-steps and token budget.

**Q: How do you design good tools?**
> Few, clear tools with one job each; names and descriptions that say when to
> use them; typed parameters; outputs that are compact and structured; errors
> the model can act on ("symbol not found; check the symbol name"). Make
> write actions idempotent and separate them from read tools so you can put
> permissions on them.

**Q: RAG as a pipeline vs retrieval as a tool?**
> A pipeline always retrieves once, then answers - predictable, cheap. As a
> tool, the model decides when and what to search, and can combine it with
> other tools like live market data. More flexible, but less predictable,
> so it needs limits, traces, and evals on the trajectory.

**Q: What breaks in agent loops?**
> Infinite or long loops (fix: step and token caps), repeated identical calls
> (detect and stop), hallucinated tool arguments (validate against the schema),
> huge tool outputs flooding context (truncate, paginate), and prompt injection
> in tool outputs (lesson 7).
