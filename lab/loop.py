"""The lesson 6 agent loop as one function, so later lessons can reuse it.
tools: {name: (function, schema)}, the same shape as lab.tools.TOOLS."""
import contextvars
import json
from concurrent.futures import ThreadPoolExecutor
from lab.llm import complete


def call(tools, name, args):
    if name not in tools:
        return f"ERROR: unknown tool {name}"
    try:
        return str(tools[name][0](**args))
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def run(system, question, tools, max_steps=6, parallel=True, llm=complete):
    """Returns answer, steps, tokens, peak (largest prompt sent), trace."""
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    out = {"answer": "Stopped: step limit reached.", "steps": 0, "tokens": 0, "peak": 0, "trace": []}
    for _ in range(max_steps):
        r = llm(msgs, tools=[spec for _, spec in tools.values()], temperature=0)
        m = r.choices[0].message
        out["steps"] += 1
        out["tokens"] += r.usage.total_tokens
        out["peak"] = max(out["peak"], r.usage.prompt_tokens)
        if not m.tool_calls:
            out["answer"] = m.content
            break
        msgs.append({"role": "assistant", "content": m.content or "",
                     "tool_calls": [tc.model_dump() for tc in m.tool_calls]})
        todo = [(tc, json.loads(tc.function.arguments)) for tc in m.tool_calls]
        # Threads do not inherit context variables (the current trace span, lesson 14),
        # so each tool call gets its own copy.
        ctxs = [contextvars.copy_context() for _ in todo]
        with ThreadPoolExecutor(len(todo) if parallel else 1) as ex:  # several tools in one turn
            results = list(ex.map(lambda c, cx: cx.run(call, tools, c[0].function.name, c[1]),
                                  todo, ctxs))
        for (tc, args), res in zip(todo, results):
            out["trace"].append((tc.function.name, args))
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": res[:6000]})
    return out
