"""Keyword search (BM25), rank fusion (RRF), and a cross-encoder reranker."""
import os
import re
from functools import cache
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder


def tokens(text):
    return re.findall(r"[\w/\-.]+", text.lower())  # keeps -1021 and /api/v3/order whole


class BM25:
    def __init__(self, chunks):
        self.chunks = chunks
        self.bm25 = BM25Okapi([tokens(c.full) for c in chunks])

    def search(self, query, k=5):
        scores = self.bm25.get_scores(tokens(query))
        top = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [(self.chunks[i], float(scores[i])) for i in top]


def rrf(result_lists, k=5, c=60):
    """Reciprocal Rank Fusion: score = sum 1/(c + rank). Uses ranks only, so the
    very different BM25 and cosine score scales never need to be compared."""
    score, by_id = {}, {}
    for results in result_lists:
        for rank, (chunk, _) in enumerate(results):
            score[chunk.id] = score.get(chunk.id, 0) + 1 / (c + rank + 1)
            by_id[chunk.id] = chunk
    top = sorted(score, key=lambda i: -score[i])[:k]
    return [(by_id[i], score[i]) for i in top]


@cache
def reranker():
    # CPU demo: MiniLM (22M). GPU PC: RERANK_MODEL=BAAI/bge-reranker-base (278M).
    name = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L6-v2")
    return CrossEncoder(name, max_length=512)


def rerank(query, results, k=5):
    """A cross-encoder reads query and chunk together: slower, much sharper."""
    scores = reranker().predict([(query, c.full) for c, _ in results])
    ranked = sorted(zip(results, scores), key=lambda x: -x[1])[:k]
    return [(c, float(s)) for (c, _), s in ranked]


class Hybrid:
    """Dense + BM25 fused with RRF: the best single-shot retriever from lesson 2."""

    def __init__(self, chunks, embedder):
        from lab.index import VectorIndex
        self.dense, self.bm25 = VectorIndex(chunks, embedder), BM25(chunks)

    def search(self, query, k=5):
        return rrf([self.dense.search(query, 20), self.bm25.search(query, 20)], k)
