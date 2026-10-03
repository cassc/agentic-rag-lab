"""One small interface over agent runtimes. Callers depend on Runtime and
Result, not on a framework. Two adapters: our own loop, and LangGraph.

Both use the same model client and the same tools, so a difference in the
numbers comes from the runtime, not from the model.
"""
import json
import operator
from dataclasses import dataclass, field
from typing import Annotated, Protocol, TypedDict
from lab import loop
from lab.llm import complete


@dataclass
class Result:
    answer: str
    steps: int
    tokens: int
    trace: list = field(default_factory=list)  # (tool name, args)


class Runtime(Protocol):
    def run(self, question: str) -> Result: ...


class Scratch:
    def __init__(self, system, tools, max_steps=6):
        self.system, self.tools, self.max_steps = system, tools, max_steps

    def run(self, question):
        r = loop.run(self.system, question, self.tools, self.max_steps)
        return Result(r["answer"], r["steps"], r["tokens"], r["trace"])


class State(TypedDict):  # LangGraph merges each node's return into this with the reducers
    msgs: Annotated[list, operator.add]
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]


class LangGraph:
    def __init__(self, system, tools, max_steps=6, approve=()):
        """approve: tool names that pause the graph for a human before they run."""
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.graph import END, START, StateGraph
        self.system, self.tools, self.max_steps, self.END = system, tools, max_steps, END
        g = StateGraph(State)
        g.add_node("model", self.model)
        g.add_node("tools", self.call_tools)
        g.add_node("approval", lambda state: {})  # does nothing: a place to pause
        g.add_edge(START, "model")
        g.add_conditional_edges("model", lambda s: self.route(s, approve), ["tools", "approval", END])
        g.add_edge("approval", "tools")
        g.add_edge("tools", "model")
        self.app = g.compile(checkpointer=InMemorySaver(), interrupt_before=["approval"])

    def model(self, state):
        if state["steps"] >= self.max_steps:
            return {"msgs": [{"role": "assistant", "content": "Stopped: step limit reached."}]}
        r = complete(state["msgs"], tools=[s for _, s in self.tools.values()], temperature=0)
        m = r.choices[0].message
        msg = {"role": "assistant", "content": m.content or ""}
        if m.tool_calls:
            msg["tool_calls"] = [tc.model_dump() for tc in m.tool_calls]
        return {"msgs": [msg], "steps": 1, "tokens": r.usage.total_tokens}

    def route(self, state, approve):
        calls = state["msgs"][-1].get("tool_calls")
        if not calls:
            return self.END
        return "approval" if any(c["function"]["name"] in approve for c in calls) else "tools"

    def call_tools(self, state):
        return {"msgs": [{"role": "tool", "tool_call_id": c["id"],
                          "content": loop.call(self.tools, c["function"]["name"],
                                               json.loads(c["function"]["arguments"]))[:6000]}
                         for c in state["msgs"][-1]["tool_calls"]]}

    def result(self, state):
        trace = [(c["function"]["name"], json.loads(c["function"]["arguments"]))
                 for m in state["msgs"] for c in m.get("tool_calls", [])]
        return Result(state["msgs"][-1]["content"], state["steps"], state["tokens"], trace)

    def run(self, question, thread="default"):
        start = {"msgs": [{"role": "system", "content": self.system},
                          {"role": "user", "content": question}], "steps": 0, "tokens": 0}
        return self.result(self.app.invoke(start, {"configurable": {"thread_id": thread}}))

    def resume(self, thread):
        """Continue a paused thread (after approval) from its checkpoint."""
        return self.result(self.app.invoke(None, {"configurable": {"thread_id": thread}}))
