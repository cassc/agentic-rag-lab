// Diagram slides: PNG from docs/diagrams + the steps in order (s = step, n = why note, loop = repeats).
const DIAGRAMS = {
  "01": [
    { img: "Ingest", t: "Offline: build the indexes once", steps: [
      { s: "Download pinned docs", n: "Pinned = same docs every run, so numbers are comparable." },
      { s: "Build keyword index (BM25)", n: "Used from lesson 2 for exact IDs." },
      { s: "Embed every chunk", n: "Chunks carry their heading path, so small chunks keep context." },
      { s: "Store vectors (cache .npy)", n: "Same docs + chunking = same hash, so no re-embedding." },
    ] },
    { img: "L1_Naive", t: "Naive RAG: retrieve once, then answer", steps: [
      { s: "Question", n: "The user's exact words are the query. Nothing is rewritten." },
      { s: "Embed query", n: "Same model as the chunks, normalized vector." },
      { s: "Top 5 by cosine", n: "One matrix multiply. This is the ONLY retrieval - the weak point for multi-hop." },
      { s: "Answer with citations", n: "Grounding prompt: only from sources, else 'Not in the sources'." },
    ] },
  ],
  "02": [
    { img: "L2_Hybrid", t: "Hybrid: dense + keyword, fuse, rerank", steps: [
      { s: "Question", n: "" },
      { s: "Dense top 20", n: "Finds meaning. Wide pool on purpose." },
      { s: "Keyword top 20", n: "Finds exact tokens like -1021." },
      { s: "RRF -> top 20 pool", n: "Ranks only: sum 1/(60 + rank). No score scaling." },
      { s: "Rerank, keep best 5", n: "Cross-encoder reads (question, chunk) together. Precise, slower." },
      { s: "Answer with citations", n: "" },
    ] },
  ],
  "03": [
    { img: "L3_MultiHop", t: "Multi-hop: one fact leads to the next", steps: [
      { s: "Question needing 2+ facts", n: "One embedding sits 'between' the facts and matches none well." },
      { s: "Split into sub-questions", n: "Decomposition. Stops here if sub-questions are independent (parallel)." },
      { s: "Retrieve for sub-question 1", n: "" },
      { s: "Use answer 1 to write query 2", n: "Iterative hop: the next query uses what hop 1 found.", loop: true },
      { s: "Retrieve for sub-question 2", n: "Max 3 hops; stops early when notes already have everything.", loop: true },
      { s: "Combine and answer", n: "Still grounded: only from retrieved sources." },
    ] },
  ],
  "04": [
    { img: "L4_CRAG", t: "CRAG: grade, then correct", steps: [
      { s: "Question", n: "" },
      { s: "Retrieve", n: "First pass: dense top 3." },
      { s: "Grade chunks", n: "correct / ambiguous / wrong. Same topic != answers the question." },
      { s: "If weak: rewrite query", n: "Keyword-style rewrite, e.g. an exact term.", loop: true },
      { s: "Retry with rewritten query (BM25/hybrid)", n: "A different source. The paper uses web search.", loop: true },
      { s: "Grade again (max N tries)", n: "Retry limit 2 here.", loop: true },
      { s: "Answer, or say not found", n: "'Not found' is a feature: no confident wrong answer." },
    ] },
  ],
  "05": [
    { img: "L5_SelfRAG", t: "Self-RAG: decide, draft, verify, fix", steps: [
      { s: "Question", n: "" },
      { s: "Need retrieval? (adaptive)", n: "The step that hurt: skipped 7/35 doc questions." },
      { s: "Hybrid top 5", n: "" },
      { s: "Draft with citations", n: "" },
      { s: "Every claim supported? (IsSup + IsUse)", n: "Also: does it fully answer the question?" },
      { s: "If not: search the missing part", n: "This fixed 2 incomplete multi-hop answers.", loop: true },
      { s: "Redraft without unsupported claims", n: "", loop: true },
      { s: "Verify again (max 2 rounds)", n: "Then return the last verified state or refuse.", loop: true },
    ] },
  ],
  "06": [
    { img: "L6_AgentLoop", t: "Agent loop: the model picks tools", steps: [
      { s: "Task", n: "" },
      { s: "Messages + tool schemas -> LLM", n: "The model sees schemas, not code.", loop: true },
      { s: "Run tool call(s)", n: "Can be several in parallel in one step.", loop: true },
      { s: "Live filters / price, doc search", n: "Errors come back as text so the model can recover.", loop: true },
      { s: "Results appended; next action", n: "No tool call = final answer. Step limit guarantees termination.", loop: true },
    ] },
  ],
  "07": [
    { img: "L7_Harness", t: "Harness: the same loop, made safe", steps: [
      { s: "Task", n: "" },
      { s: "Load checkpoint (resume if found)", n: "Same session id -> no repeated work after a crash." },
      { s: "LLM: next action", n: "", loop: true },
      { s: "pre_tool hook: allowed? approved? under limit?", n: "The hook decides, not the prompt.", loop: true },
      { s: "Run tool (only if allowed)", n: "", loop: true },
      { s: "post_tool hook: truncate, flag injection", n: "Regex flag is a signal, not a defence.", loop: true },
      { s: "Save checkpoint (atomic write)", n: "Temp file + rename: a crash can't corrupt it.", loop: true },
    ] },
  ],
};
