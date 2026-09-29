# Lesson 4 - Corrective RAG (CRAG)

Diagram: `L4_CRAG` in [docs/diagrams](../../docs/diagrams/README.md).

## The idea

Naive RAG trusts whatever retrieval returns. CRAG adds a **grader** that
checks the retrieved chunks *before* answering, and a **corrective action**
when they are weak.

```
retrieve -> grade each chunk
  some relevant  -> answer from the relevant chunks only ("knowledge refinement")
  none relevant  -> rewrite the query, search a wider/different source, grade again
  still nothing  -> "Not in the sources." (or escalate to a human)
```

The CRAG paper uses three labels: *correct* (use the docs), *incorrect*
(throw them away, search elsewhere - web search in the paper), *ambiguous*
(combine both). Here the "other source" is hybrid search with a rewritten
keyword query, and the retry limit is 2.

## Run it

```sh
uv run lessons/04_crag/run.py     # needs DEEPSEEK_API_KEY or LLM_API_KEY
```

The test set is the 25 single-hop questions plus **5 questions the docs
cannot answer**. Some are near misses: deposits and withdrawals are mentioned
but not their fees, and the commission FAQ has only fictional example rates.

## Results (bge-small dense top 3 as the first retrieval, DeepSeek)

| Setup | Answerable correct | Unanswerable refused | LLM calls/q | sec/q |
| --- | --- | --- | --- | --- |
| naive | 22/25 | 5/5 | 1.0 | 3.7 |
| CRAG | 23/25 | 5/5 | 2.2 | 6.6 |

Read this honestly - it teaches more than "CRAG wins":

- **The gain was small (+1) and the cost doubled.** The strict grounding
  prompt ("answer only from sources, else say not found") already refused all
  5 unanswerable questions. On clean, well-structured docs, a good retriever
  plus a strict prompt gets you most of the way.
- **CRAG fixed EXPIRE_MAKER**: naive got a chunk listing the modes but not the
  definition; the grader rejected it, and the rewritten keyword query found it.
- **The grader has its own errors.** For "can I still use shared-secret
  keys?" the grader accepted chunks about HMAC *signing* (same topic) but not
  the one saying *HMAC is deprecated*. Same topic != answers the question.
  Grader precision is the whole game.
- **One "failure" is the judge's fault.** "Ping every 20 seconds" is correct;
  the judge marked it wrong because the reference also mentions the pong.
  LLM judges need calibration against human labels (lesson 8).
- Expect CRAG to pay off more on messy, real data: many near-duplicate
  docs, outdated pages, user questions far from the docs' wording.

## Review questions

**Q: What is Corrective RAG?**
> A grader scores the retrieved documents before generation. If they're
> relevant, answer from them (and drop the irrelevant ones). If not, take a
> corrective action - rewrite the query, search another source such as web
> search or a different index - and if nothing good comes back, say so
> instead of guessing.

**Q: CRAG vs Self-RAG?**
> CRAG adds an external grader *around* retrieval: it fixes bad inputs.
> Self-RAG makes the generator itself reflect: decide whether to retrieve,
> judge each passage, and check whether its own answer is supported. The
> original Self-RAG fine-tunes the model to emit reflection tokens; in
> practice people approximate it with prompts. You can combine them.

**Q: What does the grader cost, and how do you make it cheaper?**
> One extra LLM call per retrieval, more on retries. Here ~2.2x calls and
> ~1.8x latency. Cheaper options: a small fine-tuned classifier or a
> cross-encoder score threshold as the grader; only grade when the retriever's
> top score is low; grade in one batched call (as this code does).

**Q: How do you know the grader is good?**
> Label a sample of (question, chunk) pairs by hand, then measure the
> grader's precision and recall on them. False "relevant" lets noise through
> (the HMAC case); false "irrelevant" triggers needless retries and wrong
> refusals.

**Q: Why does "not found" matter so much at an exchange?**
> A confident wrong answer about fees, limits, or order behaviour can cost a
> user money and creates compliance risk. A clear "I can't find that, here's
> how to reach support" is the safe default. Track the refusal rate on
> unanswerable questions *and* the wrongly-refused rate on answerable ones -
> both matter.
