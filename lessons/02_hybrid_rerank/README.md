# Lesson 2 - Hybrid search and reranking

Diagram: `L2_Hybrid` in [docs/diagrams](../../docs/diagrams/README.md).

## The idea

- **Dense search** (embeddings) finds *meaning*: "shared-secret keys" finds
  the HMAC section.
- **Keyword search** (BM25) finds *exact tokens*: `-1021`,
  `POST /api/v3/sor/order`, `EXPIRE_MAKER`. Embeddings blur these.
- **Hybrid** runs both and merges the lists with **Reciprocal Rank Fusion**:
  `score = sum 1 / (60 + rank)`. It uses only ranks, so you never compare
  BM25 scores (0-30) with cosine scores (0-1).
- **Reranker** (cross-encoder): take a wide pool (top 20), score each
  (question, chunk) pair *together*, keep the best 5.

**Bi-encoder vs cross-encoder**: an embedding model encodes question and chunk
*separately* (fast, can pre-compute chunk vectors). A cross-encoder reads them
*together* (sees word-to-word interactions, much more precise, but must run
at query time for every pair). So: bi-encoder to recall, cross-encoder to
rank.

## Run it

```sh
uv run lessons/02_hybrid_rerank/run.py
RERANK_MODEL=BAAI/bge-reranker-base uv run lessons/02_hybrid_rerank/run.py   # GPU PC
```

## Results (25 single-hop questions)

| Setup | hit@5 | MRR@5 | Missed |
| --- | --- | --- | --- |
| dense (bge-small) | 0.96 | 0.74 | trailingDelta of 100 |
| BM25 | 0.96 | 0.64 | default recvWindow |
| hybrid (RRF) | **1.00** | 0.82 | - |
| hybrid + MiniLM rerank | 1.00 | 0.82 | - |
| hybrid + bge-reranker-base | 0.96 | **0.85** | error code for old timestamp |

What to learn from this:
- Dense and BM25 fail on *different* questions. That is the whole case for
  hybrid.
- The bigger reranker ranked better on average (MRR up) but dropped one
  question. **A better average can hide a regression** - always look at the
  misses, not only the score.
- 25 questions is small: one question = 0.04. Don't claim a win from one
  flip. More questions, or several runs, before deciding.

## Review questions

**Q: Why hybrid search?**
> Embeddings are good at meaning but weak on exact strings - error codes,
> endpoint names, ticker symbols. BM25 is the reverse. On my eval set each
> missed a different question; fused with RRF, both were found. At an
> exchange, exact IDs are everywhere, so I'd always start hybrid.

**Q: Why RRF and not a weighted sum of scores?**
> The scores are on different scales and their distributions shift per
> query. RRF only uses ranks, needs no tuning, and is robust. A weighted sum
> can win if you tune it on enough labelled data.

**Q: When is a reranker worth it?**
> When the right chunk is usually in the top 20-50 but not in the top 3-5,
> and you can afford ~tens of ms per query on GPU. It's the cheapest big
> precision gain. Not worth it if recall is the problem - a reranker can't
> find what retrieval never returned.

**Q: What would you do at scale?**
> ANN index (HNSW) in a vector store with built-in hybrid search (Qdrant,
> Milvus, OpenSearch), metadata filters (product, language, date) before
> ranking, cache frequent queries, rerank only the top 20-50 on GPU.
