"""Claim-level groundedness check (Self-RAG's "is it supported?" step)."""
from lab.llm import chat_json
from lab.rag import context

VERIFY = """Check an answer against numbered sources.
Split the answer into factual claims. A claim is supported only if a source
states it (not implied by general knowledge). A refusal like "Not in the
sources" has no claims.
Return JSON: {"claims": [{"claim": "...", "supported": true or false}],
"answers_question": true or false,
"missing": "a search query for what is still needed, or null"}"""


def verify(question, answer, chunks):
    r = chat_json([{"role": "system", "content": VERIFY},
                   {"role": "user", "content": f"Sources:\n{context(chunks)}\n\n"
                                               f"Question: {question}\nAnswer: {answer}"}])
    r["grounded"] = all(c["supported"] for c in r.get("claims", []))
    return r
