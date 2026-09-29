# Diagrams

Generated from `src/workspace.dsl` by `scripts/diagrams.py`. Edit the DSL, not this file.

## Context

System context: the lab, who uses it, and the outside systems it talks to.

![Context](png/Context.png)

## Containers

The main parts inside the lab (code, indexes, models) and how they connect.

![Containers](png/Containers.png)

## Ingest

Offline step: split the documents into chunks and build both indexes once.

![Ingest](png/Ingest.png)

## L1_Naive

Lesson 1, naive RAG (Retrieval-Augmented Generation): retrieve once, then answer.

![L1_Naive](png/L1_Naive.png)

## L2_Hybrid

Lesson 2, hybrid search: dense (vector) + keyword (BM25) search, fuse the results, then rerank.

![L2_Hybrid](png/L2_Hybrid.png)

## L3_MultiHop

Lesson 3, multi-hop: split the question into sub-questions and retrieve for each one.

![L3_MultiHop](png/L3_MultiHop.png)

## L4_CRAG

Lesson 4, CRAG (Corrective RAG): grade the retrieved chunks, fix bad retrieval, then answer.

![L4_CRAG](png/L4_CRAG.png)

## L5_SelfRAG

Lesson 5, Self-RAG: the model decides if it needs retrieval, drafts, checks its own claims, and fills gaps.

![L5_SelfRAG](png/L5_SelfRAG.png)

## L6_AgentLoop

Lesson 6, agent loop: the model picks tools again and again until it can answer.

![L6_AgentLoop](png/L6_AgentLoop.png)

## L7_Harness

Lesson 7, harness: the same agent loop, plus hooks that check each tool call and checkpoints to save and resume a session.

![L7_Harness](png/L7_Harness.png)
