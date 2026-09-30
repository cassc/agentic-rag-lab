// Multiple-choice quiz per lesson: q, o = options, a = right index, e = explanation.
const QUIZ = {
  "01": [
    { q: "Why is naive RAG called \"naive\"?", o: ["It uses a small model", "It retrieves once with the user's words and trusts the result", "It has no citations", "It uses BM25 only"], a: 1, e: "One retrieval, exact user words, no checking." },
    { q: "With normalized vectors, cosine similarity equals...", o: ["Euclidean distance", "1 - dot product", "The dot product", "BM25 score"], a: 2, e: "|a| = |b| = 1, so cos = a·b." },
    { q: "Single-hop hit@5 was 0.96; multi-hop hit@5 was...", o: ["0.96", "0.80", "0.40", "0.00"], a: 2, e: "One query can't pull two facts from two docs." },
    { q: "Why eval by key phrase instead of chunk ID?", o: ["Phrases are faster", "Chunk IDs change when chunking changes", "IDs are secret", "Phrases need no labels"], a: 1, e: "So you can compare chunking strategies fairly." },
  ],
  "02": [
    { q: "Which search is best for exact tokens like -1021?", o: ["Dense", "BM25", "Reranker only", "HyDE"], a: 1, e: "Embeddings blur exact IDs; keywords match them." },
    { q: "Why does RRF use ranks, not scores?", o: ["Ranks are faster to sort", "Scores are on different scales and shift per query", "Scores are secret", "Ranks need GPU"], a: 1, e: "BM25 (0-30) vs cosine (0-1) can't be compared directly." },
    { q: "Cross-encoder vs bi-encoder:", o: ["Cross-encoder is faster", "Cross-encoder reads question and chunk together, more precise", "Bi-encoder can't be pre-computed", "They are the same"], a: 1, e: "Bi-encoder to recall, cross-encoder to rank." },
    { q: "The bigger reranker raised MRR but lost one question. Lesson?", o: ["Always use the bigger model", "A better average can hide a regression", "MRR is useless", "Rerankers hurt recall"], a: 1, e: "Look at the misses, not only the score." },
  ],
  "03": [
    { q: "Which cheap fix matched decomposition?", o: ["Raise k to 10", "Use a bigger LLM", "Add BM25", "Lower temperature"], a: 0, e: "Single k=10 got 4/5, same as decomposed." },
    { q: "When is an iterative loop better than decomposition?", o: ["When sub-questions are independent", "When a later search depends on an earlier answer", "Always", "Never"], a: 1, e: "Decomposed sub-queries run in parallel and can't use each other's results." },
    { q: "Why did the iterative loop cost only ~2.4 calls, not 4?", o: ["It skipped the LLM", "It stops early when one hop is enough", "It cached answers", "It used a smaller model"], a: 1, e: "3 of 5 questions needed only one hop." },
  ],
  "04": [
    { q: "What does the CRAG grader do?", o: ["Grades the final answer", "Checks retrieved chunks before answering", "Ranks users", "Chooses the model"], a: 1, e: "It fixes bad inputs before generation." },
    { q: "CRAG vs naive in our test:", o: ["Big gain, same cost", "+1 correct at ~2.2x calls", "Worse and cheaper", "No difference at all"], a: 1, e: "The strict grounding prompt already did most of the work." },
    { q: "The HMAC case shows that...", o: ["Same topic != answers the question", "BM25 is broken", "Graders are always right", "Refusals are bad"], a: 0, e: "Grader precision is the whole game." },
  ],
  "05": [
    { q: "Which reflection token asks \"is my statement supported?\"", o: ["Retrieve", "IsRel", "IsSup", "IsUse"], a: 2, e: "IsSup = supported by the passage." },
    { q: "What hurt Self-RAG most in our test?", o: ["The verify loop", "Adaptive retrieval skipping doc questions", "Too many citations", "The reranker"], a: 1, e: "Skipped 7/35 doc questions; model answered from memory." },
    { q: "Baseline was 35/35 grounded but missed 2. So...", o: ["Grounded != correct", "Groundedness is enough", "The judge is broken", "Use more chunks"], a: 0, e: "Measure groundedness and completeness." },
  ],
  "06": [
    { q: "When does the agent loop end normally?", o: ["After 3 steps", "When the model returns text with no tool call", "When a tool fails", "When the user types stop"], a: 1, e: "Plus the step limit, which guarantees termination." },
    { q: "How should a tool report a bad input?", o: ["Crash the loop", "Return the error as text the model can act on", "Return nothing", "Retry forever"], a: 1, e: "The model read FAKECOINUSDT errors and recovered." },
    { q: "Retrieval as a tool (vs pipeline) is...", o: ["More predictable", "More flexible but needs limits and trajectory evals", "Always cheaper", "Impossible with RAG"], a: 1, e: "The model decides when and what to search." },
  ],
  "07": [
    { q: "Who decided whether an order was placed?", o: ["The model", "The system prompt", "The pre-tool hook", "The user prompt"], a: 2, e: "Never rely on the prompt for permissions." },
    { q: "Why write checkpoints atomically?", o: ["Faster", "A crash mid-save can't corrupt the file", "Smaller files", "For caching"], a: 1, e: "Write temp file, then rename." },
    { q: "Which compaction mode worked best?", o: ["None", "Clear old outputs", "Notes, then clear", "Delete the system prompt"], a: 2, e: "4 steps, 12k tokens. Plain clearing made the agent forget and loop." },
    { q: "Why does compaction reduce prompt-cache hits?", o: ["It changes the model", "Editing early context breaks the cached prefix", "Caches expire every step", "It doesn't"], a: 1, e: "Everything after the first edit misses the cache." },
  ],
  "08": [
    { q: "pass^k means...", o: ["At least one of k tries works", "All k tries work", "Average of k tries", "k-th try works"], a: 1, e: "Consistency - what users feel." },
    { q: "90% success per try gives pass^5 of about...", o: ["90%", "75%", "59%", "10%"], a: 2, e: "0.9^5 ≈ 0.59." },
    { q: "All scores are 1.00. What next?", o: ["Ship it", "Add harder cases; benchmark is saturated", "Lower the tolerance", "Remove the judge"], a: 1, e: "Aim for the best system at 60-80%." },
    { q: "What does the regression gate do?", o: ["Blocks prompt injection", "Fails CI (exit 1) if a metric drops beyond tolerance", "Rate-limits users", "Trains the judge"], a: 1, e: "Compare with baseline.json on every change." },
  ],
};
