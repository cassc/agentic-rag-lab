workspace "Agentic RAG Lab" "How the pieces of a RAG / agentic RAG system connect." {

    model {
        user = person "Engineer" "Asks questions, reads answers and eval scores."

        docs = softwareSystem "Binance Spot API docs" "Markdown on GitHub, pinned commit." "External"
        llmApi = softwareSystem "LLM API" "Any OpenAI-compatible API. DeepSeek by default." "External"
        hf = softwareSystem "Hugging Face models" "Embedding models and cross-encoder rerankers." "External"
        market = softwareSystem "Binance market API" "Public live data: prices, symbol filters." "External"

        lab = softwareSystem "Agentic RAG Lab" {
            ingest = container "Ingest" "Downloads docs, splits them into heading-aware chunks." "fetch_docs.py, lab/chunk.py"
            embedder = container "Embedder" "Turns text into normalized vectors." "sentence-transformers"
            vindex = container "Vector index" "Dense search: dot product over a numpy matrix, cached as .npy." "lab/index.py" "Store"
            bm25 = container "Keyword index" "Sparse search: BM25 over tokens. Wins on exact IDs like -1021." "rank_bm25" "Store"
            fusion = container "Fusion" "Reciprocal Rank Fusion: merges ranked lists by rank, not score." "lab/retrieve.py"
            rerank = container "Reranker" "Cross-encoder reads (query, chunk) together. Slow, precise." "sentence-transformers"
            orch = container "Orchestrator" "Runs the pipeline or the agent loop. Enforces max steps and budget." "lessons/*/run.py"
            planner = container "Query planner" "Splits a question into sub-questions; rewrites weak queries." "LLM prompt"
            grader = container "Grader" "Labels retrieved chunks: correct / ambiguous / wrong (CRAG)." "LLM prompt"
            generator = container "Generator" "Writes a grounded answer with [n] citations." "LLM prompt"
            verifier = container "Verifier" "Splits an answer into claims; checks each is stated by a source (Self-RAG)." "lab/verify.py"
            tools = container "Tools" "search_docs, get_price, get_symbol_filters, place_order (dry run)." "lab/tools.py"
            hooks = container "Hooks" "pre_tool: permissions, approval, limits. post_tool: truncate, flag injection." "lessons/07_harness"
            sessions = container "Session store" "Checkpoint after every step; resume after a crash." "data/sessions/*.json" "Store"
            evals = container "Eval harness" "Golden set; hit@k, MRR; later groundedness and task success." "lab/evals.py"
        }

        ingest -> docs "Downloads markdown"
        ingest -> embedder "Sends chunks"
        ingest -> bm25 "Builds keyword index"
        embedder -> vindex "Writes chunk vectors"
        embedder -> hf "Loads model"
        rerank -> hf "Loads model"

        user -> orch "Asks a question"
        orch -> embedder "Embeds the query"
        orch -> vindex "Dense top-k"
        orch -> bm25 "Keyword top-k"
        orch -> fusion "Merges ranked lists"
        orch -> rerank "Reranks the pool"
        orch -> planner "Plans / rewrites queries"
        orch -> grader "Grades retrieved chunks"
        orch -> generator "Answers from chunks"
        planner -> llmApi "Calls"
        grader -> llmApi "Calls"
        generator -> llmApi "Calls"
        evals -> orch "Runs golden questions"
        orch -> verifier "Checks claims against sources"
        verifier -> llmApi "Calls"
        orch -> llmApi "Asks for the next action (tool call or answer)"
        orch -> tools "Runs the chosen tool"
        orch -> hooks "Asks before and after each tool call"
        orch -> sessions "Saves / loads checkpoint"
        tools -> market "Reads live data"
        tools -> fusion "search_docs uses hybrid search"
    }

    views {
        systemContext lab "Context" {
            include *
            autoLayout lr
        }

        container lab "Containers" {
            include *
            autoLayout lr
        }

        dynamic lab "Ingest" "Offline: build both indexes once." {
            ingest -> docs "Download pinned docs"
            ingest -> bm25 "Build keyword index"
            ingest -> embedder "Embed every chunk"
            embedder -> vindex "Store vectors (cache .npy)"
            autoLayout lr
        }

        dynamic lab "L1_Naive" "Lesson 1: retrieve once, then answer." {
            user -> orch "Question"
            orch -> embedder "Embed query"
            orch -> vindex "Top 5 by cosine"
            orch -> generator "Answer with citations"
            autoLayout lr
        }

        dynamic lab "L2_Hybrid" "Lesson 2: dense + keyword, fuse, rerank." {
            user -> orch "Question"
            orch -> vindex "Dense top 20"
            orch -> bm25 "Keyword top 20"
            orch -> fusion "RRF -> top 20 pool"
            orch -> rerank "Keep best 5"
            orch -> generator "Answer with citations"
            autoLayout lr
        }

        dynamic lab "L3_MultiHop" "Lesson 3: decompose, retrieve per sub-question." {
            user -> orch "Question needing 2+ facts"
            orch -> planner "Split into sub-questions"
            orch -> vindex "Retrieve for sub-question 1"
            orch -> planner "Use answer 1 to write query 2"
            orch -> vindex "Retrieve for sub-question 2"
            orch -> generator "Combine and answer"
            autoLayout lr
        }

        dynamic lab "L4_CRAG" "Lesson 4: grade, then correct before answering." {
            user -> orch "Question"
            orch -> vindex "Retrieve"
            orch -> grader "Grade chunks"
            orch -> planner "If wrong/ambiguous: rewrite query"
            orch -> bm25 "Retry with rewritten query"
            orch -> grader "Grade again (max N tries)"
            orch -> generator "Answer, or say not found"
            autoLayout lr
        }

        dynamic lab "L5_SelfRAG" "Lesson 5: decide, draft, verify claims, fix the gap." {
            user -> orch "Question"
            orch -> planner "Need retrieval? (adaptive)"
            orch -> fusion "Hybrid top 5"
            orch -> generator "Draft with citations"
            orch -> verifier "Every claim supported?"
            orch -> vindex "If not: search the missing part"
            orch -> generator "Redraft without unsupported claims"
            orch -> verifier "Verify again (max 2 rounds)"
            autoLayout lr
        }

        dynamic lab "L6_AgentLoop" "Lesson 6: the model picks tools until it can answer." {
            user -> orch "Task"
            orch -> llmApi "Messages + tool schemas"
            orch -> tools "Run tool call(s)"
            tools -> market "Live filters / price"
            tools -> fusion "Doc search"
            orch -> llmApi "Tool results appended; next action"
            autoLayout lr
        }

        dynamic lab "L7_Harness" "Lesson 7: the same loop inside a harness." {
            user -> orch "Task"
            orch -> sessions "Load checkpoint (resume if found)"
            orch -> llmApi "Next action"
            orch -> hooks "pre_tool: allowed? approved? under limit?"
            orch -> tools "Run tool (only if allowed)"
            orch -> hooks "post_tool: truncate, flag injection"
            orch -> sessions "Save checkpoint"
            autoLayout lr
        }

        styles {
            element "Element" {
                background #1168bd
                color #ffffff
                shape RoundedBox
            }
            element "Person" {
                shape Person
                background #08427b
            }
            element "External" {
                background #8a8a8a
            }
            element "Store" {
                shape Cylinder
            }
        }
    }
}
