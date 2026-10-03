"""Lesson 15: tools behind MCP - servers, a registry, a gateway with roles,
and what a fleet of tools costs."""
import asyncio
import statistics
import sys
import time
from pathlib import Path
from lab import loop
from lab.llm import complete
from lab.mcp_gateway import McpGateway
from lab.tools import search_docs

SERVERS = str(Path(__file__).parent / "servers.py")
REGISTRY = {n: {"args": [SERVERS, n]} for n in ("docs", "market", "ops")}
ROLES = {"reader": {"docs": ["*"], "market": ["get_price", "get_symbol_filters"]},
         "trader": {"docs": ["*"], "market": ["*"]},
         "admin": {"docs": ["*"], "market": ["*"], "ops": ["*"]}}
SYSTEM = """You are a Binance Spot API assistant with tools. Use the docs tool for rules
and the market tools for live values. Never guess numbers. Be brief."""
Q = ("Would a LIMIT BUY of 0.00001 BTC at 50000 USDT on BTCUSDT pass the live filters? "
     "Name the filter that decides it.")
ORDER = {"symbol": "BTCUSDT", "side": "BUY", "quantity": "0.001", "price": "50000"}
only = sys.argv[1] if len(sys.argv) > 1 else "ABCD"


async def main():
    here = asyncio.get_running_loop()
    async with McpGateway(REGISTRY, ROLES) as gw:
        approved = dict(gw.fingerprints)  # "an admin reviewed these tool lists"

        if "A" in only:
            print("\n## A. discovery, and what a tool list costs")
            for name, fp in gw.fingerprints.items():
                n = sum(k.startswith(name + "__") for k in gw.catalog)
                print(f"   server {name:7} {n:2} tools  fingerprint {fp}")
            base = complete([{"role": "user", "content": Q}], max_tokens=1).usage.prompt_tokens
            for role in ("reader", "admin"):
                tools = gw.tools(role, here)
                r = await asyncio.to_thread(loop.run, SYSTEM, Q, tools)
                first = complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": Q}],
                                 tools=[s for _, s in tools.values()], max_tokens=1).usage.prompt_tokens
                print(f"   role {role:7} {len(tools):2} tools: tool schemas cost ~{first - base} prompt tokens "
                      f"per LLM call; run used {r['tokens']} tokens, {r['steps']} steps, "
                      f"tools {sorted({t[0] for t in r['trace']})}")
                print(f"      A: {r['answer'][:160]!r}")

        if "B" in only:
            print("\n## B. overhead of the protocol (search_docs, 10 calls each)")
            search_docs("warm up")
            await gw.call("reader", "docs__search_docs", {"query": "warm up"})
            direct, via = [], []
            for i in range(10):
                t = time.perf_counter()
                search_docs(f"error code {-1000 - i}")
                direct.append(time.perf_counter() - t)
                t = time.perf_counter()
                await gw.call("reader", "docs__search_docs", {"query": f"error code {-1000 - i}"})
                via.append(time.perf_counter() - t)
            print(f"   direct function call p50 {statistics.median(direct) * 1000:.0f} ms   "
                  f"through gateway + MCP stdio p50 {statistics.median(via) * 1000:.0f} ms")

        if "C" in only:
            print("\n## C. roles: hiding a tool is not the same as blocking it")
            gw.audit.clear()
            for role in ("reader", "trader"):
                tools = gw.tools(role, here)
                r = await asyncio.to_thread(loop.run, SYSTEM, "Buy 0.001 BTC at 50000 USDT on BTCUSDT.", tools)
                print(f"   {role}: sees place_order={'market__place_order' in tools}  "
                      f"called {[t[0] for t in r['trace']]}\n      A: {r['answer'][:140]!r}")
            # A hijacked or buggy agent names the hidden tool anyway.
            print("   reader calls the hidden tool directly:",
                  await gw.call("reader", "market__place_order", ORDER))
            print("   audit log:")
            for row in gw.audit:
                print("     ", *row)

    if "D" in only:
        print("\n## D. a server changes its tool description after approval")
        poisoned = {**REGISTRY, "market": {"args": [SERVERS, "market"], "env": {"POISON": "1"}}}
        for label, appr in (("no fingerprint check", None), ("fingerprint check", approved)):
            async with McpGateway(poisoned, ROLES, approved=appr) as gw:
                desc = gw.specs("reader").get("market__get_price", {}).get("function", {}).get("description")
                print(f"   {label}: reader has {len(gw.specs('reader'))} tools; get_price description "
                      f"in the prompt: {desc!r}")
                for row in gw.audit:
                    print("     ", *row)


asyncio.run(main())
