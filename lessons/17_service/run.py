"""Lesson 17: the runtime as a service. Load tests run in-process (no port):
async API, overload, idempotent POST, a noisy tenant. Then one real agent run.

  uv run lessons/17_service/run.py          # A-E
  uv run lessons/17_service/run.py serve    # real server on 127.0.0.1:8770
"""
import asyncio
import sys
import time
import httpx
from lab.service import Service

only = sys.argv[1] if len(sys.argv) > 1 else "ABCDE"
executed = []


def fake_agent(question, emit):
    """Stands in for an agent run: 0.2 s of waiting on the 'LLM'."""
    executed.append(question)
    time.sleep(0.2)
    return "ok"


def real_agent(question, emit):
    from lab import loop
    from lab.tools import TOOLS, spec

    def watch(name, fn):  # report each tool call as a progress event
        def wrapped(**args):
            emit("ToolCalled", tool=name, args=args)
            return fn(**args)
        return wrapped
    tools = {n: (watch(n, TOOLS[n][0]), TOOLS[n][1]) for n in ("search_docs", "get_price", "get_symbol_filters")}
    r = loop.run("You are a Binance Spot API assistant with tools. Never guess numbers. Be brief.",
                 question, tools)
    emit("Usage", steps=r["steps"], tokens=r["tokens"])
    return r["answer"]


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else float("nan")


async def post(client, tenant, i, key=None):
    """Returns (http status, POST seconds, run id)."""
    t = time.perf_counter()
    r = await client.post("/runs", json={"question": f"q{i}", "tenant": tenant},
                          headers={"Idempotency-Key": key} if key else {})
    return r.status_code, time.perf_counter() - t, r.json().get("run_id")


async def with_service(fn, agent=fake_agent, **kw):
    """Run fn against a fresh service, wait until all runs end, return (fn result, service)."""
    svc = Service(agent, **kw)
    svc.start()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=svc.app),
                                     base_url="http://lab", timeout=120) as client:
            out = await fn(client)
            while sum(svc.open.values()):  # times come from the server, so polling adds no load
                await asyncio.sleep(0.05)
            return out, svc
    finally:
        svc.shutdown()


def summary(label, res, svc):
    ok = [svc.runs[r[2]]["seconds"] for r in res if r[0] == 202]
    print(f"   {label}: accepted {len(ok)}, refused (429) {len(res) - len(ok)};  POST p95 "
          f"{pct([r[1] for r in res], .95) * 1000:.0f} ms;  run done p50 {pct(ok, .5):.2f}s "
          f"p95 {pct(ok, .95):.2f}s")


async def main():
    if "A" in only:
        print("\n## A. async API: 100 runs at once, 8 workers, each run 0.2 s")
        summary("100 at once", *await with_service(
            lambda c: asyncio.gather(*[post(c, "acme", i) for i in range(100)])))

    if "B" in only:
        print("\n## B. overload: 300 runs at once, 8 workers")
        for max_backlog in (None, 40):
            summary(f"max backlog {max_backlog}", *await with_service(
                lambda c: asyncio.gather(*[post(c, "acme", i) for i in range(300)]), max_backlog=max_backlog))

    if "C" in only:
        print("\n## C. the client retries the same POST 5 times")
        for key in (None, "order-42"):
            executed.clear()
            res, _ = await with_service(lambda c: asyncio.gather(*[post(c, "acme", 0, key) for _ in range(5)]))
            print(f"   Idempotency-Key={key}: run ids {len({r[2] for r in res})}, agent executed {len(executed)} times")

    if "D" in only:
        print("\n## D. noisy tenant: 'big' sends 120 runs, then 'small' sends 5")
        for tenant_limit in (None, 16):
            async def load(c):
                big = await asyncio.gather(*[post(c, "big", i) for i in range(120)])
                return big, await asyncio.gather(*[post(c, "small", i) for i in range(5)])
            (big, small), svc = await with_service(load, tenant_limit=tenant_limit)
            print(f"   tenant limit {tenant_limit}:")
            summary("  big  ", big, svc)
            summary("  small", small, svc)

    if "E" in only:
        print("\n## E. one real agent run through the API, with progress events")
        async def real(c):
            r = await c.post("/runs", json={"question": "What is the smallest price step for BTCUSDT "
                                            "right now, and which filter defines it?", "tenant": "acme"})
            print(f"   POST /runs -> {r.status_code} {r.json()}")
            run_id, t, seen = r.json()["run_id"], time.perf_counter(), 0
            while True:
                body = (await c.get(f"/runs/{run_id}")).json()
                for e in body["events"][seen:]:
                    extra = {k: v for k, v in e.items() if k not in ("seq", "stream", "version", "type")}
                    print(f"   +{time.perf_counter() - t:5.1f}s  {e['type']:12} {extra or ''}")
                seen = len(body["events"])
                if body["status"] in ("done", "failed"):
                    return print(f"   A: {body['answer'][:200]!r}")
                await asyncio.sleep(0.1)
        await with_service(real, agent=real_agent, workers=2)


if only == "serve":
    import uvicorn
    uvicorn.run(Service(real_agent, workers=4, max_backlog=50, tenant_limit=10).app,
                host="127.0.0.1", port=8770)  # loopback only
else:
    asyncio.run(main())
