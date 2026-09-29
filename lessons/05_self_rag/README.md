# Lesson 5 - Self-RAG and reflect loops

Diagram: `L5_SelfRAG` in [docs/diagrams](../../docs/diagrams/README.md).

## The idea

Self-RAG (Asai et al., 2023) teaches the model to reflect at each step with
special tokens:

| Token | Question the model asks itself |
| --- | --- |
| Retrieve | Do I need to search at all? |
| IsRel | Is this passage relevant? |
| IsSup | Is my statement supported by the passage? |
| IsUse | Is my answer useful for the question? |

The original fine-tunes the model to emit these tokens. Here, like most
production systems, we **approximate it with prompts**:

```
decide: retrieval needed?  -- no --> answer directly
retrieve (hybrid top 5) -> draft with citations
loop (max 2 rounds):
  verify: split the answer into claims; is each stated by a source?
          does it answer the question? what is missing?
  all good -> stop
  else -> search for the missing part, redraft without unsupported claims
```

`lab/verify.py` is the IsSup + IsUse step. Lesson 8 reuses the same idea as a
groundedness metric.

## Run it

```sh
uv run lessons/05_self_rag/run.py
```

## Results (35 questions: 25 single-hop, 5 multi-hop, 5 unanswerable)

| Setup | Correct | Grounded (final) | LLM calls/q |
| --- | --- | --- | --- |
| baseline: hybrid top 5, one draft | **33/35** | 35/35 | 1.0 |
| self-RAG (prompted) | 31/35 | 34/35 | 3.3 |

Adaptive retrieval: skipped all 3 general questions ("17 * 3") correctly,
but **also skipped 7 of 35 doc questions**.

Self-RAG *lost*, and why is the lesson:

- **The verify-and-fix loop worked.** The baseline's 2 misses were
  *incomplete* multi-hop answers (the -1021 max window, the SOR rate limits).
  The verifier flagged "doesn't fully answer", searched the missing part, and
  self-RAG got both right.
- **Adaptive retrieval did the damage.** When the router said "no retrieval
  needed", the model answered from its own memory: "pegged orders are also
  called pegged-to-market orders" (the docs say *best bid-offer*), "funding is
  charged every 8 hours", a generic TRON fee answer. Two of those were
  supposed to be refusals. **Skipping retrieval turns a grounded assistant back
  into a plain chatbot.**
- **Grounded != correct.** The baseline was 35/35 grounded and still missed
  2: every claim was supported, but a needed fact was absent. Measure both
  groundedness *and* completeness.
- One miss is the judge again (ping every 20 s). Lesson 8 fixes the judge.

## Review questions

**Q: What is Self-RAG?**
> The model reflects during generation: whether to retrieve, whether each
> passage is relevant, whether each statement is supported, and whether the
> answer is useful. The paper fine-tunes a model to emit reflection tokens;
> in practice you get most of it with a verifier prompt and a retry loop.

**Q: Would you use adaptive retrieval ("skip search when not needed")?**
> Carefully. In my test the router skipped 7 of 35 doc questions and the model
> answered from memory - wrong, or answering things it should have refused. For
> a domain assistant like exchange support, I'd default to always retrieving
> and only skip for clearly out-of-domain small talk, with the router
> evaluated on its own labelled set.

**Q: How do you stop a reflect loop?**
> Stop when every claim is supported and the question is answered; otherwise
> a hard cap (2 rounds here) and a budget. After the cap, return the last
> verified state or refuse - never loop until the model says it's happy.

**Q: What is groundedness and how do you measure it?**
> The share of claims in the answer that a retrieved source actually states.
> Split the answer into claims, check each against the sources with an LLM or
> an NLI model. It catches hallucination, not missing facts, so pair it with
> a correctness or completeness metric.
