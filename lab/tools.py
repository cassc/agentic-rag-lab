"""Tools for the agent lessons: doc search, live public market data, and a
fake (dry-run) order tool. Each tool = JSON schema for the model + a function."""
import json
from functools import cache
from urllib.request import urlopen

API = "https://api.binance.com/api/v3"


@cache
def retriever():
    from lab.chunk import load_chunks
    from lab.embed import Embedder
    from lab.retrieve import Hybrid
    return Hybrid(load_chunks(), Embedder())


def search_docs(query, k=4):
    return "\n\n".join(f"<source id={c.id}>\n{c.full}\n</source>"
                       for c, _ in retriever().search(query, k))


def get_price(symbol):
    return urlopen(f"{API}/ticker/price?symbol={symbol.upper()}", timeout=10).read().decode()


def get_symbol_filters(symbol):
    info = json.load(urlopen(f"{API}/exchangeInfo?symbol={symbol.upper()}", timeout=10))
    return json.dumps(info["symbols"][0]["filters"])


def place_order(symbol, side, quantity, price):
    # Never trades. Exists so the harness lessons can show permission hooks.
    return json.dumps({"status": "DRY_RUN", "symbol": symbol, "side": side,
                       "quantity": quantity, "price": price})


def spec(fn, desc, **params):
    return {"type": "function", "function": {
        "name": fn.__name__, "description": desc,
        "parameters": {"type": "object", "required": list(params),
                       "properties": {k: {"type": t, "description": d}
                                      for k, (t, d) in params.items()}}}}


TOOLS = {
    "search_docs": (search_docs, spec(search_docs,
        "Search the Binance Spot API docs. Use exact names, codes and fields in the query.",
        query=("string", "search query"))),
    "get_price": (get_price, spec(get_price, "Latest price for a symbol, e.g. BTCUSDT.",
        symbol=("string", "trading pair"))),
    "get_symbol_filters": (get_symbol_filters, spec(get_symbol_filters,
        "Live trading filters (PRICE_FILTER, LOT_SIZE, NOTIONAL...) for a symbol.",
        symbol=("string", "trading pair"))),
    "place_order": (place_order, spec(place_order, "Place a LIMIT order. Moves user funds.",
        symbol=("string", "trading pair"), side=("string", "BUY or SELL"),
        quantity=("string", "base asset quantity"), price=("string", "limit price"))),
}


def run_tool(name, args):
    """Errors go back to the model as text so it can recover, not crash the loop."""
    if name not in TOOLS:
        return f"ERROR: unknown tool {name}"
    try:
        return TOOLS[name][0](**args)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
