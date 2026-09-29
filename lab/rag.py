"""Grounded answer generation with citations."""
from lab.llm import chat

SYSTEM = """Answer only from the numbered sources. Cite each claim like [2].
If the sources do not contain the answer, say "Not in the sources." Do not guess."""


def context(chunks):
    return "\n\n".join(f"[{i + 1}] {c.full}" for i, c in enumerate(chunks))


def answer(question, chunks):
    return chat([{"role": "system", "content": SYSTEM},
                 {"role": "user", "content": f"Sources:\n{context(chunks)}\n\nQuestion: {question}"}],
                temperature=0)
