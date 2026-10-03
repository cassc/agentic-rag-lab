"""Lesson 12: one agent vs a supervisor with two workers, on the same tasks.
Then two failure modes: a thin handoff, and workers that run one by one."""
import sys
import time
from lab import loop
from lab.evals import load_golden
from lab.judge import RUBRIC, judge, pmap
from lab.multi import Team
from lab.tools import TOOLS

SINGLE = """You are a Binance Spot API assistant with tools.
Use search_docs for rules and definitions, and the market tools for live values.
Never guess numbers. Cite doc sources by their id, e.g. (filters#12).
If the docs don't cover it, say "Not in the sources." """
READ_ONLY = {n: TOOLS[n] for n in ("search_docs", "get_price", "get_symbol_filters")}

MIXED = [  # need live data AND docs. References hold for BTCUSDT's long-standing filters.
    {"q": "Would a LIMIT BUY of 0.00001 BTC at 50000 USDT on BTCUSDT pass the live filters? "
          "Name the filter that decides it and explain its rule from the docs.",
     "answer": "No. It fails the NOTIONAL filter: 0.00001 * 50000 = 0.5 USDT, below the "
               "live minimum notional of 5 USDT."},
    {"q": "What is the smallest price step for BTCUSDT right now, and which filter in the "
          "docs defines it?",
     "answer": "tickSize 0.01, defined by PRICE_FILTER."},
    {"q": "What are the live trading filters for the symbol FAKECOINUSDT?",
     "answer": "None can be given: the symbol does not exist / the request fails as an "
               "invalid symbol."},
]
TASKS = load_golden(multi_hop=True) + MIXED


def single(row):
    t = time.time()
    r = loop.run(SINGLE, row["q"], READ_ONLY)
    return {**r, "llm_calls": r["steps"], "total_tokens": r["tokens"], "sec": time.time() - t}


def team(**kw):
    def fn(row):
        t = time.time()
        return {**Team(**kw).run(row["q"]), "sec": time.time() - t}
    return fn


def report(name, fn):
    res = pmap(fn, TASKS, workers=4)
    ok = [judge(row, r["answer"], RUBRIC) for row, r in zip(TASKS, res)]
    n = len(TASKS)
    print(f"{name:26} correct {sum(ok)}/{n}   LLM calls/task {sum(r['llm_calls'] for r in res) / n:.1f}"
          f"   tokens/task {sum(r['total_tokens'] for r in res) / n:.0f}"
          f"   top-agent peak context {sum(r['peak'] for r in res) / n:.0f}"
          f"   s/task {sum(r['sec'] for r in res) / n:.1f}")
    for row, r, good in zip(TASKS, res, ok):
        if not good:
            print(f"    BAD: {row['q'][:70]} -> {r['answer'][:150]!r}")
    return res


only = sys.argv[1] if len(sys.argv) > 1 else "ABC"
print(f"{len(TASKS)} tasks: 5 multi-hop doc questions + 3 that need docs and live data\n")
if "A" in only:
    report("single agent", single)
    res = report("team, full brief", team())
    print("    example handoffs:")
    for name, task, r in res[5]["handoffs"]:
        print(f"      -> {name}: {task[:150]!r}  ({r['steps']} steps, {r['tokens']} tokens)")
if "B" in only:
    res = report("team, 4-word brief", team(brief="short"))
    for name, task, r in res[5]["handoffs"]:
        print(f"      -> {name}: {task!r}")
if "C" in only:
    report("team, workers one by one", team(parallel=False))
