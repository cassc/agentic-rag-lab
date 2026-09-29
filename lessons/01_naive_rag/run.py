"""Lesson 1: naive RAG = chunk, embed, retrieve once, answer.

uv run lessons/01_naive_rag/run.py                 # retrieval eval only
uv run lessons/01_naive_rag/run.py "question?"     # also answer with the LLM
"""
import sys
from lab.chunk import load_chunks
from lab.embed import Embedder
from lab.evals import evaluate, load_golden
from lab.index import VectorIndex
from lab.rag import answer

index = VectorIndex(load_chunks(), Embedder())
print(f"model={index.emb.key} dim={index.emb.dim} chunks={len(index.chunks)}\n")

print("Single-hop questions:")
evaluate(index.search, load_golden(multi_hop=False))
print("\nMulti-hop questions (all hops must be in the top 5):")
evaluate(index.search, load_golden(multi_hop=True))

if len(sys.argv) > 1:
    q = sys.argv[1]
    hits = index.search(q, 5)
    for c, s in hits:
        print(f"  {s:.3f}  {c.id}  {c.heading[:70]}")
    print("\n" + answer(q, [c for c, _ in hits]))
