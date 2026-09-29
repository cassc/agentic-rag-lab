"""Render docs/diagrams/src/workspace.dsl to PNG via kroki.io and rebuild docs/diagrams/README.md."""

from pathlib import Path
from urllib.request import Request, urlopen

VIEWS = {
    "Context": "System context: the lab, who uses it, and the outside systems it talks to.",
    "Containers": "The main parts inside the lab (code, indexes, models) and how they connect.",
    "Ingest": "Offline step: split the documents into chunks and build both indexes once.",
    "L1_Naive": "Lesson 1, naive RAG (Retrieval-Augmented Generation): retrieve once, then answer.",
    "L2_Hybrid": "Lesson 2, hybrid search: dense (vector) + keyword (BM25) search, fuse the results, then rerank.",
    "L3_MultiHop": "Lesson 3, multi-hop: split the question into sub-questions and retrieve for each one.",
    "L4_CRAG": "Lesson 4, CRAG (Corrective RAG): grade the retrieved chunks, fix bad retrieval, then answer.",
    "L5_SelfRAG": "Lesson 5, Self-RAG: the model decides if it needs retrieval, drafts, checks its own claims, and fills gaps.",
    "L6_AgentLoop": "Lesson 6, agent loop: the model picks tools again and again until it can answer.",
    "L7_Harness": "Lesson 7, harness: the same agent loop, plus hooks that check each tool call and checkpoints to save and resume a session.",
}
DIR = Path(__file__).resolve().parent.parent / "docs" / "diagrams"


def render(dsl: bytes, view: str) -> bytes:
    req = Request(f"https://kroki.io/structurizr/png?view-key={view}", data=dsl,
                  headers={"Content-Type": "text/plain", "User-Agent": "agentic-rag-lab"})
    with urlopen(req, timeout=60) as r:
        return r.read()


def main():
    dsl = (DIR / "src" / "workspace.dsl").read_bytes()
    (DIR / "png").mkdir(exist_ok=True)
    md = ["# Diagrams", "",
          "Generated from `src/workspace.dsl` by `scripts/diagrams.py`. Edit the DSL, not this file."]
    for v, desc in VIEWS.items():
        (DIR / "png" / f"{v}.png").write_bytes(render(dsl, v))
        md += ["", f"## {v}", "", desc, "", f"![{v}](png/{v}.png)"]
        print(v)
    (DIR / "README.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
