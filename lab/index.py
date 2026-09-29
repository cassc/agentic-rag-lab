"""Brute-force vector index: a numpy matrix and a dot product. Cached on disk."""
import hashlib
from pathlib import Path
import numpy as np

CACHE = Path(__file__).resolve().parent.parent / "data" / "index"


class VectorIndex:
    def __init__(self, chunks, embedder):
        self.chunks, self.emb = chunks, embedder
        fp = hashlib.sha1("".join(c.full for c in chunks).encode()).hexdigest()[:10]
        path = CACHE / f"{embedder.key}-{fp}.npy"  # copy this file from the GPU PC
        if path.exists():
            self.vecs = np.load(path)
        else:
            self.vecs = embedder.docs([c.full for c in chunks])
            CACHE.mkdir(parents=True, exist_ok=True)
            np.save(path, self.vecs)

    def search(self, query, k=5):
        scores = self.vecs @ self.emb.query(query)  # cosine, since vectors are normalized
        top = np.argsort(-scores)[:k]
        return [(self.chunks[i], float(scores[i])) for i in top]
