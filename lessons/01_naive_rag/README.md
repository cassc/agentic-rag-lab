# Lesson 1 - Naive RAG

Diagram: `L1_Naive` in [docs/diagrams](../../docs/diagrams/README.md).

## The idea in 4 steps

1. **Chunk** the docs into small pieces (here: split by Markdown heading,
   packed up to 1200 chars).
2. **Embed** each chunk into a vector. Similar meaning -> nearby vectors.
3. **Retrieve**: embed the question, take the 5 closest chunks (cosine).
4. **Generate**: give the LLM those chunks and ask it to answer only from
   them, with citations.

It is "naive" because it retrieves **once**, with the user's exact words,
and trusts whatever comes back.

## Run it

```sh
uv run lessons/01_naive_rag/run.py
uv run lessons/01_naive_rag/run.py "What is the default recvWindow?"   # needs LLM_API_KEY
```

## What the numbers show (bge-small, CPU)

| Question type | hit@5 | MRR@5 |
| --- | --- | --- |
| single-hop (25) | 0.96 | 0.74 |
| multi-hop (5) | 0.40 | 0.12 |

Single-hop works. **Multi-hop fails**: one query can't pull two facts from
two different docs. That gap is why agentic RAG exists (lessons 3-5).

## Things in the code worth explaining

- **Contextual chunks** (`Chunk.full`): each chunk carries
  `[doc] Heading > Sub-heading`. A chunk that only says "UTC" is useless; with
  its heading "Which time zone does interval DAY use?" it becomes findable.
- **Normalized vectors**: then cosine = dot product, so search is one matrix
  multiply. Brute force is fine up to ~1M chunks; beyond that use an ANN index
  (HNSW in Qdrant/Milvus).
  - `lab/index.py`: `self.vecs @ q` is `(N, d) @ (d,) -> (N,)`, one score per
    chunk.
  - `cos(a, b) = a·b / (|a| |b|)`. Both sides use `normalize_embeddings=True`,
    so `|a| = |b| = 1` and cosine is just `a·b`.
  - The score is cosine **similarity** (-1 to 1, higher = closer), not
    distance (`1 - similarity`, lower = closer). So we sort by `-scores`.
  - If the vectors are not normalized (old cache, other model), the score is a
    raw dot product and long vectors win. Delete `data/index/` to rebuild.
- **Grounding prompt** (`lab/rag.py`): "answer only from sources, cite [n],
  say 'Not in the sources' otherwise". This is the cheapest guard against
  hallucination.
- **Eval by phrase, not chunk ID**: a hit = the right doc *and* a key phrase
  inside the chunk. Chunk IDs change when you change chunking; phrases don't.
  So you can compare chunking strategies fairly.

## Review questions

**Q: Walk me through a basic RAG pipeline.**
> Offline: clean the docs, chunk them, embed each chunk, store the vectors.
> Online: embed the question, get the top-k nearest chunks, put them in the
> prompt, and tell the model to answer only from them with citations. Then
> measure: retrieval recall on a golden set, and whether answers are grounded.

**Q: How do you choose chunk size?**
> It's a trade-off. Small chunks are precise but lose context; big chunks
> keep context but add noise and cost tokens. I start from the document
> structure - split on headings - then tune the size against the eval set.
> I also prepend the heading path to each chunk so small chunks keep their
> context.

**Q: What are the main ways naive RAG fails?**
> 1. Retrieval misses: wording mismatch, or exact IDs that embeddings blur
> (fix: hybrid search). 2. Wrong ranking: the right chunk is at rank 8 (fix:
> reranker). 3. Multi-fact questions: one query can't find two facts (fix:
> decomposition, multi-hop). 4. The model ignores or goes beyond the context
> (fix: grounding prompt, citations, a groundedness check).

**Q: hit@k vs MRR?**
> hit@k (recall@k here): is the right chunk anywhere in the top k? MRR: how
> high is it - 1/rank, averaged. Recall matters for whether the answer is
> *possible*; MRR matters when you pass only the top few chunks to the LLM.
