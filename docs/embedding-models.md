# Embedding and reranker models

All models run locally through `sentence-transformers`. Pick one with
`EMBED_MODEL` in `.env`. Each model gets its own cache file in `data/index/`,
so you can switch models without rebuilding the others.

## Embedding models

| Key | Model | Dims | Params | Max tokens | MTEB (en) | License | Where to run |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `bge-small` | BAAI/bge-small-en-v1.5 | 384 | 33M | 512 | ~62 | MIT | CPU (default demo) |
| `bge-base` | BAAI/bge-base-en-v1.5 | 768 | 110M | 512 | 63.6 | MIT | CPU ok, GPU fast |
| `nomic` | nomic-ai/nomic-embed-text-v1.5 | 768 (Matryoshka: 512/256/128/64) | 137M | 8192 | 62.3 | Apache-2.0 | CPU ok, GPU fast |
| `gte-qwen2` | Alibaba-NLP/gte-Qwen2-1.5B-instruct | 1536 | 1.5B | 32k | 67.2 | Apache-2.0 | GPU |

Rejected: `Qwen/Qwen3-Embedding-4B` can output 1536 dims (Matryoshka), but at
4B params it is too slow without a GPU and too big for the gain here.

### Usage notes (each model is used a little differently)

- **BGE**: add the query instruction
  `"Represent this sentence for searching relevant passages: "` to queries
  only, not to documents. Normalize vectors.
- **nomic**: needs a task prefix on *both* sides: `search_query: ` and
  `search_document: `. Needs `trust_remote_code=True`.
- **gte-Qwen2**: queries use `prompt_name="query"` (an instruction prompt
  stored with the model); documents have no prompt. Needs
  `trust_remote_code=True`. The model card asks for `flash_attn` on GPU.
  Not tested on this CPU machine yet - run it on the GPU PC first.

In `lab/embed.py` all of this sits behind `Embedder.docs()` and
`Embedder.query()`.

## Reranker models (cross-encoders)

| Model | Params | Where | Notes |
| --- | --- | --- | --- |
| cross-encoder/ms-marco-MiniLM-L6-v2 | 22M | CPU default | Fast. Trained on web search (MS MARCO). |
| BAAI/bge-reranker-base | 278M | GPU | Better on this corpus (see below), but ~9 min on CPU for the eval. |

Pick with `RERANK_MODEL`.

## Results on this corpus (25 single-hop questions, top 5)

| Setup | hit@5 | MRR@5 |
| --- | --- | --- |
| dense, bge-small | 0.96 | 0.74 |
| BM25 | 0.96 | 0.64 |
| hybrid (RRF) | 1.00 | 0.82 |
| hybrid + MiniLM rerank | 1.00 | 0.82 |
| hybrid + bge-reranker-base | 0.96 | 0.85 |

TODO on the GPU PC: fill in rows for `bge-base`, `nomic`, `gte-qwen2`.

## Key points

- **Dimensions are not quality.** More dims cost more memory and slower
  search. 1536 floats = 6 KB per chunk; 10M chunks = 60 GB before any index
  overhead. Compare models on *your* eval set, not on dims or MTEB alone.
- **Matryoshka embeddings** (nomic, Qwen3) let you cut vectors short (768 to
  256) with a small quality loss. Useful for a cheap first pass, then
  re-score with full vectors.
- **Changing the embedding model means re-embedding everything.** Vectors
  from different models are not comparable. Plan for it: version the index,
  build the new one beside the old, switch after the eval passes.
- **Instruction prefixes matter.** Forgetting BGE's query prefix or nomic's
  task prefix quietly lowers recall. It's a common production bug.
- **Why run locally?** Data privacy (no text leaves the network), no per-token
  cost, stable versions. Cost: you run the GPU yourself.

## Sources

- [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5)
- [BAAI/bge-base-en-v1.5](https://huggingface.co/BAAI/bge-base-en-v1.5)
- [nomic-ai/nomic-embed-text-v1.5](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)
- [Alibaba-NLP/gte-Qwen2-1.5B-instruct](https://huggingface.co/Alibaba-NLP/gte-Qwen2-1.5B-instruct)
- [Qwen/Qwen3-Embedding-4B](https://huggingface.co/Qwen/Qwen3-Embedding-4B)
- [BAAI/bge-reranker-base](https://huggingface.co/BAAI/bge-reranker-base)
- [cross-encoder/ms-marco-MiniLM-L6-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2)
