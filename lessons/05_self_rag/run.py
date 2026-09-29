"""Lesson 5: Self-RAG style reflection with prompts: decide -> retrieve ->
draft -> verify claims -> retrieve the gap and redraft (max 2 rounds)."""
from lab.evals import load_golden
from lab.judge import judge, pmap, refused
from lab.llm import chat, chat_json
from lab.rag import SYSTEM, answer, context
from lab.tools import retriever
from lab.verify import verify

DECIDE = """Does answering this question need facts from the Binance Spot API
docs (limits, fields, errors, rules), or is it general knowledge / arithmetic?
Return JSON: {"retrieve": true or false}"""

REDRAFT = SYSTEM + """
Your previous draft had problems: {problems}
Write a new answer. Drop any claim the sources do not state."""

NO_RETRIEVAL = ["What is 17 * 3?", "What does the abbreviation API stand for?",
                "Translate 'order book' into French."]


def decide(q):
    return chat_json([{"role": "system", "content": DECIDE},
                      {"role": "user", "content": q}])["retrieve"]


def baseline(q):
    found = [c for c, _ in retriever().search(q, 5)]
    ans = answer(q, found)
    return ans, verify(q, ans, found), None, 1


def self_rag(q, rounds=2):
    calls = 1
    if not decide(q):  # adaptive retrieval: skip the search when not needed
        return chat([{"role": "user", "content": q}]), {"grounded": True}, None, 2
    found = [c for c, _ in retriever().search(q, 5)]
    ans, first = answer(q, found), None
    calls += 1
    for i in range(rounds + 1):
        v = verify(q, ans, found)
        calls += 1
        first = first or v
        if v["grounded"] and v.get("answers_question", True):
            break  # stop condition: every claim supported and the question answered
        if i == rounds:
            break  # budget spent: keep the last (verified) state
        if v.get("missing"):
            ids = {c.id for c in found}
            found += [c for c, _ in retriever().search(v["missing"], 3) if c.id not in ids]
        bad = [c["claim"] for c in v.get("claims", []) if not c["supported"]]
        problems = f"unsupported claims {bad}; missing: {v.get('missing')}"
        ans = chat([{"role": "system", "content": REDRAFT.format(problems=problems)},
                    {"role": "user", "content": f"Sources:\n{context(found)}\n\nQuestion: {q}"}],
                   temperature=0)
        calls += 1
    return ans, v, first, calls


rows = load_golden(multi_hop=None) + load_golden(unanswerable=True)
print("Adaptive retrieval: skip on general questions?",
      [not decide(q) for q in NO_RETRIEVAL], "| wrongly skipped doc questions:",
      sum(not d for d in pmap(decide, [r["q"] for r in rows])), f"/ {len(rows)}")

for name, fn in [("baseline (hybrid top 5, one draft)", baseline), ("self-RAG", self_rag)]:
    def run(row):
        ans, v, first, calls = fn(row["q"])
        return judge(row, ans), refused(ans), v["grounded"], (first or v)["grounded"], calls, ans

    res = pmap(run, rows)
    ok = sum(r[0] for r in res)
    print(f"\n== {name}\ncorrect {ok}/{len(rows)}  grounded: first draft "
          f"{sum(r[3] for r in res)}/{len(rows)} -> final {sum(r[2] for r in res)}/{len(rows)}  "
          f"LLM calls/q {sum(r[4] for r in res) / len(rows):.1f} (plus judge)")
    for row, r in zip(rows, res):
        if not r[0]:
            print(f"  BAD {row['q'][:70]}\n      -> {r[5][:140]!r}")
