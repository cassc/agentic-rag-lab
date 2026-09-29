# Lesson 8 - Evaluation: judge the judge, measure reliability, gate regressions

## The idea

Every earlier lesson printed numbers. This lesson asks: **can you trust
them, and how do you keep them from sliding?**

1. **Judge calibration**: an LLM judge is a model too. Label a small set by
   hand and measure agreement before you trust its scores.
2. **Reliability**: agents are non-deterministic. Run each task several
   times.
   - pass@1 = average success
   - pass@k = at least one of k tries worked (fine for "retry until
     success" tasks)
   - pass^k = all k worked. This is what users feel: every time they ask,
     it must work.
3. **Trajectory metrics**: steps per run, repeated identical tool calls,
   tool errors.
4. **Regression gate**: save metrics, compare with a baseline, fail (exit 1)
   if something drops more than its tolerance. Run it in CI on every prompt,
   model, or tool change.

## Run it

```sh
uv run lessons/08_evals/run.py                     # compare with evals/baseline.json
uv run lessons/08_evals/run.py --update-baseline   # accept the current numbers
```

## Results

**1. Judge calibration** on 18 labelled answers (`evals/judge_labels.jsonl`):

| Judge prompt | Agreement | Cohen's kappa |
| --- | --- | --- |
| strict (used in lessons 3-5) | 0.94 | 0.89 |
| rubric ("answer what the question asks; unasked details optional") | 1.00 | 1.00 |

The strict judge failed "The taker order's STP mode decides." (it wanted the
TRANSFER exception, which the question didn't ask about). In lessons 4-5 it
also failed "ping every 20 seconds" for missing the pong. The same kind of
error, now measured.

Honest caveats:
- The labels were written by the same person (Claude) who wrote the rubric.
  That's **overfitting the judge to its own labels**. Relabel them yourself,
  and keep a held-out set the rubric was never tuned on.
- 18 examples is small. Real calibration: 100+ labels, 2 human labelers,
  and measure human-human agreement first (that's your ceiling).
- Lessons 3-5 still use the strict judge, so their numbers are slightly
  pessimistic.

**2. Reliability** (harness agent, 5 multi-hop questions x 3 trials,
temperature 1):

| pass@1 | pass@3 | pass^3 | steps/run | repeated calls |
| --- | --- | --- | --- | --- |
| 1.00 | 1.00 | 1.00 | 2.1 | 0 |

**The benchmark is saturated.** Perfect scores mean it can no longer tell a
good change from a bad one. Next step: add harder questions (3+ hops,
conflicting sources, live-data tasks, injection cases) until the best system
scores about 60-80%.

**3. Retrieval**: hybrid hit@5 1.00, MRR@5 0.82. Deterministic and takes
seconds, so it's the cheapest check to run on every commit.

**4. Gate**: the first run wrote `evals/baseline.json`. Later runs fail if
a metric drops more than its tolerance. The tolerance is 0.02 for
deterministic metrics, and wider for the noisy LLM metrics on tiny sets.

## Review questions

**Q: How do you evaluate a RAG or agent system?**
> In layers. Retrieval: recall@k and MRR on a golden set. Answers:
> correctness against references, groundedness (claims supported by
> sources), refusal on unanswerable questions. End to end: task success,
> latency, cost. Trajectory: steps, repeated calls, unsafe actions. Offline
> in CI on every change; online with user feedback and escalations feeding
> new test cases.

**Q: Can you trust LLM-as-judge?**
> Only after calibrating it. Hand-label a sample, measure agreement or
> kappa, read the disagreements, fix the rubric, and check it on a held-out
> set. Watch for known biases: position, length (verbosity), and preferring
> answers from its own model family. In my test a strict prompt marked
> correct answers wrong for leaving out details nobody asked for.

**Q: pass@k vs pass^k?**
> pass@k: at least one of k attempts succeeds, which fits tasks where you can
> check the result and retry. pass^k: all k succeed, which measures
> consistency. For a user-facing support agent, pass^k is the one that
> matters. It drops fast: 90% per try gives pass^5 of about 59%.

**Q: How do you build a benchmark for a new domain?**
> Start from real user questions and production failures. Label the expected
> sources and answers with clear annotation guidelines, and cover edge cases
> (unanswerable, multi-hop, adversarial). Version the dataset. Keep a held-out
> split. Check contamination (the model may have seen public docs). Keep it
> hard enough that the best system scores around 60-80%, so it can show
> progress.

**Q: How do you use production feedback?**
> Log traces. Collect signals: thumbs down, corrections, escalations to a
> human, repeated questions. Sample and label them, add them to the golden
> set, fix, and confirm with the gate. The eval set grows from real failures.
