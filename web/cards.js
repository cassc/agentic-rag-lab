// Cards per lesson. fp = first-principle card. Concept: t, b (HTML). Likely question: q, a.
// Pattern: root problem -> idea that follows -> evidence from our numbers.
const LESSONS = [
  {
    id: "01", title: "Naive RAG",
    cards: [
      { fp: true, t: "Why RAG exists", b: "An LLM only knows its training data, and it can read only a limited amount of text per call. It can't read all the docs for every question.<br><b>So:</b> pick the few pieces that matter, give only those, and make the model answer from them. That is RAG. Every other part follows from this." },
      { t: "Why chunk?", b: "<b>Problem:</b> you retrieve and pay for whole units of text. A whole doc is too big and has too much noise.<br><b>So:</b> split it into chunks. The chunk is the unit you match and the unit the LLM reads.<br><b>Trade-off:</b> small = precise but loses context; big = keeps context but adds noise and tokens." },
      { t: "Why embeddings?", b: "<b>Problem:</b> users and docs use different words for the same idea.<br><b>So:</b> map text to a vector where similar meaning = nearby. Then \"find relevant text\" becomes \"find nearby vectors\"." },
      { t: "Why normalize vectors?", b: "Cosine = a·b / (|a| |b|). If every vector has length 1, cosine is just the dot product.<br><b>So:</b> search over all chunks is one matrix multiply: <code>vecs @ q</code>. Brute force is fine up to ~1M chunks; after that, an ANN index (HNSW) trades a little accuracy for speed." },
      { t: "Why prepend the heading?", b: "A chunk is cut from its context. A chunk that only says \"UTC\" matches nothing.<br><b>So:</b> each chunk carries <code>[doc] Heading &gt; Sub-heading</code>. Now the chunk says what it is about." },
      { t: "Why a grounding prompt?", b: "<b>Problem:</b> when the chunks don't have the answer, the model fills the gap from memory. It sounds just as sure.<br><b>So:</b> \"answer only from sources, cite [n], else say 'Not in the sources'\". The cheapest guard against hallucination." },
      { t: "Where naive RAG breaks", b: "One question -> one vector -> one point in meaning space. If the answer needs two facts from two docs, the question vector sits <i>between</i> them and matches neither well.<br><b>Evidence:</b> single-hop hit@5 0.96, multi-hop <b>0.40</b>." },
      { t: "How to measure retrieval", b: "<b>hit@k</b>: is the right chunk in the top k? That tells you if a right answer is <i>possible</i>.<br><b>MRR</b>: average of 1/rank. It matters when the LLM sees only the top few.<br>A hit = right doc <b>and</b> a key phrase. Chunk IDs change with chunking; phrases don't, so strategies stay comparable." },
    ],
    qa: [
      { q: "Why do we need RAG at all? Why not put all docs in the prompt?", a: "Context is limited and costs tokens every call. Quality also drops as context grows. And the model's training data is old or missing your private docs. So retrieve the few relevant pieces, and make the answer come from them." },
      { q: "How do you choose chunk size?", a: "The chunk is both the search unit and the reading unit. Too small: the match is precise but the meaning is cut. Too big: noise and cost. Start from the doc structure (headings), add the heading path to each chunk, then tune size on the eval set." },
      { q: "What are the main ways naive RAG fails, and what is the root cause of each?", a: "1) Wording or exact-ID mismatch: the embedding lost the exact token -> hybrid. 2) Right chunk ranked too low: the fast similarity is rough -> reranker. 3) Multi-fact questions: one vector can't be close to two facts -> decomposition / multi-hop. 4) The model goes beyond the context: it fills gaps from memory -> grounding prompt, citations, groundedness check." },
      { q: "hit@k vs MRR - which matters when?", a: "hit@k asks whether the answer is possible at all. MRR asks how high the right chunk is. If you give the LLM only the top 3, rank matters, so watch MRR." },
    ],
  },
  {
    id: "02", title: "Hybrid search + rerank",
    cards: [
      { fp: true, t: "Two kinds of matching", b: "An embedding compresses text into a few hundred numbers. Compression keeps meaning but loses rare exact tokens like <code>-1021</code>. A keyword index keeps exact tokens but knows no meaning.<br><b>So:</b> they fail on <i>different</i> questions. Use both." },
      { t: "Evidence: different misses", b: "Dense hit@5 0.96 (missed \"trailingDelta of 100\"). BM25 0.96 (missed \"default recvWindow\"). Hybrid: <b>1.00</b>.<br>Same score, different misses. That is the whole case for hybrid." },
      { t: "Why fuse by rank (RRF)?", b: "<b>Problem:</b> BM25 scores (0-30) and cosine (0-1) are not in the same unit, and their spread changes per query.<br><b>So:</b> use only rank: <code>score = sum 1/(60 + rank)</code>. No units, no tuning." },
      { t: "Speed vs precision", b: "To be fast, chunk vectors must be computed <i>before</i> the question exists. So question and chunk never \"see\" each other (<b>bi-encoder</b>).<br>A <b>cross-encoder</b> reads both together: more precise, but it can't pre-compute. Cost grows with every pair." },
      { t: "So: two stages", b: "Cheap and wide first (bi-encoder + BM25, top 20), expensive and narrow second (cross-encoder, keep 5).<br><i>Bi-encoder to recall, cross-encoder to rank.</i><br>A reranker only reorders. It can't find what stage 1 missed." },
      { t: "Averages hide flips", b: "A bigger reranker raised MRR to 0.85 but <b>lost one question</b>. On 25 questions, one question = 0.04.<br><b>So:</b> read the misses, not only the average. Don't claim a win from one flip." },
    ],
    qa: [
      { q: "Why hybrid search? Explain from how embeddings work.", a: "An embedding is a lossy compression of meaning. Rare exact strings (error codes, endpoints, tickers) get blurred. BM25 keeps exact tokens but misses synonyms. They fail on different questions, so fusing them covers both. At an exchange, exact IDs are everywhere." },
      { q: "Why RRF and not a weighted sum of scores?", a: "The scores are in different units and their spread shifts per query, so a fixed weight is wrong for many queries. Ranks have no units. RRF needs no tuning. A tuned weighted sum can win, but only with enough labelled data." },
      { q: "Why is a cross-encoder more precise, and why not use it for everything?", a: "It reads question and chunk together, so it sees word-to-word links. But it can't pre-compute anything: one model call per (question, chunk) pair. That cost only fits a small pool, so use it after a cheap wide retrieval." },
      { q: "When is a reranker NOT worth it?", a: "When recall is the problem. A reranker only reorders the pool. If the right chunk isn't in the top 20-50, fix retrieval first." },
      { q: "What would you do at scale?", a: "ANN (HNSW) in a vector store with built-in hybrid (Qdrant, Milvus, OpenSearch). Metadata filters before ranking to shrink the pool. Cache frequent queries. Rerank only the top 20-50 on GPU." },
    ],
  },
  {
    id: "03", title: "Multi-hop retrieval",
    cards: [
      { fp: true, t: "Some facts depend on other facts", b: "Search finds text similar to the <b>query</b>. But in \"error -1021: what window, and how large can it be?\", the second fact (recvWindow max) is similar to the <i>first fact</i>, not to the question.<br><b>So:</b> sometimes you must learn fact 1 before you can ask for fact 2." },
      { t: "Independent vs dependent", b: "<b>Independent</b> sub-questions: split up front and search in parallel (<b>decomposition</b>). Low latency.<br><b>Dependent</b>: search, read, then write the next query from what you found (<b>iterative multi-hop</b>). Must be sequential." },
      { t: "Try the cheap fix first", b: "A bigger k widens the net and sometimes catches the second fact. It costs tokens, but no extra round trip.<br><b>Evidence:</b> k=5 3/5, k=10 4/5 = decomposition 4/5. Iterative 5/5." },
      { t: "Why a loop needs limits", b: "The model decides when it is \"done\", and it can be wrong. It can repeat itself or drift.<br><b>So:</b> max hops (3), explicit done signal, don't re-add seen chunks, keep short notes instead of full history.<br>It stopped early when one hop was enough: 2.4 calls, not 4." },
      { t: "Errors compound", b: "A wrong hop 1 sends hop 2 to the wrong place. The model also leaks its own beliefs into queries (\"recvWindow default 5000 maximum 60000\"). A wrong belief steers the search.<br><b>So:</b> still ground the final answer in sources." },
    ],
    qa: [
      { q: "Why does one search fail on multi-hop questions?", a: "Similarity search finds text close to the query vector. A two-fact question is a mix of both facts, so it is close to neither. And when fact 2 is only findable once you know fact 1, no single query can reach it." },
      { q: "Decomposition or an iterative loop? How do you decide?", a: "Ask: does sub-question 2 need the answer to sub-question 1? No -> decompose and run in parallel (fast). Yes -> iterate (sequential), with max hops, a budget, and a clear stop signal." },
      { q: "Before building a loop, what cheap fix would you try, and why might it work?", a: "Raise k. The second fact is often just below the cut-off. More context costs tokens but no extra LLM round trip. Here k=10 matched decomposition." },
      { q: "How do you evaluate multi-hop retrieval?", a: "Were ALL needed facts retrieved (every hop), not just one? Is the answer correct vs a reference (with a calibrated judge)? What did it cost: calls, tokens, latency? Always compare to the cheap baseline." },
    ],
  },
  {
    id: "04", title: "CRAG",
    cards: [
      { fp: true, t: "Garbage in, confident garbage out", b: "Retrieval is a guess. The generator trusts whatever it gets and writes a fluent answer anyway.<br><b>So:</b> check the input <i>before</i> using it. If it is bad, fix it (rewrite, search elsewhere) or say \"not found\"." },
      { t: "The flow", b: "retrieve -> grade each chunk<br>- some relevant -> answer from those only<br>- none -> rewrite query, try another source, grade again (max 2)<br>- still none -> \"Not in the sources\"<br>Paper labels: correct / ambiguous / incorrect." },
      { t: "The grader is a model too", b: "Its mistakes limit the gain. It accepted chunks about HMAC <i>signing</i> (same words) but rejected \"HMAC is deprecated\" (the real answer).<br><b>Same topic != answers the question.</b> Grader precision is the whole game." },
      { t: "Value depends on how often retrieval fails", b: "naive 22/25, CRAG 23/25, at 2.2x calls.<br>On clean docs with a strict grounding prompt, retrieval rarely fails, so a checker has little to fix. Expect more gain on messy data: duplicates, old pages, far-off wording." },
      { t: "Why \"not found\" is a feature", b: "The two errors have different costs. A confident wrong answer about fees or limits can lose a user money. \"I can't find it, contact support\" costs a little time.<br><b>So:</b> track refusals on unanswerable AND wrong refusals on answerable." },
    ],
    qa: [
      { q: "What problem does CRAG solve, from first principles?", a: "The generator can't tell good context from bad, and it writes fluently either way. So you put a check between retrieval and generation. Keep the good chunks, fix the retrieval when they are bad, and refuse when nothing good is found." },
      { q: "Why did CRAG help so little here?", a: "A checker only helps when there is something to catch. Clean docs + good retriever + strict grounding prompt = few bad inputs. And the grader has its own errors (same topic vs answers the question)." },
      { q: "CRAG vs Self-RAG?", a: "CRAG checks the INPUT: an external grader around retrieval. Self-RAG checks the OUTPUT: the generator reflects on its own claims. Different failure points, so you can combine them." },
      { q: "How do you make the grader cheaper, and how do you know it's good?", a: "Cheaper: small classifier or cross-encoder threshold; grade only when the top score is low; batch in one call. Good: hand-label (question, chunk) pairs, measure precision (noise let in) and recall (good chunks rejected)." },
    ],
  },
  {
    id: "05", title: "Self-RAG",
    cards: [
      { fp: true, t: "Checking is easier than writing", b: "It is hard to write a perfect answer in one go. It is easier to check one claim against one source.<br><b>So:</b> draft, split into claims, verify each, then fix only the gaps. That is Self-RAG's core." },
      { t: "Reflection questions", b: "<b>Retrieve</b>: do I need to search?<br><b>IsRel</b>: is this passage relevant?<br><b>IsSup</b>: is my claim supported?<br><b>IsUse</b>: does it answer the question?<br>The paper fine-tunes these; we approximate with prompts." },
      { t: "A model doesn't know what it doesn't know", b: "Adaptive retrieval asks the model \"do you need to search?\". It said no on <b>7/35</b> doc questions and answered from memory, wrongly.<br><b>So:</b> for a domain assistant, always retrieve. Skipping turns it back into a plain chatbot." },
      { t: "Two different failures", b: "<b>Saying false things</b> (hallucination) vs <b>leaving out true things</b> (incomplete).<br>Baseline was 35/35 grounded yet missed 2: no false claims, but a needed fact was missing.<br><b>So:</b> measure groundedness AND completeness." },
      { t: "Result: the fix worked, the skip hurt", b: "baseline 33/35 (1 call) vs self-RAG 31/35 (3.3 calls).<br>Verify-and-fix repaired 2 incomplete answers; adaptive retrieval lost more than that." },
    ],
    qa: [
      { q: "Why does verify-then-fix work better than one careful draft?", a: "Checking one claim against one source is a small, clear task. Writing a full correct answer is a big, open task. Splitting the big task into small checks catches errors the writer missed." },
      { q: "Would you use adaptive retrieval?", a: "Rarely. The router is the same model, and it can't see its own knowledge gaps. It skipped 7/35 doc questions. Default to always retrieving; skip only clear small talk, and test the router on its own labelled set." },
      { q: "Grounded but wrong - how is that possible?", a: "Groundedness only checks what IS said. Every claim can be supported while a needed fact is missing. Pair it with a correctness or completeness metric." },
      { q: "How do you stop a reflect loop?", a: "Stop when every claim is supported and the question is answered. Else a hard cap (2 rounds) and a budget. Then return the last verified state or refuse. Never loop until the model \"feels\" happy." },
    ],
  },
  {
    id: "06", title: "Agent loop + tools",
    cards: [
      { fp: true, t: "A model can only write text", b: "It can't fetch a price or search an index by itself. The runtime must do it for the model. The next step often depends on the result.<br><b>So:</b> a loop. Model asks -> runtime runs the tool -> result goes back -> repeat." },
      { t: "The loop", b: "<code>repeat (max N):<br>&nbsp; resp = LLM(messages, tools)<br>&nbsp; if no tool call: return resp<br>&nbsp; run each tool, append result</code><br>ReAct (reason -> act -> observe) with native function calling. ~20 lines." },
      { t: "The schema is the whole interface", b: "The model never sees your code. It sees only the name, description, and parameters.<br><b>So:</b> one clear job per tool, say <i>when</i> to use it, typed params, compact output." },
      { t: "The model reacts only to what's in context", b: "If a tool crashes the loop, the model learns nothing. If it returns \"symbol not found; check the name\" as text, the model can recover.<br><b>Evidence:</b> FAKECOINUSDT failed; it searched the error code and explained it." },
      { t: "Who decides to stop?", b: "The model stops when it returns no tool call. That is a model decision, so it can fail.<br><b>So:</b> a step limit is the only thing that <i>guarantees</i> termination." },
      { t: "Evidence", b: "Multi-hop 5/5 at 2.2 steps. Same as the hand-written loop in lesson 3, with less code. Parallel tool calls in one step." },
    ],
    qa: [
      { q: "Why do agents need a loop at all?", a: "The model only writes text; the runtime has to act for it. And the next action depends on the last result, so you can't plan every call up front. Hence: call model, run tools, feed results back, repeat until no tool call or a limit." },
      { q: "How do you design good tools?", a: "The schema is all the model sees. So: few tools with one job each; names and descriptions that say when to use them; typed params; compact structured output; errors the model can act on; idempotent writes, kept apart from reads so you can put permissions on them." },
      { q: "RAG as a pipeline vs retrieval as a tool?", a: "Pipeline: code decides - always retrieve once. Predictable and cheap. Tool: the model decides when and what to search, and can mix sources. Flexible, but less predictable, so it needs limits, traces, and trajectory evals." },
      { q: "What breaks in agent loops, and why?", a: "Every stop/choice is a model guess: infinite loops (cap steps), repeated identical calls (detect), hallucinated args (validate schema). Context is finite: huge outputs flood it (truncate). Tool text is read like instructions: injection (lesson 7)." },
    ],
  },
  {
    id: "07", title: "Agent harness",
    cards: [
      { fp: true, t: "Must-hold rules can't live in the model", b: "A model is probabilistic, and its input can manipulate it. A prompt rule holds <i>most</i> of the time.<br><b>So:</b> anything that must ALWAYS hold (permissions, limits, saving state) goes into deterministic code around the model. That code is the harness." },
      { t: "Permissions: the hook decides", b: "The model chose to call <code>place_order</code> every time. The pre-tool hook denied unapproved orders and orders over 1,000 USDT.<br>The prompt can ask nicely; the hook decides." },
      { t: "Injection: one text stream", b: "The model reads instructions and data in the same stream. It can't reliably tell them apart.<br><b>So:</b> treat tool output as untrusted data, and keep privileged actions behind hooks. Then even a hijacked model can't act (defence in depth)." },
      { t: "Crashes: save after every step", b: "Processes crash, and LLM calls cost money.<br><b>So:</b> checkpoint after every step with an atomic write (temp file + rename). Resume by session id. Side-effect tools need idempotency keys, so a trade doesn't run twice." },
      { t: "Context is finite", b: "Every step adds tokens, and quality drops as context grows (\"context rot\"). So you must choose what stays.<br>none: 6 steps, 51k tokens. clear: <b>no answer</b> (forgot, looped). notes then clear: <b>4 steps, 12k</b>. Keep the facts, drop the raw output." },
      { t: "Prompt cache: stable prefix", b: "Providers reuse work for an identical prompt prefix.<br><b>So:</b> keep system + tools fixed and append at the end. Any edit to early context breaks the cache after that point." },
    ],
    qa: [
      { q: "What is an agent harness, and why can't the model do its job?", a: "The code around the model: loop, tool execution, checkpoints, hooks, context management, budgets, tracing. The model is probabilistic and can be manipulated, so rules that must always hold have to be enforced by deterministic code." },
      { q: "How do you stop an agent doing something dangerous?", a: "Enforce it outside the model: pre-tool hooks for permissions, limits, and human approval; credentials scoped to the minimum (Agent OS: isolated sub-accounts, no external withdrawals). The prompt asks; the hook decides." },
      { q: "Why is prompt injection hard to fix inside the model?", a: "Instructions and data arrive in the same text stream, and the model has no hard boundary between them. So defend outside it: mark tool output as untrusted, limit tools per task, gate privileged actions, log, and test with injection cases." },
      { q: "How do you manage context in long-running agents?", a: "Context is finite and quality drops as it grows. Truncate outputs at the source; clear old results but keep a short notes message so facts survive; use memory files; hand sub-tasks to subagents. Remember edits to early context break prompt caching." },
      { q: "How do you recover a session after a crash?", a: "Checkpoint full state (messages, step, budget) after every step with an atomic write. Load by session id and continue. Make side-effect tools idempotent or record started/finished, so a resume doesn't repeat a trade." },
    ],
  },
  {
    id: "08", title: "Evals",
    cards: [
      { fp: true, t: "A number is only as good as how you got it", b: "You can't improve what you can't measure. But every measurement has an <b>instrument</b> (the judge), a <b>sample</b> (the golden set), and <b>noise</b> (random outputs).<br><b>So:</b> check each of the three before you trust a score." },
      { t: "Instrument: judge the judge", b: "An LLM judge is a model, so it has errors and biases (position, length, self-preference).<br><b>So:</b> hand-label a set, measure agreement / Cohen's kappa. strict 0.94 (kappa 0.89), rubric 1.00 on 18 labels. Caveat: same author wrote labels and rubric." },
      { t: "Noise: one run is one sample", b: "Agents are random. <b>pass@k</b>: at least one of k works (fine when you can retry). <b>pass^k</b>: all k work - what users feel.<br>Independent tries multiply: 0.9^5 ≈ <b>0.59</b>." },
      { t: "Sample: a test everyone passes says nothing", b: "pass@1 = pass@3 = pass^3 = 1.00 means the benchmark is saturated. It can't tell a good change from a bad one.<br><b>So:</b> add harder cases until the best system scores 60-80%." },
      { t: "Levels: find where it broke", b: "<b>Retrieval</b> (hit@k, MRR) -> <b>answer</b> (correct, grounded, refuses) -> <b>end to end</b> (success, latency, cost) -> <b>trajectory</b> (steps, repeats, unsafe actions).<br>Each level points to a different part to fix." },
      { t: "Regression gate", b: "Every change can break something you didn't touch.<br><b>So:</b> save metrics in <code>baseline.json</code>, compare on every prompt/model/tool change, exit 1 if a metric drops beyond tolerance (0.02 for deterministic)." },
    ],
    qa: [
      { q: "How do you evaluate a RAG or agent system?", a: "In layers, so a failure points to a part: retrieval (recall@k, MRR), answer (correctness, groundedness, refusal), end to end (success, latency, cost), trajectory (steps, repeats, unsafe actions). Offline in CI on every change; online feedback turns failures into new cases." },
      { q: "Can you trust LLM-as-judge? Why or why not?", a: "It is a model, so it is an instrument with its own errors. Trust it only after calibration: hand-label, measure kappa, read disagreements, fix the rubric, test on a held-out set. Human-human agreement is the ceiling." },
      { q: "Why does pass^k drop so fast?", a: "All k tries must succeed, and independent tries multiply: p^k. 90% per try -> pass^5 ≈ 59%. For a user-facing agent, that consistency is what users feel." },
      { q: "Your benchmark scores 100%. Good news?", a: "No: it carries no information now. It can't show if a change helped or hurt. Add harder cases (3+ hops, conflicting sources, live data, injection) until the best system scores 60-80%." },
      { q: "How do you build a benchmark for a new domain?", a: "Real user questions and production failures; labelled sources and answers with guidelines; edge cases (unanswerable, multi-hop, adversarial); versioned; held-out split; check contamination; keep it hard." },
    ],
  },
];
