"""Lesson 9: durable execution from scratch - event log, replay, retries,
idempotency keys, and the determinism rule."""
import sys
from collections import Counter
from lab.durable import RUNS, Crash, Ctx, NonDeterminism
from lab.evals import load_golden
from lab.llm import chat, chat_json
from lab.tools import search_docs

calls = Counter()  # how many times each real side effect ran


def plan(question):
    calls["llm"] += 1
    return chat_json([{"role": "user", "content":
                       f"Question: {question}\nWrite 2 short search queries for API docs. "
                       'Return JSON: {"queries": ["...", "..."]}'}])["queries"][:2]


def search(query):
    calls["search"] += 1
    return search_docs(query, k=3)


def answer(question, found):
    calls["llm"] += 1
    return chat([{"role": "user", "content": "Answer in two sentences, from the sources only.\n\n"
                  + "\n\n".join(found) + f"\n\nQuestion: {question}"}], temperature=0)


def research(ctx, question):
    """The workflow: only ctx.step() calls and pure logic. No direct I/O."""
    queries = ctx.step("plan", plan, question)
    found = [ctx.step(f"search:{i}", search, q) for i, q in enumerate(queries)]
    return ctx.step("answer", answer, question, found)


def research_v2(ctx, question):
    """A "small refactor": search before plan. Old logs no longer match."""
    found = [ctx.step("search:0", search, question)]
    ctx.step("plan", plan, question)
    return ctx.step("answer", answer, question, found)


def fresh(run_id):
    (RUNS / f"{run_id}.jsonl").unlink(missing_ok=True)
    return run_id


def show(title, ctx):
    print(f"   {title}: ran={ctx.ran} replayed={ctx.replayed} attempts={ctx.attempts} "
          f"side effects so far={dict(calls)}")


only = sys.argv[1] if len(sys.argv) > 1 else "ABCD"
q = load_golden(multi_hop=True)[0]["q"]

# A. Crash in the middle, then run the same code again.
if "A" in only:
    print("\n## A. crash and replay")
    rid = fresh("a-research")
    ctx = Ctx(rid, crash_after="search:0")
    try:
        research(ctx, q)
    except Crash as e:
        print(f"   CRASH: {e}")
    show("run 1", ctx)
    ctx = Ctx(rid)
    out = research(ctx, q)
    show("run 2", ctx)
    print(f"   A: {out[:200]}")
    ctx = Ctx(rid)
    research(ctx, q)
    show("run 3 (already done)", ctx)

# B. A flaky tool: fails twice, then works.
if "B" in only:
    print("\n## B. retries with backoff")
    for retries in (1, 3):
        fails = iter([True, True, False])

        def flaky():
            calls["flaky"] += 1
            if next(fails):
                raise TimeoutError("exchange API timed out")
            return "price 65000"

        ctx = Ctx(fresh(f"b-retries-{retries}"))
        try:
            print(f"   retries={retries}: {ctx.step('price', flaky, retries=retries)}"
                  f" after {ctx.attempts} attempts")
        except TimeoutError as e:
            print(f"   retries={retries}: workflow FAILED: {e}")

# C. Crash after the side effect but before the log write: the step runs again.
if "C" in only:
    print("\n## C. at-least-once steps need idempotency keys")
    for use_key in (False, True):
        orders, seen = [], {}

        def place(key):
            if key and key in seen:  # the exchange has seen this key: no new order
                return seen[key]
            orders.append("BUY 0.001 BTC")
            seen[key] = {"order_id": len(orders)}
            return seen[key]

        rid = fresh(f"c-order-{use_key}")
        for attempt in (1, 2):
            ctx = Ctx(rid, crash_before_record="order" if attempt == 1 else None)
            try:
                ctx.step("order", place, ctx.key("order") if use_key else None)
            except Crash:
                pass
        print(f"   idempotency key={use_key}: orders on the exchange = {len(orders)}")

# D. The workflow code must ask for the same steps in the same order.
if "D" in only:
    print("\n## D. determinism")
    rid = fresh("d-version")
    try:
        research(Ctx(rid, crash_after="search:0"), q)
    except Crash:
        pass
    try:
        research_v2(Ctx(rid), q)
    except NonDeterminism as e:
        print(f"   new code on an old log: NonDeterminism: {e}")
