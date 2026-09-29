"""Lesson 4: Corrective RAG. Grade what you retrieved before you trust it."""
import time
from lab.chunk import load_chunks
from lab.embed import Embedder
from lab.evals import load_golden
from lab.index import VectorIndex
from lab.judge import judge, pmap, refused
from lab.llm import chat_json
from lab.rag import answer, context
from lab.retrieve import BM25, rrf

chunks = load_chunks()
dense, bm25 = VectorIndex(chunks, Embedder()), BM25(chunks)

GRADE = """For each numbered source, decide if it contains information that helps
answer the question (directly or as a needed part). Be strict: same topic
but not the asked fact = not relevant.
Return JSON: {"relevant": [source numbers]}"""

REWRITE = """The search below found nothing useful. Rewrite the question as a
keyword search query for the Binance Spot API docs: exact field names, enum
values, endpoint paths, error codes. Return JSON: {"query": "..."}"""


def grade(q, found):
    r = chat_json([{"role": "system", "content": GRADE},
                   {"role": "user", "content": f"Question: {q}\n\nSources:\n{context(found)}"}])
    return [found[i - 1] for i in r["relevant"] if 1 <= i <= len(found)]


def naive(q):
    return answer(q, [c for c, _ in dense.search(q, 3)]), 1


def crag(q, max_tries=2):
    found, calls = [c for c, _ in dense.search(q, 3)], 0
    for attempt in range(max_tries):
        good = grade(q, found)
        calls += 1
        if good:
            # "Knowledge refinement": answer from the relevant chunks only, drop noise.
            return answer(q, good), calls + 1
        if attempt + 1 < max_tries:
            # Correct: rewrite the query and search a different, wider source.
            new_q = chat_json([{"role": "system", "content": REWRITE},
                               {"role": "user", "content": q}])["query"]
            calls += 1
            found = [c for c, _ in rrf([dense.search(new_q, 20), bm25.search(new_q, 20)], 5)]
    return "Not in the sources.", calls  # give up honestly instead of guessing


answerable, unanswerable = load_golden(multi_hop=False), load_golden(unanswerable=True)
for name, method in [("naive (dense top 3)", naive), ("CRAG", crag)]:
    def run(row):
        t = time.time()
        ans, calls = method(row["q"])
        print(".", end="", flush=True)
        return judge(row, ans), refused(ans), calls, time.time() - t, ans

    a, u = pmap(run, answerable), pmap(run, unanswerable)
    every = a + u
    print(f"\n== {name}")
    print(f"answerable correct     {sum(r[0] for r in a)}/{len(a)}  (wrongly refused {sum(r[1] for r in a)})")
    print(f"unanswerable refused   {sum(r[0] for r in u)}/{len(u)}")
    print(f"LLM calls/q {sum(r[2] for r in every) / len(every):.1f} (plus judge), "
          f"sec/q {sum(r[3] for r in every) / len(every):.1f}")
    for row, r in zip(answerable + unanswerable, every):
        if not r[0]:
            print(f"  BAD {row['q'][:70]}\n      -> {r[4][:150]!r}")
