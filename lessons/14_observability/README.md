# Lesson 14 - Observability: traces, cost, and latency budgets

## The idea

A normal service does the same thing for the same request. An agent decides
at run time how many steps to take and which tools to call. So "it was slow"
or "it was wrong" has no answer unless you recorded **what this run did**.

The unit is the **trace**: one tree per run.

```
invoke_agent                 (root span: the run)
  |- chat                    (one LLM call: model, tokens in/out, cached)
  |- execute_tool search_docs
  |- execute_tool get_price
  |- chat
```

`lab/trace.py` (~55 lines) does this with the real **OpenTelemetry SDK**.
Attribute names follow the OTel GenAI conventions (`gen_ai.usage.input_tokens`,
`gen_ai.tool.name`, ...), so Langfuse, Arize, Jaeger, Tempo or Datadog can
read the spans without custom code.

| Signal | Answers | Example |
| --- | --- | --- |
| Trace | what did **this run** do, in what order, how long | the tree above |
| Metric | how is the **system** doing over time | p95 run latency, tokens/min, queue depth |
| Log | details of one event | the full prompt of one call |
| Eval score | was the **answer** good | groundedness judge on sampled traces (lesson 8) |

## Run it

```sh
uv run lessons/14_observability/run.py
```

8 runs of the single agent (5 multi-hop doc questions, 3 with live data, one
of them about a symbol that does not exist). Spans go to memory and the
script reads them back.

To send the same spans to a real backend, add `opentelemetry-exporter-otlp`
and one line in `lab/trace.py`:

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))  # reads OTEL_EXPORTER_OTLP_ENDPOINT
```

## Results

**The slowest run, as a trace:**

```
invoke_agent  15703 ms
  +     0 ms  chat                          1240 ms  in=545 out=206 cached=384
  +  1241 ms  execute_tool get_symbol_filters  5122 ms
  +  1242 ms  execute_tool get_price           5122 ms
  +  1243 ms  execute_tool search_docs           73 ms
  +  1244 ms  execute_tool search_docs           69 ms
  +  6364 ms  chat                          9339 ms  in=4364 out=972 cached=640
```

You can read the whole story: 4 tools started in the same millisecond
(parallel), two of them waited 5 s on the exchange API, then one LLM call
took 9 s to write 972 tokens. Without the trace this is just "15.7 s".

**Where the time goes** (all 8 runs):

| Span | Count | p50 | p95 | Share of run time |
| --- | --- | --- | --- | --- |
| `chat` | 19 | 1307 ms | 9339 ms | 87% |
| `get_symbol_filters` | 4 | 149 ms | 5122 ms | 12% |
| `get_price` | 2 | 5122 ms | 5122 ms | 11% |
| `search_docs` | 16 | 73 ms | 213 ms | 3% |

(Shares add up to more than 100% because parallel tools overlap.)

- The LLM is 87% of the time. Making retrieval faster would change nothing.
- Look at **p95, not p50**. The LLM call is 1.3 s at p50 and 9.3 s at p95:
  a 7x tail. Output length drives it (972 output tokens in the slow call).
- `get_symbol_filters`: 149 ms normally, 5.1 s once. An outside API with no
  timeout of its own. The fix is a 1-2 s timeout in the tool.

**Per run** (budget: 15 s):

| | |
| --- | --- |
| Run latency | p50 5.8 s, p95 15.7 s |
| Tokens per run | 3.3k - 9.3k |
| Over budget | 1 of 8 (longest span: `chat`, 9.3 s) |
| Runs with a tool error | 1 of 8 (the fake symbol; the agent recovered and answered) |
| Tokens per tenant | acme 17.6k, beta 20.7k |

**Sampling.** You cannot store every trace at scale. Of the 8 traces, 2 are
interesting (one error, one over budget).

| Policy | Traces kept | Interesting ones kept |
| --- | --- | --- |
| head sampling 25% (decide at the start) | 0 in this draw | 0 of 2 |
| tail sampling (decide at the end: error or over budget) | 2 | 2 of 2 |

Head sampling is blind: it decides before it knows what happened. Tail
sampling keeps what you will want to read, plus a small random share for
the baseline.

**A bug worth knowing.** The loop runs tools in a thread pool. Threads do
not inherit the current span, so at first every tool span would have been a
separate trace with no parent. The fix is in `lab/loop.py`: copy the context
into each thread. The same happens across processes and queues: the trace id
must travel **inside the message** (W3C `traceparent` header), or the trace
ends at the queue.

## Latency budgets

Start from what the user accepts (say 15 s for a full answer, 1 s to the
first token), then split it over the steps:

```
budget 15 s = 2 LLM calls x 5 s  +  tools 2 s  +  3 s spare
```

Each step gets a **timeout from the budget** and a **deadline that is
passed down** (the tool knows how much time is left). When the budget is
nearly spent, degrade on purpose: fewer steps, a faster model, thinking off
(lesson 10), a shorter answer. Never let it just run long.

## What I would do in production

- Dashboards and alerts on: run success rate, p95 run latency, time to first
  token, tokens and cost per run and per tenant, tool error rate, steps per
  run, share of runs that hit a limit, provider error rate, queue depth and
  age, dead letters.
- SLOs per use case ("95% of chat runs under 15 s"), with an error budget.
- Prompts and outputs are sensitive: redact PII before export, keep full
  payloads in your own store with short retention, and link them by trace id.
- Online evals: run the judge (lesson 8) on a sample of traces; failures
  become new golden-set rows.
- One trace id from the API through the queue, the workflow, each agent and
  each tool (and each worker agent, lesson 12).

## Review questions

**Q: Why is observability harder for agents than for normal services?**
> The path is decided at run time: a different number of steps, tools and
> tokens every run, and the same input can give a different path. So
> averages hide the story. You need a trace per run, with tokens and cost
> as first-class data, plus quality scores, not just latency and errors.

**Q: What do you put in a trace for an agent?**
> A root span per run (tenant, session, task type), a child span per LLM
> call (model, input/output/cached tokens, finish reason), a span per tool
> call (name, error), and spans for retrieval, hooks and worker agents. Use
> the OTel GenAI attribute names so any backend can read them.

**Q: Your agent is too slow. What do you do first?**
> Read the traces, not the code. Find which span type takes the time at
> p95. In my runs the LLM was 87% of the time and one outside API had a 5 s
> tail. So: shorter outputs, thinking off or a faster model for simple
> steps, a timeout on the tool, parallel tool calls. Speeding up retrieval
> (3%) would do nothing.

**Q: Head sampling or tail sampling?**
> Head sampling is cheap but blind - in my draw it kept none of the 2
> interesting traces. Tail sampling decides after the run: keep all errors
> and slow runs, plus a small random share. It needs a collector that holds
> the whole trace for a short time.

**Q: How do you keep a trace together across threads, queues and agents?**
> Pass the trace context along: copy it into worker threads, put the W3C
> traceparent into queue messages and HTTP headers, and into the workflow
> or the worker agent's input. If you don't, each part shows up as its own
> small trace.

**Q: How do you track cost?**
> Record tokens (input, output, cached) on every LLM span with tenant and
> feature tags, then sum by any of them. Alert on cost per run and on runs
> that hit their budget. Cached tokens matter: they are much cheaper, and a
> change that breaks the cache shows up here first.
