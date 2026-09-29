"""A small agent harness: the lesson 6 loop plus the runtime pieces around it.

- checkpoint: state saved after every step; a new Agent with the same session
  id resumes where the old one stopped (crash recovery, replay for debugging)
- hooks: pre_tool can deny a call (permissions, human approval, limits);
  post_tool can rewrite output (truncate, flag prompt injection)
- compaction: when the context gets big, old tool outputs are cleared
- budget: max steps and max total tokens
"""
import json
from pathlib import Path
from lab.llm import chat, complete
from lab.tools import TOOLS, run_tool

SESSIONS = Path(__file__).resolve().parent.parent / "data" / "sessions"


class Crash(Exception):
    """Raised on purpose to simulate the process dying mid-run."""


def size(msgs):
    return sum(len(json.dumps(m)) for m in msgs) // 4  # rough tokens: ~4 chars each


class Agent:
    def __init__(self, session, system, tools, max_steps=8, max_tokens=80_000,
                 pre_tool=(), post_tool=(), compact_at=None, compact_mode="clear",
                 crash_at_step=None, temperature=0):
        self.path = SESSIONS / f"{session}.json"
        self.system, self.tools = system, tools
        self.max_steps, self.max_tokens = max_steps, max_tokens
        self.pre_tool, self.post_tool = pre_tool, post_tool
        self.compact_at, self.crash_at_step = compact_at, crash_at_step
        self.compact_mode, self.temperature = compact_mode, temperature
        self.log = []  # (event, detail) for the lesson to print

    def load(self, question):
        if self.path.exists():
            s = json.loads(self.path.read_text())
            self.log.append(("resume", f"step {s['step']}, {len(s['msgs'])} messages"))
            return s
        return {"msgs": [{"role": "system", "content": self.system},
                         {"role": "user", "content": question}],
                "step": 0, "tokens": 0, "cached": 0, "done": None}

    def save(self, s):
        SESSIONS.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(s))
        tmp.replace(self.path)  # atomic: a crash mid-write never leaves half a file

    def compact(self, s):
        """Clear old tool outputs, keep the last 2.
        mode "clear": just drop them. Cheap, but the agent forgets what it found.
        mode "notes": first ask the LLM to write the useful facts into one notes
        message (kept at the end), then drop them.
        Either way it edits early messages, so the provider's prompt cache for
        everything after the first edit is lost."""
        old = [m for m in s["msgs"] if m["role"] == "tool"][:-2]
        old = [m for m in old if not m["content"].startswith("[cleared")]
        if not old:
            return
        before = size(s["msgs"])
        if self.compact_mode == "notes":
            prev = next((m["content"] for m in s["msgs"] if m.get("name") == "notes"), "")
            notes = chat([{"role": "user", "content":
                           f"Task: {s['msgs'][1]['content']}\n\nExisting notes:\n{prev}\n\n"
                           "New tool results:\n" + "\n---\n".join(m["content"] for m in old) +
                           "\n\nUpdate the notes: every fact useful for the task, with source "
                           "ids, and which searches are already done. Be brief."}], temperature=0)
            s["msgs"] = [m for m in s["msgs"] if m.get("name") != "notes"]
            s["msgs"].append({"role": "user", "name": "notes",
                              "content": "Notes from earlier (cleared) tool results:\n" + notes})
        for m in old:
            m["content"] = "[cleared to save context; see notes, or call the tool again]"
        self.log.append(("compact", f"{self.compact_mode}: ~{before} -> ~{size(s['msgs'])} tokens"))

    def call_tool(self, name, args):
        for hook in self.pre_tool:
            deny = hook(name, args)
            if deny:
                self.log.append(("denied", f"{name} {args}: {deny}"))
                return f"DENIED by policy: {deny}"
        out = run_tool(name, args)
        for hook in self.post_tool:
            out = hook(name, out)
        return out

    def run(self, question):
        s = self.load(question)
        while s["done"] is None:
            if s["step"] >= self.max_steps or s["tokens"] >= self.max_tokens:
                s["done"] = f"Stopped: budget spent ({s['step']} steps, {s['tokens']} tokens)."
                break
            if self.compact_at and size(s["msgs"]) > self.compact_at:
                self.compact(s)
            r = complete(s["msgs"], tools=[TOOLS[n][1] for n in self.tools],
                         temperature=self.temperature)
            m = r.choices[0].message
            s["tokens"] += r.usage.total_tokens
            s["cached"] += getattr(r.usage, "prompt_cache_hit_tokens", 0) or 0  # DeepSeek field
            s["step"] += 1
            if not m.tool_calls:
                s["done"] = m.content
            else:
                s["msgs"].append({"role": "assistant", "content": m.content or "",
                                  "tool_calls": [tc.model_dump() for tc in m.tool_calls]})
                for tc in m.tool_calls:
                    args = json.loads(tc.function.arguments)
                    self.log.append(("tool", f"{tc.function.name} {args}"))
                    s["msgs"].append({"role": "tool", "tool_call_id": tc.id,
                                      "content": self.call_tool(tc.function.name, args)})
            self.save(s)  # checkpoint after every step
            if self.crash_at_step == s["step"]:
                raise Crash(f"simulated crash after step {s['step']}")
        self.save(s)
        return s
