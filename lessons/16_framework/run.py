"""Lesson 16: the same agent on two runtimes behind one interface - our own
loop and LangGraph. Contract tests, a side-by-side eval, and what the
framework gives for free (checkpoints, pause for approval)."""
import sys
import time
import uuid
from lab.evals import load_golden
from lab.judge import RUBRIC, judge, pmap
from lab.runtime import LangGraph, Result, Scratch
from lab.tools import TOOLS

SYSTEM = """You are a Binance Spot API assistant with tools.
Use search_docs for rules and definitions, and the market tools for live values.
Never guess numbers. Cite doc sources by their id, e.g. (filters#12).
If the docs don't cover it, say "Not in the sources." """
READ_ONLY = {n: TOOLS[n] for n in ("search_docs", "get_price", "get_symbol_filters")}
RUNTIMES = {"scratch": Scratch, "langgraph": LangGraph}
only = sys.argv[1] if len(sys.argv) > 1 else "ABC"


def run(rt, question):
    """LangGraph keeps state per thread id. Give every run its own."""
    return rt.run(question, uuid.uuid4().hex) if isinstance(rt, LangGraph) else rt.run(question)


# A. Contract tests: what every runtime must do, whatever is inside.
def contract(make):
    yield "returns a Result with an answer", (lambda r: isinstance(r, Result) and bool(r.answer))(
        run(make(SYSTEM, READ_ONLY), "What does error -1021 mean?"))
    r = run(make(SYSTEM, READ_ONLY, max_steps=1), "What is the default recvWindow and the max?")
    yield "stops at the step limit", r.steps == 1 and r.answer.startswith("Stopped")
    r = run(make(SYSTEM, READ_ONLY), "What are the live trading filters for FAKECOINUSDT?")
    yield "a tool error does not crash the run", bool(r.answer) and len(r.trace) >= 1
    r = run(make(SYSTEM, READ_ONLY), "What is the BTCUSDT price now?")
    yield "the trace names the tools used", [t[0] for t in r.trace] == ["get_price"]


if "A" in only:
    print("\n## A. contract tests")
    for name, make in RUNTIMES.items():
        for what, ok in contract(make):
            print(f"   {name:10} {'pass' if ok else 'FAIL'}  {what}")

# B. Same tasks, same judge, both runtimes.
if "B" in only:
    print("\n## B. side by side (5 multi-hop + 5 single-hop questions)")
    rows = load_golden(multi_hop=True) + load_golden(multi_hop=False)[:5]
    for name, make in RUNTIMES.items():
        rt = make(SYSTEM, READ_ONLY)

        def timed(row):
            t = time.time()
            return run(rt, row["q"]), time.time() - t

        res = pmap(timed, rows, workers=4)
        good = sum(judge(row, r.answer, RUBRIC) for row, (r, _) in zip(rows, res))
        n = len(rows)
        print(f"   {name:10} correct {good}/{n}   steps/q {sum(r.steps for r, _ in res) / n:.1f}"
              f"   tokens/q {sum(r.tokens for r, _ in res) / n:.0f}   s/q {sum(s for _, s in res) / n:.1f}")

# C. What the framework gives for free: checkpoints and a pause for a human.
if "C" in only:
    print("\n## C. LangGraph: pause before place_order, then resume from the checkpoint")
    tools = {**READ_ONLY, "place_order": TOOLS["place_order"]}
    rt = LangGraph(SYSTEM, tools, approve=["place_order"])
    cfg = {"configurable": {"thread_id": "order-1"}}
    rt.run("Buy 0.001 BTC at 50000 USDT on BTCUSDT. Do not check anything, just place it.", "order-1")
    state = rt.app.get_state(cfg)
    call = state.values["msgs"][-1]["tool_calls"][0]["function"]
    print(f"   paused before node {state.next}; waiting call: {call['name']} {call['arguments']}")
    print(f"   checkpoints saved so far: {len(list(rt.app.get_state_history(cfg)))}")
    r = rt.resume("order-1")  # "the human clicked approve"; could be days later, in another process
    print(f"   resumed: tools run {[t[0] for t in r.trace]}  A: {r.answer[:120]!r}")
    print(f"   checkpoints in the thread: {len(list(rt.app.get_state_history(cfg)))}")
