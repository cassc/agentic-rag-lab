# Agentic RAG Lab

Learn agentic RAG, agent harnesses, evaluation, and the **agent runtime**
around them by building each part - small and from scratch - over Binance's
public Spot API docs.

Two tracks:

- **Lessons 1-8, agentic RAG:** retrieval, agent loop, harness, evals. No
  framework.
- **Lessons 9-17, agent runtime:** durable execution, LLM gateway, memory,
  multi-agent, event-driven workers, observability, MCP, frameworks, and a
  service under load. Each part is built from scratch first, then compared
  with the real tool where one is the standard (Temporal, OpenTelemetry,
  MCP SDK, LangGraph, FastAPI).

Each lesson explains the concept, runs a script that produces real numbers,
and ends with review questions. The numbers are honest, including the cases
where the fancier method did not help.

- **Start here:** [CHEATSHEET.md](CHEATSHEET.md) - all concepts on one page.
- **Study cards + quiz:** `uv run web/server.py`, open http://127.0.0.1:8765.
  Slide cards, likely questions, a quiz, and a chat where Claude Code quizzes
  you (needs the `claude` CLI). Without the server, open `web/index.html`
  directly (no chat).
- **Diagrams:** [docs/diagrams](docs/diagrams/README.md) (Structurizr C4 +
  dynamic views; PNGs; source in `src/workspace.dsl`).
- **Models:** [docs/embedding-models.md](docs/embedding-models.md).
- **Metrics:** [docs/retrieval-metrics.md](docs/retrieval-metrics.md) - recall,
  precision, hit@k, MRR, RRF vs rerank.

## Lessons

| # | Topic | Status |
| --- | --- | --- |
| 01 | [Naive RAG](lessons/01_naive_rag/README.md): chunk, embed, retrieve, answer | done |
| 02 | [Hybrid search + reranking](lessons/02_hybrid_rerank/README.md) | done |
| 03 | [Query decomposition + multi-hop](lessons/03_multi_hop/README.md) | done |
| 04 | [CRAG](lessons/04_crag/README.md): grade retrieved chunks, rewrite, retry | done |
| 05 | [Self-RAG](lessons/05_self_rag/README.md): decide, verify claims, fix the gap | done |
| 06 | [Agent loop + tool calling](lessons/06_agent_loop/README.md), docs + live market data | done |
| 07 | [Harness](lessons/07_harness/README.md): resume, hooks, injection, compaction | done |
| 08 | [Evals](lessons/08_evals/README.md): judge calibration, pass^k, regression gate | done |
| 09 | [Durable execution](lessons/09_durable/README.md): event log, replay, retries, idempotency; then Temporal | done |
| 10 | [LLM gateway](lessons/10_gateway/README.md): failover, circuit breaker, routing, structured output, streaming | done |
| 11 | [Memory and state](lessons/11_memory/README.md): extract, update, scope per user | done |
| 12 | [Multi-agent](lessons/12_multi_agent/README.md): supervisor + workers vs one agent, failure modes | done |
| 13 | [Event-driven runtime](lessons/13_events/README.md): queue, backpressure, dead letters, event sourcing, CQRS | done |
| 14 | [Observability](lessons/14_observability/README.md): OpenTelemetry traces, cost, latency budgets, sampling | done |
| 15 | [MCP](lessons/15_mcp/README.md): tool servers, registry, gateway with roles, tool poisoning | done |
| 16 | [Frameworks](lessons/16_framework/README.md): one interface, own loop vs LangGraph, how to migrate | done |
| 17 | [Runtime as a service](lessons/17_service/README.md): FastAPI, idempotent API, overload, noisy tenant | done |

**Design document:** [docs/design/agent-runtime.md](docs/design/agent-runtime.md) -
the whole runtime for hundreds of agents: architecture, decisions with
trade-offs, API contract, AWS / EKS / Terraform mapping, failure modes.

## Setup

```sh
uv sync                                  # CPU PyTorch (default)
uv run scripts/fetch_docs.py             # pinned Binance docs -> data/docs/
cp .env.example .env                     # LLM key: LLM_API_KEY, or DEEPSEEK_API_KEY from your shell
uv run lessons/01_naive_rag/run.py
export HF_HUB_OFFLINE=1                  # after the first run: models are cached, skip Hub checks
```

LLM: any OpenAI-compatible API (DeepSeek by default). Change `LLM_BASE_URL`,
`LLM_MODEL`, `LLM_API_KEY` to use OpenAI, OpenRouter, Ollama, vLLM, etc.

Extra needs of the runtime lessons:

| Lesson | Needs |
| --- | --- |
| 09 (Temporal part) | a Temporal server: `--dev-server` lets the SDK download and start one on 127.0.0.1, or set `TEMPORAL_ADDRESS` |
| 10 | two providers: `DEEPSEEK_API_KEY` and `OPENROUTER_API_KEY` |
| 13, 17 (A-D) | nothing: no LLM calls |
| 15 | nothing extra: MCP servers run as child processes over stdio, no port |
| 17 `serve` | opens `127.0.0.1:8770` (loopback only) |

### GPU PC (bigger embedding models)

```sh
uv sync --no-default-groups --group gpu  # CUDA PyTorch
EMBED_MODEL=gte-qwen2 uv run --no-sync lessons/01_naive_rag/run.py
```

Use `--no-sync` so `uv run` doesn't swap back to CPU PyTorch. The vectors are
cached in `data/index/<model>-<hash>.npy`. Copy that file to the CPU machine
and the lessons use it without re-embedding (same docs + chunking = same hash).
Query embedding still loads the model, but one query is fast even on CPU.

## Layout

```
lab/        shared code. RAG: chunk, embed, index, retrieve, llm, rag, evals,
            judge, verify, tools, agent (the harness).
            Runtime: loop, durable, gateway, memory, multi, bus, trace,
            mcp_gateway, runtime, service
lessons/    one folder per lesson: README.md (concepts + review Q&A) + run.py
evals/      golden.jsonl - 35 questions (25 single-hop, 5 multi-hop, 5 unanswerable)
            judge_labels.jsonl (judge calibration), baseline.json (regression gate)
scripts/    fetch_docs.py, diagrams.py
docs/       embedding models, diagrams, design/agent-runtime.md
```

## License

MIT. See [LICENSE](LICENSE).
