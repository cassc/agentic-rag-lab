"""Local embedding models behind one interface. Pick with EMBED_MODEL."""
import os
from sentence_transformers import SentenceTransformer

BGE_QUERY = "Represent this sentence for searching relevant passages: "

MODELS = {
    # key: (hf name, dim, query prefix, query prompt_name, trust_remote_code)
    "bge-small": ("BAAI/bge-small-en-v1.5", 384, BGE_QUERY, None, False),
    "bge-base": ("BAAI/bge-base-en-v1.5", 768, BGE_QUERY, None, False),
    "nomic": ("nomic-ai/nomic-embed-text-v1.5", 768, "search_query: ", None, True),
    "gte-qwen2": ("Alibaba-NLP/gte-Qwen2-1.5B-instruct", 1536, "", "query", True),
}


class Embedder:
    def __init__(self, key=None):
        self.key = key or os.getenv("EMBED_MODEL", "bge-small")
        name, self.dim, self.prefix, self.prompt_name, trust = MODELS[self.key]
        self.model = SentenceTransformer(name, trust_remote_code=trust)
        self.doc_prefix = "search_document: " if self.key == "nomic" else ""

    def docs(self, texts):
        return self.model.encode([self.doc_prefix + t for t in texts], batch_size=16,
                                 normalize_embeddings=True, show_progress_bar=True)

    def query(self, text):
        if self.prompt_name:
            return self.model.encode([text], prompt_name=self.prompt_name,
                                     normalize_embeddings=True)[0]
        return self.model.encode([self.prefix + text], normalize_embeddings=True)[0]
