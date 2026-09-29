"""Lesson 6: the agent loop with native tool calling, no framework.
The model picks tools; we run them and feed results back until it answers."""
import json
from lab.evals import load_golden
from lab.judge import judge, pmap
from lab.llm import complete
from lab.tools import TOOLS, run_tool

SYSTEM = """You are a Binance Spot API assistant with tools.
Use search_docs for rules and definitions, and the market tools for live values.
Never guess numbers. Cite doc sources by their id, e.g. (filters#12).
When you have everything, answer without calling a tool.
If the docs don't cover it, say "Not in the sources." """

READ_ONLY = ["search_docs", "get_price", "get_symbol_filters"]  # no place_order here


def agent(question, max_steps=6):
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    trace = []
    for step in range(max_steps):  # the loop always has a hard limit
        m = complete(msgs, tools=[TOOLS[n][1] for n in READ_ONLY], temperature=0).choices[0].message
        if not m.tool_calls:
            return m.content, step + 1, trace  # no tool call = final answer
        msgs.append({"role": "assistant", "content": m.content or "",
                     "tool_calls": [tc.model_dump() for tc in m.tool_calls]})
        for tc in m.tool_calls:  # the model may ask for several tools at once
            args = json.loads(tc.function.arguments)
            out = run_tool(tc.function.name, args)
            trace.append((tc.function.name, args, out.startswith("ERROR")))
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": out[:6000]})
    return "Stopped: step limit reached.", max_steps, trace


LIVE = [
    ("What is the BTCUSDT price right now, and what is the smallest price step allowed?",
     {"get_price", "get_symbol_filters"}),
    ("Would a LIMIT BUY of 0.00001 BTC at 50000 USDT on BTCUSDT pass the live filters? "
     "Name the filter that decides it and explain its rule from the docs.",
     {"get_symbol_filters", "search_docs"}),
    ("Can I place a trailing stop on ETHUSDT with trailingDelta 5? Check the live filter "
     "and explain what 5 means.", {"get_symbol_filters", "search_docs"}),
    ("What are the live trading filters for the symbol FAKECOINUSDT?", {"get_symbol_filters"}),
]

print("== live tasks (tools + docs)")
for q, need in LIVE:
    ans, steps, trace = agent(q)
    used = {t[0] for t in trace}
    print(f"\nQ: {q}\n   steps={steps} tools={[(t[0], t[1]) for t in trace]}"
          f"\n   needed tools used: {need <= used}   tool errors: {sum(t[2] for t in trace)}"
          f"\n   A: {ans[:400]}")

rows = load_golden(multi_hop=True)
res = pmap(lambda r: agent(r["q"]), rows)
ok = [judge(r, a) for r, (a, _, _) in zip(rows, res)]
print(f"\n== multi-hop golden: correct {sum(ok)}/{len(rows)}, "
      f"steps/q {sum(s for _, s, _ in res) / len(rows):.1f}, "
      f"searches/q {sum(len(t) for _, _, t in res) / len(rows):.1f}")
for r, (a, s, t), good in zip(rows, res, ok):
    print(f"  {'ok ' if good else 'BAD'} steps={s} {[x[1].get('query') for x in t]}")
