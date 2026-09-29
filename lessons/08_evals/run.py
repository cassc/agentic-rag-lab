"""Lesson 8: evaluate the evaluator, measure reliability, and gate regressions.

uv run lessons/08_evals/run.py                     # compare with evals/baseline.json
uv run lessons/08_evals/run.py --update-baseline   # accept current numbers
"""
import json
import sys
import uuid
from pathlib import Path
from lab.agent import Agent
from lab.evals import evaluate, load_golden
from lab.judge import JUDGE, RUBRIC, judge, pmap
from lab.tools import retriever

ROOT = Path(__file__).resolve().parents[2] / "evals"
metrics = {}

# 1. Judge calibration: agreement with (author-written) human labels.
labels = [json.loads(l) for l in (ROOT / "judge_labels.jsonl").read_text().splitlines()]


def kappa(pred, gold):
    """Cohen's kappa: agreement corrected for chance. 1 = perfect, 0 = chance."""
    n = len(gold)
    po = sum(p == g for p, g in zip(pred, gold)) / n
    pe = sum((sum(p == v for p in pred) / n) * (sum(g == v for g in gold) / n) for v in (True, False))
    return (po - pe) / (1 - pe)


print("== 1. judge calibration on", len(labels), "labelled answers")
for name, prompt in [("strict (lessons 3-5)", JUDGE), ("rubric", RUBRIC)]:
    pred = pmap(lambda r: judge(r, r["candidate"], prompt), labels)
    gold = [r["label"] for r in labels]
    agree = sum(p == g for p, g in zip(pred, gold)) / len(gold)
    print(f"{name:22} agreement {agree:.2f}  kappa {kappa(pred, gold):.2f}")
    for r, p in zip(labels, pred):
        if p != r["label"]:
            print(f"    judge={p!s:5} human={r['label']!s:5} {r['candidate'][:60]!r} ({r['note']})")
    metrics[f"judge_agreement_{name.split()[0]}"] = round(agree, 3)

# 2. Reliability: the lesson 7 agent, 3 trials per question at temperature 1.
SYSTEM = """You are a Binance Spot API assistant. Use search_docs; never guess.
Answer without a tool call when done. If the docs don't cover it, say "Not in the sources." """
rows, K = load_golden(multi_hop=True), 3


def trial(row):
    a = Agent(f"eval-{uuid.uuid4().hex[:8]}", SYSTEM, ["search_docs"], max_steps=6, temperature=1.0)
    s = a.run(row["q"])
    calls = [d for ev, d in a.log if ev == "tool"]
    return judge(row, s["done"], RUBRIC), s["step"], len(calls) - len(set(calls))


res = pmap(trial, [r for r in rows for _ in range(K)])
per_q = [res[i * K:(i + 1) * K] for i in range(len(rows))]
pass1 = sum(t[0] for t in res) / len(res)
passk = sum(any(t[0] for t in q) for q in per_q) / len(rows)
pass_hat_k = sum(all(t[0] for t in q) for q in per_q) / len(rows)
print(f"\n== 2. reliability, {len(rows)} multi-hop questions x {K} trials (temperature 1)")
print(f"pass@1 {pass1:.2f}   pass@{K} {passk:.2f}   pass^{K} {pass_hat_k:.2f}")
print(f"trajectory: steps/run {sum(t[1] for t in res) / len(res):.1f}, "
      f"repeated identical tool calls {sum(t[2] for t in res)}")
for row, q in zip(rows, per_q):
    print(f"   {''.join('Y' if t[0] else 'n' for t in q)}  {row['q'][:70]}")
metrics |= {"pass@1": round(pass1, 3), f"pass^{K}": round(pass_hat_k, 3)}

# 3. Cheap deterministic retrieval metric: runs in seconds, good for every commit.
print("\n== 3. retrieval (hybrid)")
hit, mrr = evaluate(retriever().search, load_golden(multi_hop=False), show_misses=False)
metrics |= {"hit@5": round(hit, 3), "mrr@5": round(mrr, 3)}

# 4. Regression gate, the CI step: fail if any metric drops more than its tolerance.
TOL = {"pass@1": 0.15, f"pass^{K}": 0.2}  # LLM metrics are noisy on 5 questions
base_file = ROOT / "baseline.json"
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "latest.json").write_text(json.dumps(metrics, indent=2))
if "--update-baseline" in sys.argv or not base_file.exists():
    base_file.write_text(json.dumps(metrics, indent=2))
    print("\nbaseline written:", metrics)
    sys.exit(0)
base = json.loads(base_file.read_text())
fails = [f"{k}: {base[k]} -> {v}" for k, v in metrics.items()
         if k in base and v < base[k] - TOL.get(k, 0.02)]
print("\n== 4. gate:", "FAIL " + "; ".join(fails) if fails else "PASS")
sys.exit(1 if fails else 0)
