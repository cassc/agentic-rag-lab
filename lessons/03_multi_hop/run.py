"""Lesson 3: multi-hop. One retrieval vs decomposition vs an iterative loop."""
import time
from lab.chunk import load_chunks
from lab.embed import Embedder
from lab.evals import found_all, load_golden
from lab.judge import judge, pmap
from lab.llm import chat_json
from lab.rag import answer, context
from lab.retrieve import Hybrid

retr = Hybrid(load_chunks(), Embedder())

DECOMPOSE = """Split the user's question into the smallest set (1-4) of standalone
search queries, one fact each. Keep exact names, codes and parameters.
Return JSON: {"queries": ["...", "..."]}"""

STEP = """You research a question in the Binance Spot API docs, one search at a time.
Read the new sources, update your notes (facts + source ids), then decide:
if a fact is still missing, write the next search query for it; otherwise null.
Return JSON: {"notes": "...", "next_query": "..." or null}"""


def merge(lists):
    """Interleave ranked lists (1st of each, then 2nd of each...) and drop duplicates."""
    out, seen = [], set()
    for rank in range(max(map(len, lists))):
        for lst in lists:
            if rank < len(lst) and lst[rank].id not in seen:
                seen.add(lst[rank].id)
                out.append(lst[rank])
    return out


def single(q, k):
    return [c for c, _ in retr.search(q, k)], 0, [q]


def decomposed(q, k=4):
    subs = chat_json([{"role": "system", "content": DECOMPOSE},
                      {"role": "user", "content": q}])["queries"]
    return merge([[c for c, _ in retr.search(s, k)] for s in subs]), 1, subs


def iterative(q, k=4, max_hops=3):
    seen, notes, query, trace = {}, "", q, []
    for _ in range(max_hops):  # hard limit: loops must always terminate
        trace.append(query)
        new = [c for c, _ in retr.search(query, k) if c.id not in seen]
        seen |= {c.id: c for c in new}
        r = chat_json([{"role": "system", "content": STEP},
                       {"role": "user", "content": f"Question: {q}\nNotes so far: {notes or '-'}\n"
                                                   f"New sources:\n{context(new)}"}])
        notes, query = r["notes"], r.get("next_query")
        if not query:
            break
    return list(seen.values()), len(trace), trace


METHODS = [("single k=5", lambda q: single(q, 5)),
           ("single k=10", lambda q: single(q, 10)),  # same chunk budget as the others
           ("decomposed", decomposed),
           ("iterative", iterative)]

rows = load_golden(multi_hop=True)
for name, method in METHODS:
    def run(row):
        t = time.time()
        chunks, calls, trace = method(row["q"])
        ans = answer(row["q"], chunks)
        return found_all(row, chunks), judge(row, ans), calls + 1, len(chunks), time.time() - t, trace

    res = pmap(run, rows)
    n = len(rows)
    print(f"\n== {name}: hops found {sum(r[0] for r in res)}/{n}, "
          f"answer correct {sum(r[1] for r in res)}/{n}, "
          f"LLM calls/q {sum(r[2] for r in res) / n:.1f}, "
          f"chunks/q {sum(r[3] for r in res) / n:.1f}, "
          f"sec/q {sum(r[4] for r in res) / n:.1f}")
    if name in ("decomposed", "iterative"):
        for row, r in zip(rows, res):
            print(f"  {'ok ' if r[1] else 'BAD'} {row['q'][:60]}")
            for s in r[5]:
                print(f"       -> {s}")
