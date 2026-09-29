# Agentic RAG Lab

Learn agentic RAG, agent harnesses, and evaluation by building them - small,
from scratch, no framework - over Binance's public Spot API docs.

Each lesson explains the concept, runs a script that produces real numbers,
and ends with review questions. The numbers are honest, including the cases
where the fancier method did not help.

- **Start here:** [CHEATSHEET.md](CHEATSHEET.md) - all concepts on one page.
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

## Setup

```sh
uv sync                                  # CPU PyTorch (default)
uv run scripts/fetch_docs.py             # pinned Binance docs -> data/docs/
cp .env.example .env                     # LLM key: LLM_API_KEY, or DEEPSEEK_API_KEY from your shell
uv run lessons/01_naive_rag/run.py
```

LLM: any OpenAI-compatible API (DeepSeek by default). Change `LLM_BASE_URL`,
`LLM_MODEL`, `LLM_API_KEY` to use OpenAI, OpenRouter, Ollama, vLLM, etc.

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
lab/        shared code: chunk, embed, index, retrieve, llm, rag, evals,
            judge, verify, tools, agent (the harness)
lessons/    one folder per lesson: README.md (concepts + review Q&A) + run.py
evals/      golden.jsonl - 35 questions (25 single-hop, 5 multi-hop, 5 unanswerable)
            judge_labels.jsonl (judge calibration), baseline.json (regression gate)
scripts/    fetch_docs.py, diagrams.py
docs/       embedding models, diagrams
```

## License

MIT. See [LICENSE](LICENSE).
