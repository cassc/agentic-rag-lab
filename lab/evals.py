"""Golden-set retrieval metrics: hit rate@k (recall) and MRR."""
import json
import re
from pathlib import Path

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden.jsonl"


def norm(s):
    return re.sub(r"[`*]", "", s).lower()


def load_golden(multi_hop=None, unanswerable=False):
    rows = [json.loads(l) for l in GOLDEN.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r.get("unanswerable", False) == unanswerable]
    return [r for r in rows if multi_hop is None or ("hops" in r) == multi_hop]


def is_hit(chunk, target):
    must = target["must"] if isinstance(target["must"], list) else [target["must"]]
    return chunk.doc == target["doc"] and all(norm(m) in norm(chunk.full) for m in must)


def targets(row):
    return row.get("hops") or [row]


def found_all(row, chunks):
    """True if every target (hop) of the row is somewhere in chunks."""
    return all(any(is_hit(c, t) for c in chunks) for t in targets(row))


def evaluate(search, rows, k=5, show_misses=True):
    """search(query, k) -> list of (chunk, score). A row counts as found only
    if every one of its targets (hops) is in the top k."""
    hits, rr = 0, 0.0
    for r in rows:
        results = [c for c, _ in search(r["q"], k)]
        ranks = [next((i for i, c in enumerate(results) if is_hit(c, t)), None)
                 for t in targets(r)]
        if all(x is not None for x in ranks):
            hits += 1
            rr += 1 / (1 + max(ranks))
        elif show_misses:
            print(f"  miss: {r['q']}")
    n = len(rows)
    print(f"hit@{k}: {hits}/{n} = {hits / n:.2f}   MRR@{k}: {rr / n:.2f}")
    return hits / n, rr / n
