"""Heading-aware Markdown chunking. Each chunk keeps its heading path as context."""
import re
from dataclasses import dataclass
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "data" / "docs"


@dataclass
class Chunk:
    id: str
    doc: str
    heading: str
    text: str

    @property
    def full(self):
        # Prepending doc + heading is "contextual chunking": a chunk like
        # "UTC" alone is useless, "order_count_decrement > Which time zone...?" is not.
        return f"[{self.doc}] {self.heading}\n{self.text}"


def split_markdown(doc, md, max_chars=1200):
    chunks, path, paras, buf, in_code = [], [], [], [], False

    def flush_para():
        if buf:
            paras.append("\n".join(buf))
            buf.clear()

    def flush_section():
        flush_para()
        pack = ""
        for p in paras:
            if pack and len(pack) + len(p) > max_chars:
                chunks.append(Chunk(f"{doc}#{len(chunks)}", doc, " > ".join(path), pack))
                pack = ""
            pack = f"{pack}\n\n{p}" if pack else p
        if pack.strip():
            chunks.append(Chunk(f"{doc}#{len(chunks)}", doc, " > ".join(path), pack))
        paras.clear()

    for line in md.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        m = None if in_code else re.match(r"(#{1,4})\s+(.*)", line)
        if m:
            flush_section()
            path[:] = path[: len(m.group(1)) - 1] + [m.group(2).strip()]
        elif not line.strip() and not in_code:
            flush_para()
        else:
            buf.append(line)
    flush_section()
    return chunks


def load_chunks(max_chars=1200):
    return [c for p in sorted(DOCS.glob("*.md"))
            for c in split_markdown(p.stem, p.read_text(), max_chars)]
