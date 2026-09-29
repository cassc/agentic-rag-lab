"""Render docs/diagrams/src/workspace.dsl to PNG via kroki.io and rebuild docs/diagrams/README.md."""

from pathlib import Path
from urllib.request import Request, urlopen

VIEWS = ["Context", "Containers", "Ingest", "L1_Naive", "L2_Hybrid", "L3_MultiHop",
         "L4_CRAG", "L5_SelfRAG", "L6_AgentLoop", "L7_Harness"]
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
    for v in VIEWS:
        (DIR / "png" / f"{v}.png").write_bytes(render(dsl, v))
        md += ["", f"## {v}", "", f"![{v}](png/{v}.png)"]
        print(v)
    (DIR / "README.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
