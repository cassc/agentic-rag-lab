"""Lesson 10: an LLM gateway - failover, circuit breaker, model routing,
structured output, streaming."""
import json
import random
import sys
import time
from typing import Literal
from pydantic import BaseModel, Field, ValidationError
from lab.gateway import AllProvidersFailed, Gateway, provider
from lab.judge import pmap

only = sys.argv[1] if len(sys.argv) > 1 else "ABCDE"
PING = [{"role": "user", "content": "Reply with the single word: ok"}]


def success(gw, n=20):
    ok = 0
    for _ in range(n):
        try:
            ok += gw.chat(PING, think=False).strip().lower().startswith("ok")
        except AllProvidersFailed:
            pass
    return f"{ok}/{n} ok   used={dict(gw.used)}"


# A. Retries fix short errors. Only a second provider fixes an outage.
if "A" in only:
    print("\n## A. retry vs fallback (the failures are simulated, the calls are real)")
    for label, fail in (("primary fails 50% of calls", 0.5), ("primary is down", 1.0)):
        random.seed(1)
        print(f"   {label}")
        print("     no retry, no fallback:", success(Gateway([provider("flash", fail=fail)])))
        print("     2 retries:            ", success(Gateway([provider("flash", fail=fail)], retries=2)))
        print("     fallback provider:    ", success(Gateway([provider("flash", fail=fail),
                                                              provider("flash-backup")])))

# B. A hanging provider costs its full timeout on every request, until the breaker opens.
if "B" in only:
    print("\n## B. circuit breaker (primary hangs 2 s, then times out)")
    for breaker in (None, 2):
        gw = Gateway([provider("flash-backup", hang=2), provider("flash")], breaker=breaker)
        t = time.time()
        for _ in range(10):
            gw.chat(PING, think=False)
        print(f"   breaker={breaker}: 10 requests in {time.time() - t:.1f}s, "
              f"{gw.wasted:.0f}s of it waiting on the dead provider   errors={dict(gw.errors)}")


# C. Routing. Task: does this order pass the filters? Graded by exact match.
class Check(BaseModel):
    ok: bool
    filter: Literal["PRICE_FILTER", "LOT_SIZE", "NOTIONAL"] | None


RULES = """Filters for BTCUSDT:
PRICE_FILTER: minPrice 0.01, maxPrice 1000000, tickSize 0.01 (price must be a multiple of tickSize)
LOT_SIZE: minQty 0.00001, maxQty 9000, stepSize 0.00001 (quantity must be a multiple of stepSize)
NOTIONAL: minNotional 5 (price * quantity must be >= 5)
Does the LIMIT order pass? Return JSON only: {"ok": true or false, "filter": the one failing
filter name or null}"""
ORDERS = [  # (quantity, price, passes, failing filter)
    ("0.00001", "50000", False, "NOTIONAL"), ("0.001", "50000.005", False, "PRICE_FILTER"),
    ("0.000125", "60000", False, "LOT_SIZE"), ("0.0002", "30000", True, None),
    ("0.00016", "31249.99", False, "NOTIONAL"), ("0.00016", "31250.00", True, None),
    ("10000", "50000", False, "LOT_SIZE"), ("0.5", "1200000", False, "PRICE_FILTER"),
    ("0.00011", "45454.55", True, None), ("0.003", "2000.10", True, None),
    ("0.00037", "13513.51", False, "NOTIONAL"), ("0.00037", "13513.52", True, None),
]


def check(gw, order, **kw):
    """Returns (answer or None, tokens, seconds)."""
    t = time.time()
    r = gw.complete([{"role": "system", "content": RULES},
                     {"role": "user", "content": f"quantity {order[0]}, price {order[1]}"}],
                    response_format={"type": "json_object"}, **kw)
    try:
        c = Check.model_validate_json(r.choices[0].message.content)
        ans = (c.ok, c.filter)
    except ValidationError:
        ans = None
    return ans, r.usage.total_tokens, time.time() - t


if "C" in only:
    print("\n## C. model routing (12 filter checks)")
    flash, pro = Gateway([provider("flash")]), Gateway([provider("pro")])

    def cascade(order):
        """Ask the cheap model twice. If the two answers differ, ask the strong model."""
        a, b = check(flash, order, temperature=1), check(flash, order, temperature=1)
        tok, sec = a[1] + b[1], a[2] + b[2]
        if a[0] == b[0] and a[0] is not None:
            return a[0], tok, sec, 0
        p = check(pro, order, temperature=0)
        return p[0], tok + p[1], sec + p[2], 1

    for name, fn in (("flash", lambda o: (*check(flash, o, temperature=0), 0)),
                     ("pro", lambda o: (*check(pro, o, temperature=0), 1)),
                     ("cascade", cascade)):
        res = pmap(fn, ORDERS)
        good = sum(r[0] == (o[2], o[3]) for r, o in zip(res, ORDERS))
        print(f"   {name:8} correct {good}/{len(ORDERS)}   tokens/q {sum(r[1] for r in res) / len(res):.0f}"
              f"   s/q {sum(r[2] for r in res) / len(res):.1f}   pro calls {sum(r[3] for r in res)}")


# D. Structured output: the prompt asks, the validator decides.
class Order(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z]+USDT$")
    side: Literal["BUY", "SELL"]
    quantity: float = Field(gt=0)
    price: float | None  # None = market order


TEXTS = [
    ("buy 0.5 btc at 64,200", ("BTCUSDT", "BUY", 0.5, 64200)),
    ("sell two ETH, limit 3100.50 usdt", ("ETHUSDT", "SELL", 2, 3100.5)),
    ("I want to get 100 sol at market", ("SOLUSDT", "BUY", 100, None)),
    ("dump 0.25 BTC @ 70k", ("BTCUSDT", "SELL", 0.25, 70000)),
    ("long 1,500 XRP around 0.52", ("XRPUSDT", "BUY", 1500, 0.52)),
    ("pls sell half a bitcoin for sixty-five thousand", ("BTCUSDT", "SELL", 0.5, 65000)),
    ("BUY 3 bnb limit 590", ("BNBUSDT", "BUY", 3, 590)),
    ("sell 10 DOGE at market price", ("DOGEUSDT", "SELL", 10, None)),
    ("get rid of all 4 of my ether at 2.9k", ("ETHUSDT", "SELL", 4, 2900)),
    ("ape into 0.01 btc, whatever the price", ("BTCUSDT", "BUY", 0.01, None)),
]
ASK = "Extract the order from the message as JSON with fields symbol, side, quantity, price."
PROMPTS = {"loose prompt": ASK,
           "schema in prompt": ASK + " price is null for a market order. JSON schema:\n"
           + json.dumps(Order.model_json_schema())}

if "D" in only:
    print("\n## D. structured output (10 messy order messages)")
    gw = Gateway([provider("flash")])

    def extract(text, ask, repairs):
        try:
            o, used = gw.structured([{"role": "system", "content": ask},
                                     {"role": "user", "content": text}], Order,
                                    repairs=repairs, temperature=0, think=False)
            return (o.symbol, o.side, o.quantity, o.price), used
        except ValueError:
            return None, repairs

    for label, ask in PROMPTS.items():
        for repairs in (0, 2):
            res = pmap(lambda t: extract(t[0], ask, repairs), TEXTS)
            valid = sum(r[0] is not None for r in res)
            right = sum(r[0] == want for r, (_, want) in zip(res, TEXTS))
            print(f"   {label}, repairs={repairs}: valid {valid}/10   correct {right}/10   "
                  f"repair rounds used {sum(r[1] for r in res if r[0])}")
            for r, (text, want) in zip(res, TEXTS):
                if r[0] and r[0] != want:
                    print(f"     valid but WRONG: {text!r} -> {json.dumps(r[0])}")

# E. Streaming does not make the answer faster. It makes the wait shorter.
if "E" in only:
    print("\n## E. streaming: time to first visible token vs total")
    gw = Gateway([provider("flash")])
    for think in (True, False):
        for _ in range(3):
            t, first, n = time.time(), None, 0
            for piece in gw.stream([{"role": "user", "content":
                                     "Explain what a circuit breaker is in 120 words."}], think=think):
                first = first or time.time() - t
                n += len(piece)
            print(f"   think={think}: first token {first:.2f}s   total {time.time() - t:.2f}s   {n} chars")
