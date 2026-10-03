// Diagram slides per lesson id: img = repo-relative path (optional), steps in order (s = step, n = why note, loop = repeats).
const DIAGRAMS = {
  "00": [
    { img: "docs/diagrams/png/Containers.png", t: "Architecture: the parts a question meets", steps: [
      { s: "Ingest (offline)", n: "Pinned docs become heading-aware chunks. <code>lab/chunk.py:58-60</code>" },
      { s: "Embedder + vector index", n: "Chunks become normalized vectors, cached on disk. <code>lab/index.py:10-19</code>" },
      { s: "Keyword index (BM25)", n: "Built in memory each run. Keeps exact tokens. <code>lab/retrieve.py:13-16</code>" },
      { s: "Orchestrator: one lesson script", n: "It owns the flow and the limits (max hops, max steps). <code>lessons/03_multi_hop/run.py:44-56</code>" },
      { s: "Fusion + reranker", n: "Merge by rank, then a slow precise model reorders a small pool. <code>lab/retrieve.py:24-47</code>" },
      { s: "LLM prompts: planner, grader, generator, verifier", n: "All go through one client, so the model is easy to swap. <code>lab/llm.py:22-34</code>" },
      { s: "Tools, hooks, session store", n: "Agent lessons only. Hooks run before and after each tool. <code>lab/agent.py:79-88</code>" },
      { s: "Eval harness", n: "Runs the golden questions through any of the parts above. <code>lab/evals.py:33-48</code>" },
    ] },
    { t: "Request trace: one question through naive RAG", steps: [
      { s: "Run the lesson with a question", n: "The script is the entry point. No server. <code>lessons/01_naive_rag/run.py:21-23</code>" },
      { s: "Load and split the docs", n: "Done at start, because every later step works on chunks. <code>lab/chunk.py:58-60</code>" },
      { s: "Load the embedding model", n: "Query and chunks must use the same model, or the vectors can't be compared. <code>lab/embed.py:16-21</code>" },
      { s: "Build or load the vector index", n: "Embedding is slow, so vectors are cached by model + content hash. <code>lab/index.py:10-19</code>" },
      { s: "Embed the question, take the top 5", n: "One dot product over all chunks. This is the only retrieval. <code>lab/index.py:21-24</code>" },
      { s: "Number the chunks as sources", n: "The numbers let the model cite [n]. <code>lab/rag.py:8-9</code>" },
      { s: "Build the grounded prompt", n: "Rules + sources + question, temperature 0 for stable output. <code>lab/rag.py:12-15</code>" },
      { s: "Call the LLM", n: "One call through the shared client. <code>lab/llm.py:22-28</code>" },
      { s: "Print the answer with citations", n: "<code>lessons/01_naive_rag/run.py:26</code>" },
    ] },
  ],
  "01": [
    { img: "docs/diagrams/png/Ingest.png", t: "Offline: build the indexes once", steps: [
      { s: "Download pinned docs", n: "Pinned = same docs every run, so numbers are comparable." },
      { s: "Build keyword index (BM25)", n: "Used from lesson 2 for exact IDs." },
      { s: "Embed every chunk", n: "Chunks carry their heading path, so small chunks keep context." },
      { s: "Store vectors (cache .npy)", n: "Same docs + chunking = same hash, so no re-embedding." },
    ] },
    { img: "docs/diagrams/png/L1_Naive.png", t: "Naive RAG: retrieve once, then answer", steps: [
      { s: "Question", n: "The user's exact words are the query. Nothing is rewritten." },
      { s: "Embed query", n: "Same model as the chunks, normalized vector." },
      { s: "Top 5 by cosine", n: "One matrix multiply. This is the ONLY retrieval - the weak point for multi-hop." },
      { s: "Answer with citations", n: "Grounding prompt: only from sources, else 'Not in the sources'." },
    ] },
  ],
  "02": [
    { img: "docs/diagrams/png/L2_Hybrid.png", t: "Hybrid: dense + keyword, fuse, rerank", steps: [
      { s: "Question", n: "" },
      { s: "Dense top 20", n: "Finds meaning. Wide pool on purpose." },
      { s: "Keyword top 20", n: "Finds exact tokens like -1021." },
      { s: "RRF -> top 20 pool", n: "Ranks only: sum 1/(60 + rank). No score scaling." },
      { s: "Rerank, keep best 5", n: "Cross-encoder reads (question, chunk) together. Precise, slower." },
      { s: "Answer with citations", n: "" },
    ] },
  ],
  "03": [
    { img: "docs/diagrams/png/L3_MultiHop.png", t: "Multi-hop: one fact leads to the next", steps: [
      { s: "Question needing 2+ facts", n: "One embedding sits 'between' the facts and matches none well." },
      { s: "Split into sub-questions", n: "Decomposition. Stops here if sub-questions are independent (parallel)." },
      { s: "Retrieve for sub-question 1", n: "" },
      { s: "Use answer 1 to write query 2", n: "Iterative hop: the next query uses what hop 1 found.", loop: true },
      { s: "Retrieve for sub-question 2", n: "Max 3 hops; stops early when notes already have everything.", loop: true },
      { s: "Combine and answer", n: "Still grounded: only from retrieved sources." },
    ] },
  ],
  "04": [
    { img: "docs/diagrams/png/L4_CRAG.png", t: "CRAG: grade, then correct", steps: [
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
    { img: "docs/diagrams/png/L5_SelfRAG.png", t: "Self-RAG: decide, draft, verify, fix", steps: [
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
    { img: "docs/diagrams/png/L6_AgentLoop.png", t: "Agent loop: the model picks tools", steps: [
      { s: "Task", n: "" },
      { s: "Messages + tool schemas -> LLM", n: "The model sees schemas, not code.", loop: true },
      { s: "Run tool call(s)", n: "Can be several in parallel in one step.", loop: true },
      { s: "Live filters / price, doc search", n: "Errors come back as text so the model can recover.", loop: true },
      { s: "Results appended; next action", n: "No tool call = final answer. Step limit guarantees termination.", loop: true },
    ] },
  ],
  "07": [
    { img: "docs/diagrams/png/L7_Harness.png", t: "Harness: the same loop, made safe", steps: [
      { s: "Task", n: "" },
      { s: "Load checkpoint (resume if found)", n: "Same session id -> no repeated work after a crash." },
      { s: "LLM: next action", n: "", loop: true },
      { s: "pre_tool hook: allowed? approved? under limit?", n: "The hook decides, not the prompt.", loop: true },
      { s: "Run tool (only if allowed)", n: "", loop: true },
      { s: "post_tool hook: truncate, flag injection", n: "Regex flag is a signal, not a defence.", loop: true },
      { s: "Save checkpoint (atomic write)", n: "Temp file + rename: a crash can't corrupt it.", loop: true },
    ] },
  ],
  "09": [
    { t: "Durable run: crash, then replay", steps: [
      { s: "Open the log for this run id", n: "The same id after a crash finds the same history. <code>lab/durable.py:29-33</code>" },
      { s: "Workflow asks for the next step", n: "Only step() calls and pure logic, so a second run asks the same things. <code>lessons/09_durable/run.py:31-35</code>" },
      { s: "In the log? Return the logged result", n: "Replay: no LLM call, no tool call. The name must match. <code>lab/durable.py:43-49</code>", loop: true },
      { s: "Not in the log: run it, with retries", n: "Short failures are retried with a growing wait. <code>lab/durable.py:50-58</code>", loop: true },
      { s: "Append the result and fsync", n: "On disk before the code goes on. <code>lab/durable.py:61-65</code>", loop: true },
      { s: "Crash? Run the same function again", n: "It starts from the top; finished steps are replayed. <code>lessons/09_durable/run.py:68-70</code>" },
    ] },
  ],
  "10": [
    { t: "One LLM call through the gateway", steps: [
      { s: "Take the next provider in the chain", n: "Same model on another provider first: same behaviour. <code>lab/gateway.py:79-80</code>" },
      { s: "Breaker open? Skip this provider", n: "Do not pay a dead provider's timeout again. <code>lab/gateway.py:81-83</code>", loop: true },
      { s: "Call the provider", n: "Provider-specific fields are set here, not by the caller. <code>lab/gateway.py:50-58</code>", loop: true },
      { s: "Error worth a retry? Wait, try again", n: "Backoff with jitter. A 400 or 401 fails at once. <code>lab/gateway.py:91-98</code>", loop: true },
      { s: "Too many failures: open the breaker, go to the next provider", n: "<code>lab/gateway.py:94-96</code>", loop: true },
      { s: "Validate the output; send errors back to repair", n: "The validator decides, not the prompt. <code>lab/gateway.py:105-115</code>" },
    ] },
  ],
  "11": [
    { t: "Memory: write after a session, read before an answer", steps: [
      { s: "Session ends: load this user's existing memories", n: "The writer must see old facts to replace them. <code>lab/memory.py:36</code>" },
      { s: "LLM turns the transcript into add / update operations", n: "Only lasting facts; small talk is dropped. <code>lab/memory.py:37-42</code>" },
      { s: "Apply: update only rows of this user", n: "An id of another user's row is never touched. <code>lab/memory.py:43-49</code>" },
      { s: "New question: embed it", n: "<code>lab/memory.py:52-56</code>" },
      { s: "Top 3 memories of this user go into the prompt", n: "A few lines, not the whole history. <code>lab/memory.py:56-57</code>" },
    ] },
  ],
  "12": [
    { t: "Supervisor with workers as tools", steps: [
      { s: "Supervisor reads the question", n: "It has no tools of its own, only workers. <code>lab/multi.py:7-11</code>" },
      { s: "It writes a brief for each worker", n: "The worker sees nothing but this text. <code>lab/multi.py:23-25</code>", loop: true },
      { s: "Each worker runs its own loop with its own tools", n: "A fresh context per worker. <code>lab/multi.py:36-39</code>", loop: true },
      { s: "Only the worker's final answer comes back", n: "The searches stay out of the supervisor's window. <code>lab/multi.py:39</code>", loop: true },
      { s: "Supervisor writes the answer, or delegates again", n: "The loop risk: its step limit is the only stop. <code>lab/multi.py:44-46</code>" },
      { s: "Add up calls and tokens of the whole tree", n: "Cost is the tree, not the top agent. <code>lab/multi.py:47-49</code>" },
    ] },
  ],
  "13": [
    { t: "A job through the queue", steps: [
      { s: "Producer sends a job with a dedupe key", n: "The same key twice makes one job. <code>lab/bus.py:36-41</code>" },
      { s: "Worker claims a job; it is hidden for a while", n: "Hidden, not removed: it comes back if the worker dies. <code>lab/bus.py:43-55</code>", loop: true },
      { s: "Worker does the work (idempotent)", n: "A repeat must be harmless. <code>lessons/13_events/run.py:84-91</code>", loop: true },
      { s: "Ack: the job is done", n: "No ack means it will be delivered again. <code>lab/bus.py:57-58</code>", loop: true },
      { s: "Too many attempts: dead letter", n: "A poison job must not loop forever. <code>lab/bus.py:45-48</code>" },
      { s: "Each change is appended as an event, with a version check", n: "State and read models are built from these. <code>lab/bus.py:70-77</code>" },
    ] },
  ],
  "14": [
    { t: "One run as a trace", steps: [
      { s: "Start the root span for the run", n: "Tenant and task id go on it, to filter later. <code>lab/trace.py:44-46</code>" },
      { s: "LLM call: a child span with tokens", n: "Input, output and cached tokens. <code>lab/trace.py:23-32</code>", loop: true },
      { s: "Tool calls: child spans, context copied into each thread", n: "Without the copy they would be separate traces. <code>lab/loop.py:33-38</code>", loop: true },
      { s: "A tool error marks its span", n: "The run can still succeed. <code>lab/trace.py:35-41</code>", loop: true },
      { s: "Run ends: read the spans", n: "Time per span type, tokens per run, runs over budget. <code>lessons/14_observability/run.py:60-68</code>" },
      { s: "Decide which traces to keep", n: "Errors and slow runs, decided at the end. <code>lessons/14_observability/run.py:86-91</code>" },
    ] },
  ],
  "15": [
    { t: "A tool call through the MCP gateway", steps: [
      { s: "Gateway starts each server in the registry and lists its tools", n: "stdio transport: child processes, no port. <code>lab/mcp_gateway.py:29-35</code>" },
      { s: "Compare the tool fingerprint with the approved one", n: "Changed definitions block the server. <code>lab/mcp_gateway.py:36-39</code>" },
      { s: "Build the tool list for the agent's role", n: "Fewer tools: fewer tokens, easier choice. <code>lab/mcp_gateway.py:52-56</code>" },
      { s: "Agent asks for a tool by name", n: "", loop: true },
      { s: "Gateway checks the role again", n: "A hidden tool can still be named. <code>lab/mcp_gateway.py:58-62</code>", loop: true },
      { s: "Call the server, write the audit row", n: "<code>lab/mcp_gateway.py:63-65</code>", loop: true },
    ] },
  ],
  "16": [
    { t: "The agent as a LangGraph state machine", steps: [
      { s: "START -> model node", n: "Calls the LLM, returns an update to the state. <code>lab/runtime.py:58-66</code>" },
      { s: "Route: no tool calls -> END", n: "Decided in code, not by the framework. <code>lab/runtime.py:68-72</code>", loop: true },
      { s: "Route: risky tool -> approval node (pause)", n: "The graph stops here; the state is saved. <code>lab/runtime.py:49-56</code>", loop: true },
      { s: "tools node runs the tool calls", n: "The same tool functions as the own loop. <code>lab/runtime.py:74-78</code>", loop: true },
      { s: "Back to the model node", n: "A checkpoint is written after every node.", loop: true },
      { s: "Resume a paused thread later", n: "invoke(None) continues from the checkpoint. <code>lab/runtime.py:90-92</code>" },
    ] },
  ],
  "17": [
    { t: "A run through the service", steps: [
      { s: "POST /runs with an Idempotency-Key", n: "A retry of the same key returns the first run. <code>lab/service.py:57-60</code>" },
      { s: "Admission: backlog full or tenant over its limit -> 429", n: "Backpressure reaches the client. <code>lab/service.py:61-64</code>" },
      { s: "Create the run, enqueue, answer 202 + run id", n: "The API never waits for the run. <code>lab/service.py:65-73</code>" },
      { s: "A worker takes the job and runs the agent", n: "Workers hold no state. <code>lab/service.py:97-108</code>" },
      { s: "Progress is written as events", n: "One version counter per run keeps them in order. <code>lab/service.py:52-54</code>", loop: true },
      { s: "Client polls GET /runs/{id} or reads the event stream", n: "<code>lab/service.py:79-95</code>" },
      { s: "Run finished: free the tenant's slot, ack the job", n: "<code>lab/service.py:109-115</code>" },
    ] },
  ],
  "18": [
    { t: "One run through the platform (design)", steps: [
      { s: "Client calls the API gateway with a token", n: "The token gives the tenant and the roles. <code>docs/design/agent-runtime.md:21-24</code>" },
      { s: "Runs API: idempotency key, admission, 202 + run id", n: "Stateless. Refuses with 429 when the tenant is over its share. <code>docs/design/agent-runtime.md:86-99</code>" },
      { s: "Workflow engine starts the run", n: "Its history is the source of truth. <code>docs/design/agent-runtime.md:49-54</code>" },
      { s: "A worker runs the agent loop", n: "Stateless: any worker can continue after a crash. <code>docs/design/agent-runtime.md:56-59</code>" },
      { s: "LLM call through the LLM gateway", n: "Failover, quotas, cost in one place. <code>docs/design/agent-runtime.md:66-70</code>", loop: true },
      { s: "Tool call through the MCP gateway", n: "Role check and audit on every call.", loop: true },
      { s: "State and events are written", n: "Status, memory, big payloads each go to their own store. <code>docs/design/agent-runtime.md:101-110</code>", loop: true },
      { s: "Client reads status or the event stream", n: "From read models, not from the engine." },
    ] },
  ],
};
