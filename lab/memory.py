"""Long-term memory for an agent, from scratch.

write: after a session, an LLM turns the transcript into operations on the
       user's memories - add a new fact, update an old one, or nothing
read:  embed the question, return the user's top-k memories by cosine

Short-term memory is the context window (lessons 6-7). This is the layer that
survives the session.
"""
import json
import numpy as np
from lab.llm import chat_json

WRITE = """You keep long-term memory about one user of a trading assistant.
Read the new conversation. Keep only lasting facts about the user: preferences,
limits, setup, role. Skip small talk and one-off questions.
{mode}
Return JSON: {{"ops": [{{"op": "add", "text": "..."}}{update}]}}
Each text is one short sentence that makes sense alone."""
UPDATE = ("If a new fact replaces an existing memory, update that memory by id. "
          "Do not add a fact that is already stored.")
APPEND = "Add every lasting fact."


class Memory:
    def __init__(self, embedder, update=True, scoped=True):
        self.embed = lambda t: embedder.model.encode([t], normalize_embeddings=True)[0]
        self.embed_query = embedder.query
        self.update, self.scoped = update, scoped
        self.rows = []  # {"user", "text", "vec"}

    def of(self, user):
        return [(i, r) for i, r in enumerate(self.rows) if r["user"] == user or not self.scoped]

    def write(self, user, transcript):
        known = "\n".join(f"[{i}] {r['text']}" for i, r in self.of(user)) or "(none)"
        system = WRITE.format(mode=UPDATE if self.update else APPEND,
                              update=', {"op": "update", "id": 3, "text": "..."}' if self.update else "")
        ops = chat_json([{"role": "system", "content": system},
                         {"role": "user", "content":
                          (f"Existing memories:\n{known}\n\n" if self.update else "")
                          + f"New conversation:\n{transcript}"}])["ops"]
        mine = {i for i, _ in self.of(user)}
        for op in ops:
            row = {"user": user, "text": op["text"], "vec": self.embed(op["text"])}
            if op["op"] == "update" and op.get("id") in mine:  # never touch another user's row
                self.rows[op["id"]] = row
            else:
                self.rows.append(row)
        return ops

    def read(self, user, query, k=3):
        rows = [r for _, r in self.of(user)]
        if not rows:
            return []
        scores = np.stack([r["vec"] for r in rows]) @ self.embed_query(query)
        return [rows[i]["text"] for i in np.argsort(-scores)[:k]]

    def dump(self):
        return json.dumps([{"user": r["user"], "text": r["text"]} for r in self.rows], indent=1)
