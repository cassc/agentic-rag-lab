"""Lesson 11: long-term memory - what to keep between sessions, how to update
it, and how to keep one user's memory away from another user."""
import json
from pathlib import Path
from lab.embed import Embedder
from lab.judge import RUBRIC, judge, pmap
from lab.llm import complete
from lab.memory import Memory

USERS = json.loads((Path(__file__).parent / "users.json").read_text())
SYSTEM = """Answer the question about the user in one short sentence. Use only the
memory below. If the memory does not say, answer exactly: unknown."""
emb = Embedder()


def ask(memory_text, q):
    r = complete([{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": f"Memory:\n{memory_text or '(empty)'}\n\nQuestion: {q}"}],
                 temperature=0)
    return r.choices[0].message.content, r.usage.prompt_tokens


def build(**kw):
    """Feed all sessions to a Memory, in time order across users."""
    mem = Memory(emb, **kw)
    for i in range(3):
        for user, u in USERS.items():
            if i < len(u["sessions"]):
                mem.write(user, u["sessions"][i])
    return mem


def strategies():
    yield "no memory", lambda user, q: ""
    yield "full history in the prompt", lambda user, q: "\n\n".join(
        f"Session {i + 1}:\n{s}" for i, s in enumerate(USERS[user]["sessions"]))
    for name, kw in (("facts, append only", dict(update=False)),
                     ("facts, with update", dict(update=True)),
                     ("facts, update, NO user scope", dict(update=True, scoped=False))):
        mem = build(**kw)
        yield f"{name} ({len(mem.rows)} rows)", lambda user, q, mem=mem: "\n".join(
            f"- {t}" for t in mem.read(user, q))
        if "NO" in name or "append" in name:
            saved[name] = mem


saved = {}
tasks = [(user, row) for user, u in USERS.items() for row in u["questions"]]
print(f"{len(tasks)} questions over {len(USERS)} users, "
      f"{sum(len(u['sessions']) for u in USERS.values())} sessions\n")
for name, recall in strategies():
    res = pmap(lambda t: ask(recall(t[0], t[1]["q"]), t[1]["q"]), tasks)
    good = [("unknown" in a.lower()) if row.get("unknown") else judge(row, a, RUBRIC)
            for (_, row), (a, _) in zip(tasks, res)]
    print(f"{name:40} correct {sum(good)}/{len(tasks)}   prompt tokens/q {sum(t for _, t in res) / len(res):.0f}")
    for (user, row), (a, _), ok in zip(tasks, res, good):
        if not ok and name != "no memory":
            print(f"    BAD {user}: {row['q']} -> {a[:90]}   (want: {row['answer']})")

print("\nappend-only memory about alice's currency:",
      saved["facts, append only"].read("alice", "Which currency should prices be shown in?"))
print("unscoped memory, what dave's question retrieves:",
      saved["facts, update, NO user scope"].read("dave", "Which currency should prices be shown in?"))
