"""Lesson 2: dense vs keyword vs hybrid (RRF) vs hybrid + cross-encoder rerank."""
from lab.chunk import load_chunks
from lab.embed import Embedder
from lab.evals import evaluate, load_golden
from lab.index import VectorIndex
from lab.retrieve import BM25, rerank, rrf

chunks = load_chunks()
dense, bm25 = VectorIndex(chunks, Embedder()), BM25(chunks)


def hybrid(q, k=5):
    return rrf([dense.search(q, 20), bm25.search(q, 20)], k)


def hybrid_rerank(q, k=5):
    return rerank(q, hybrid(q, 20), k)  # rerank a wider pool, keep the best k


rows = load_golden(multi_hop=False)
for name, fn in [("dense", dense.search), ("bm25", bm25.search),
                 ("hybrid", hybrid), ("hybrid+rerank", hybrid_rerank)]:
    print(f"\n== {name}")
    evaluate(fn, rows)
