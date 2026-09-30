// Multiple-choice quiz per lesson: q, o = options, a = right index, e = explanation.
// Questions test the reason (why), not the recall of numbers.
const QUIZ = {
  "01": [
    { q: "What is the root reason RAG exists?", o: ["LLMs are slow", "The model can't read all docs per question and doesn't know private or new docs", "Embeddings are cheap", "Vector databases are popular"], a: 1, e: "Limited context + limited knowledge -> select the few relevant pieces." },
    { q: "Why can search be one matrix multiply?", o: ["Because BM25 is linear", "Vectors are normalized, so cosine = dot product", "Because chunks are small", "Because of HNSW"], a: 1, e: "|a| = |b| = 1, so a·b is the cosine for every chunk at once." },
    { q: "Why does one query fail on a two-fact question?", o: ["The LLM is too small", "The question vector sits between the two facts and is close to neither", "BM25 is missing", "k is always too big"], a: 1, e: "One vector = one point in meaning space." },
    { q: "Why does the grounding prompt reduce hallucination?", o: ["It makes the model smarter", "Without it, the model fills gaps from memory; with it, it must cite or say 'not found'", "It shortens answers", "It improves retrieval"], a: 1, e: "It targets the gap-filling behaviour directly." },
  ],
  "02": [
    { q: "Why do embeddings miss exact IDs like -1021?", o: ["They are too slow", "Compressing text into a few hundred numbers keeps meaning but loses rare exact tokens", "IDs are not in the docs", "Cosine can't be negative"], a: 1, e: "Lossy compression of meaning. BM25 keeps the exact token." },
    { q: "Why fuse with ranks (RRF), not raw scores?", o: ["Ranks are faster", "BM25 and cosine scores are in different units and their spread changes per query", "Scores are secret", "RRF is newer"], a: 1, e: "Ranks have no units, so no tuning is needed." },
    { q: "Why can't a cross-encoder replace the first retrieval stage?", o: ["It is less precise", "It can't pre-compute: one model call per (question, chunk) pair is too slow for all chunks", "It needs BM25", "It only works on GPU"], a: 1, e: "Cheap and wide first, expensive and narrow second." },
    { q: "Recall is the problem (right chunk not in the top 50). Will a reranker help?", o: ["Yes, always", "No: a reranker only reorders what it gets", "Only a bigger one", "Only with RRF"], a: 1, e: "Fix retrieval first." },
  ],
  "03": [
    { q: "What makes a question need an iterative loop instead of decomposition?", o: ["It is long", "Sub-question 2 depends on the answer to sub-question 1", "It mentions two docs", "It has numbers"], a: 1, e: "Dependent -> sequential. Independent -> parallel." },
    { q: "Why might just raising k work for multi-hop?", o: ["It changes the embedding", "The second fact is often just below the cut-off; a wider net catches it with no extra LLM call", "It adds BM25", "It lowers cost"], a: 1, e: "Try the cheap fix before building a loop." },
    { q: "Why does an agentic retrieval loop need a hard hop limit?", o: ["To save disk", "'Done' is a model decision, and it can be wrong or drift", "The API requires it", "Chunks run out"], a: 1, e: "Only code can guarantee termination." },
  ],
  "04": [
    { q: "What root problem does CRAG address?", o: ["Slow retrieval", "The generator trusts any input and answers fluently even when the context is bad", "Too many chunks", "No citations"], a: 1, e: "Check the input before generation." },
    { q: "Why was CRAG's gain small on our docs?", o: ["The code had a bug", "Clean docs + strict prompt meant retrieval rarely failed, so there was little to fix", "DeepSeek is weak", "It used BM25"], a: 1, e: "A checker's value depends on how often the input is bad." },
    { q: "The grader accepted HMAC signing chunks but rejected 'HMAC is deprecated'. Why?", o: ["Same words != answers the question", "BM25 is broken", "The chunk was too long", "The judge was wrong"], a: 0, e: "Grader precision is the whole game." },
    { q: "Why prefer 'not found' at an exchange?", o: ["It is faster", "A confident wrong answer costs far more than a short delay", "Users like it", "It saves tokens"], a: 1, e: "Asymmetric error costs." },
  ],
  "05": [
    { q: "Why does verify-then-fix work?", o: ["It uses a bigger model", "Checking one claim against one source is easier than writing a perfect answer at once", "It skips retrieval", "It adds more chunks"], a: 1, e: "Split a hard task into small checkable ones." },
    { q: "Why did adaptive retrieval hurt?", o: ["It was too slow", "A model can't see its own knowledge gaps, so it skipped search and answered from memory", "It retrieved too much", "The verifier was wrong"], a: 1, e: "Skipped 7/35 doc questions." },
    { q: "An answer is 100% grounded but wrong. How?", o: ["Impossible", "Groundedness checks what is said, not what is missing", "The judge is broken", "Too many citations"], a: 1, e: "Measure groundedness AND completeness." },
  ],
  "06": [
    { q: "Why does an agent need a loop and not one call?", o: ["To use more tokens", "The model only writes text; the runtime must act, and the next step depends on the result", "APIs require loops", "For streaming"], a: 1, e: "Ask -> act -> observe -> repeat." },
    { q: "Why return tool errors as text instead of crashing?", o: ["Shorter logs", "The model can only react to what is in its context", "Python can't raise", "For speed"], a: 1, e: "FAKECOINUSDT: it read the error and recovered." },
    { q: "What alone GUARANTEES the loop ends?", o: ["The model saying done", "The step limit in code", "A good prompt", "Temperature 0"], a: 1, e: "The model's stop is a guess; the limit is code." },
  ],
  "07": [
    { q: "Why must permissions live in a hook, not the prompt?", o: ["Hooks are faster", "The model is probabilistic and can be manipulated; must-hold rules need deterministic code", "Prompts are too long", "Hooks are cheaper"], a: 1, e: "The prompt asks; the hook decides." },
    { q: "Why is prompt injection hard to stop inside the model?", o: ["Models are old", "Instructions and data arrive in the same text stream with no hard boundary", "Regex is slow", "Tools are untyped"], a: 1, e: "So gate privileged actions outside the model." },
    { q: "Why did 'notes then clear' beat plain clearing?", o: ["Fewer tools", "Clearing dropped the facts, so the agent searched again; notes kept the facts in few tokens", "Bigger model", "More steps allowed"], a: 1, e: "Keep the facts, drop the raw output." },
    { q: "Why does editing early context hurt cost?", o: ["It doesn't", "The provider caches an identical prefix; an early edit breaks the cache for everything after it", "More tokens are sent", "Tools reload"], a: 1, e: "Keep system + tools stable, append at the end." },
  ],
  "08": [
    { q: "Why must you calibrate an LLM judge?", o: ["It is slow", "It is a model too - an instrument with its own errors and biases", "It is expensive", "The API requires it"], a: 1, e: "Hand-label, measure kappa, read disagreements." },
    { q: "90% success per try. pass^5 is about...", o: ["90%", "75%", "59%", "10%"], a: 2, e: "All must succeed: 0.9^5 ≈ 0.59." },
    { q: "Why is a 100% benchmark a problem?", o: ["It isn't", "It can no longer tell good changes from bad ones", "It costs more", "It breaks CI"], a: 1, e: "Add harder cases until the best system is at 60-80%." },
    { q: "Why run the regression gate on every change?", o: ["For speed", "Any change can break something you didn't touch; only an automatic comparison catches it", "To train the model", "To block injection"], a: 1, e: "baseline.json + tolerance, exit 1 in CI." },
  ],
};
