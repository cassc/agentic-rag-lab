# Retrieval metrics and RRF vs rerank

Notes from a Q&A session while working on lesson 02.

## RRF vs rerank

**RRF (Reciprocal Rank Fusion)** merges several ranked lists into one.

- Input: ranked lists (here dense + BM25).
- Uses only each doc's **rank**, not its text or score:
  `score = sum(1 / (60 + rank))` over the lists.
- Fast, cheap, no model.
- Rewards docs that rank high in many lists. It does not know which doc
  really answers the question.

**Rerank** re-scores one list with a stronger model (a cross-encoder).

- Input: the query + each candidate's **text**.
- The model reads query and doc together and scores relevance.
- Slow and costly, so run it only on a small pool (e.g. 20 docs).
- Much more accurate, because it judges meaning.

In [lessons/02_hybrid_rerank/run.py](../lessons/02_hybrid_rerank/run.py):

```python
def hybrid(q, k=5):
    return rrf([dense.search(q, 20), bm25.search(q, 20)], k)

def hybrid_rerank(q, k=5):
    return rerank(q, hybrid(q, 20), k)
```

1. `hybrid`: RRF merges dense + BM25 -> good **recall**.
2. `hybrid_rerank`: the reranker picks the best 5 of the top 20 -> good
   **precision**.

RRF merges by rank. Rerank sorts by reading the text.

## Recall and precision

- **Recall** = relevant retrieved / all relevant. "Did I miss anything?"
- **Precision** = relevant retrieved / all retrieved. "Is what I returned good?"

Example: 4 docs are relevant. You return 5, and 3 of them are relevant.
Recall = 3/4 = 0.75. Precision = 3/5 = 0.6.

### Easy way to remember

A lake has 10 good fish.

- **Recall**: did I catch all the good fish? Caught 5 of 10 -> 5/10.
- **Precision**: is my bucket clean? 5 fish + 5 old boots -> 5/10.

Recall is about **missing** things. Precision is about **junk**.
A big net: high recall, low precision. A small careful net: high precision,
low recall.

## recall@k

Standard, per query, then averaged over all queries:

```
recall@k = relevant docs in top k / all relevant docs for the query
```

Example: 100 relevant docs, k = 5, all 5 returned are relevant.

| Metric | Value | Why |
| --- | --- | --- |
| recall@5 | 5/100 = 0.05 | can never go above 5/100 here |
| precision@5 | 5/5 = 1.0 | every returned doc is good |
| hit@5 | 1 | at least one good doc in top 5 |

So recall@k is only useful when a query has few relevant docs (fewer than
k). That is why RAG golden sets usually have 1-2 target chunks per query.

### What this repo measures

[lab/evals.py](../lab/evals.py) reports **hit@k** (called recall in the
docstring):

- A query scores 1 if its target chunk is in the top k, else 0. Average over
  queries.
- A chunk is a hit only if it is from the right `doc` and contains every
  `must` string.
- Multi-hop rows score 1 only if **every** hop is in the top k. No partial
  credit.

With one target per query, hit@k = recall@k. They differ only for multi-hop:
finding 1 of 2 hops gives recall 0.5 but hit 0.

## Other terms

**Retrieval** (did we find the right chunks?)

- **Hit@k**: any good chunk in top k? 1 or 0. Used here.
- **MRR** (Mean Reciprocal Rank): how high is the first good chunk?
  Rank 1 = 1.0, rank 2 = 0.5, rank 3 = 0.33. Averaged over queries. Used
  here. "Is the good fish at the top of the bucket?"
- **nDCG**: like MRR, but scores all good chunks and allows grades
  ("very good" vs "a bit good"). Use it when many chunks are relevant.
- **F1**: one number that mixes precision and recall. High only if both are
  high.

**Answer** (did the LLM use the chunks well?)

- **Faithfulness / groundedness**: is the answer based on the chunks, or
  made up? Low = hallucination.
- **Answer relevance**: does the answer respond to the question?
- **Context precision / context recall**: precision and recall of the chunks
  given to the LLM (names from the RAGAS library).

Learn **MRR** and **faithfulness** first.
