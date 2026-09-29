"""Download a pinned snapshot of Binance's public Spot API docs into data/docs/."""
from pathlib import Path
from urllib.request import urlopen

REPO = "binance/binance-spot-api-docs"
SHA = "828ca74b809cfedbd5602df328b5f706368d483b"  # 2026-09-18, pinned so evals stay stable
FILES = [
    "README.md", "enums.md", "errors.md", "filters.md", "rest-api.md",
    "web-socket-streams.md", "user-data-stream.md",
    *(f"faqs/{n}.md" for n in [
        "api_key_types", "commission_faq", "market_data_only", "market_orders_faq",
        "opo", "order_amend_keep_priority", "order_count_decrement", "pegged_orders",
        "price_range_execution_rules", "sbe_faq", "sor_faq", "spot_glossary",
        "stp_faq", "trailing-stop-faq",
    ]),
]
OUT = Path(__file__).resolve().parent.parent / "data" / "docs"

for f in FILES:
    dest = OUT / f.replace("/", "__")
    if dest.exists():
        continue
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(urlopen(f"https://raw.githubusercontent.com/{REPO}/{SHA}/{f}").read())
    print("fetched", f)
