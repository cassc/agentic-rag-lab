# Lesson 3 - Query decomposition and multi-hop retrieval

Diagram: `L3_MultiHop` in [docs/diagrams](../../docs/diagrams/README.md).

## The problem

"My bot gets error -1021. What window must the timestamp fit, and how large
can I make it?" needs two facts from two docs: `errors.md` (what -1021 means)
and `rest-api.md` (recvWindow default 5000 ms, max 60000 ms). One search with
the whole question often finds only one of them.

## Three ways to handle it

1. **Single retrieval**: one search, top k. Cheapest.
2. **Decomposition** (plan first): the LLM splits the question into
   standalone sub-queries up front; search each; merge the lists
   (interleave by rank, drop duplicates). The sub-queries are **parallel** -
   they can't use each other's results.
3. **Iterative multi-hop** (a small agent loop): search -> the LLM reads the
   new sources, updates its notes, and writes the *next* query for the missing
   fact, or stops. The next query can use what hop 1 found. Hard limit: 3
   hops.

## Run it

```sh
uv run lessons/03_multi_hop/run.py     # needs DEEPSEEK_API_KEY or LLM_API_KEY
```

## Results (5 multi-hop questions, hybrid retriever, DeepSeek)

| Method | Hops found | Answer correct | LLM calls/q | Chunks/q |
| --- | --- | --- | --- | --- |
| single, k=5 | 3/5 | 3/5 | 1 | 5 |
| single, k=10 | 4/5 | 4/5 | 1 | 10 |
| decomposed | 4/5 | 4/5 | 2 | 6.8 |
| iterative | **5/5** | **5/5** | 2.4 | 5.6 |

"Answer correct" is judged by an LLM against the reference answer
(`lab/judge.py`). Five questions is a tiny sample: treat this as a demo of
the shape, not proof.

What to learn from it:
- **Try the cheap fix first.** Just raising k to 10 matched decomposition.
  More context costs tokens but no extra round trip.
- **Iterative wins on dependent facts**, and it *stops early* when the first
  search already has everything (3 of 5 questions needed only one hop). So the
  average cost stayed near 2 LLM calls, not 4.
- **Decomposition can miss when the split is wrong.** For the pegged-order
  question it wrote two sub-queries that both stayed on the pegged-order doc,
  so the price-filter rules were never retrieved.
- **The model leaks its own knowledge into queries.** In one trace the second
  query was "recvWindow default 5000 maximum 60000": the model already
  "knew" the answer. That helps retrieval, but it also means a wrong belief
  can steer the search. Grounding (answer only from sources) still matters.

## Review questions

**Q: What is multi-hop retrieval and why is it hard?**
> A question whose answer needs facts from several places, often where one
> fact tells you what to look for next. It's hard because one embedding of the
> whole question sits "between" the facts and matches none of them well, and
> because errors compound: a wrong hop 1 sends hop 2 to the wrong place.

**Q: Decomposition or an iterative loop?**
> Decomposition when the sub-questions are independent: you can run them in
> parallel, so latency stays low. An iterative loop when a later search
> depends on an earlier answer. The loop needs a max-hop limit, a budget, and
> a clear stop signal. In my test the loop was most accurate and, because it
> stopped early, cost only ~2.4 calls per question.

**Q: How do you stop an agentic retrieval loop from running forever or
drifting?**
> A hard cap on hops and tokens; the model must return an explicit "done"
> signal; don't re-add chunks it already saw; keep a running notes summary
> instead of the full history (so context doesn't grow); log every query so
> you can see drift in traces.

**Q: How would you evaluate it?**
> Retrieval: were *all* the needed facts found (every hop in the retrieved
> set)? Answer: correctness against a reference, with an LLM judge checked
> against a few human labels. Cost: LLM calls, tokens, latency per question.
> Compare against the cheap baseline (bigger k) so you know the loop is worth
> it.
