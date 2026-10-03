"""Lesson 14: trace agent runs with OpenTelemetry, then answer from the spans:
where does the time go, what does a run cost, which runs break the latency
budget, and which traces are worth keeping."""
import random
from collections import defaultdict
from opentelemetry.trace import StatusCode
from lab import trace
from lab.evals import load_golden
from lab.tools import TOOLS, retriever

SYSTEM = """You are a Binance Spot API assistant with tools.
Use search_docs for rules and definitions, and the market tools for live values.
Never guess numbers. Cite doc sources by their id, e.g. (filters#12).
If the docs don't cover it, say "Not in the sources." """
READ_ONLY = {n: TOOLS[n] for n in ("search_docs", "get_price", "get_symbol_filters")}
TASKS = [r["q"] for r in load_golden(multi_hop=True)] + [
    "Would a LIMIT BUY of 0.00001 BTC at 50000 USDT on BTCUSDT pass the live filters? "
    "Name the filter that decides it and explain its rule from the docs.",
    "What is the smallest price step for BTCUSDT right now, and which filter defines it?",
    "What are the live trading filters for the symbol FAKECOINUSDT?"]
BUDGET_MS = 15_000  # the latency budget for one run

retriever()  # load the embedding model first, so it is not counted in the first span
for i, q in enumerate(TASKS):  # one by one: clean latency numbers
    trace.run(SYSTEM, q, READ_ONLY, **{"tenant.id": "acme" if i % 2 else "beta", "task.id": i})

spans = trace.exporter.get_finished_spans()
kids, roots = defaultdict(list), []
for s in sorted(spans, key=lambda s: s.start_time):
    (kids[s.parent.span_id] if s.parent else roots).append(s)


def under(root):
    out = []
    for k in kids[root.context.span_id]:
        out += [k] + under(k)
    return out


def tokens(root):
    return sum(s.attributes.get("gen_ai.usage.input_tokens", 0)
               + s.attributes.get("gen_ai.usage.output_tokens", 0) for s in under(root))


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


slow = max(roots, key=trace.ms)
print(f"== the slowest run as a trace tree (task {slow.attributes['task.id']})")
print(f"invoke_agent  {trace.ms(slow):.0f} ms")
for s in under(slow):
    a = s.attributes
    extra = (f"in={a['gen_ai.usage.input_tokens']} out={a['gen_ai.usage.output_tokens']} "
             f"cached={a['gen_ai.usage.cached_tokens']}" if s.name == "chat" else
             "ERROR" if s.status.status_code == StatusCode.ERROR else "")
    print(f"  +{(s.start_time - slow.start_time) / 1e6:6.0f} ms  {s.name:34} {trace.ms(s):6.0f} ms  {extra}")

print("\n== where the time goes (all runs)")
total = sum(trace.ms(r) for r in roots)
by_name = defaultdict(list)
for s in spans:
    if s.parent:
        by_name[s.name].append(trace.ms(s))
for name, xs in sorted(by_name.items(), key=lambda kv: -sum(kv[1])):
    print(f"  {name:34} n={len(xs):2}  p50 {pct(xs, .5):6.0f} ms  p95 {pct(xs, .95):6.0f} ms  "
          f"share of run time {sum(xs) / total:4.0%}")

print(f"\n== per run (budget {BUDGET_MS} ms)")
keep = []
for r in roots:
    errors = [s.name for s in under(r) if s.status.status_code == StatusCode.ERROR]
    over = trace.ms(r) > BUDGET_MS
    worst = max(under(r), key=trace.ms)
    keep.append(bool(errors) or over)
    print(f"  task {r.attributes['task.id']} tenant={r.attributes['tenant.id']:5} {trace.ms(r):6.0f} ms  "
          f"tokens={tokens(r):6}  llm calls={sum(s.name == 'chat' for s in under(r))}  "
          f"{'OVER BUDGET, longest span: ' + worst.name + f' {trace.ms(worst):.0f} ms' if over else ''}"
          f"{'  errors: ' + str(errors) if errors else ''}")
d = [trace.ms(r) for r in roots]
print(f"  run latency p50 {pct(d, .5):.0f} ms  p95 {pct(d, .95):.0f} ms   "
      f"tokens per tenant: " + str({t: sum(tokens(r) for r in roots if r.attributes['tenant.id'] == t)
                                    for t in ('acme', 'beta')}))

random.seed(0)
head = [random.random() < 0.25 for _ in roots]
print(f"\n== sampling: which of the {len(roots)} traces do we store?")
print(f"  head sampling 25% (decide at the start): keeps {sum(head)}, "
      f"of the {sum(keep)} interesting ones it keeps {sum(h and k for h, k in zip(head, keep))}")
print(f"  tail sampling (decide at the end: errors or over budget): keeps {sum(keep)}")
