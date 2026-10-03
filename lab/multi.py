"""Multi-agent, the simplest useful shape: a supervisor that calls worker
agents as tools. Each worker is its own loop with its own tools and a fresh
context. The supervisor sees only the worker's final answer."""
from lab import loop
from lab.tools import TOOLS, spec

SUPERVISOR = """You lead a small team for Binance Spot API questions. You have no
tools of your own. Delegate to the workers, then write the final answer from
what they report. Ask independent workers in the same turn. Keep doc source ids
like (filters#12) in the answer. If the workers could not find it, say
"Not in the sources." """

WORKERS = {  # name: (system prompt, tools, description for the supervisor)
    "docs_agent": ("You answer questions about the Binance Spot API docs. Use search_docs. "
                   "Cite sources by id, e.g. (filters#12). Never guess. If the docs don't "
                   'cover it, say "Not in the sources."', ["search_docs"],
                   "Finds rules, definitions and error codes in the API docs."),
    "market_agent": ("You report live Binance market data with your tools. Give the exact "
                     "values the task asks for. Report tool errors as they are.",
                     ["get_price", "get_symbol_filters"],
                     "Gets live prices and live trading filters for a symbol."),
}
BRIEF = {"full": "A complete task for the worker: every detail, number and symbol it needs. "
                 "The worker sees nothing but this text.",
         "short": "The task in at most 4 words."}


class Team:
    def __init__(self, brief="full", worker_steps=4, parallel=True):
        self.brief, self.worker_steps, self.parallel = brief, worker_steps, parallel
        self.handoffs = []  # (worker, task, result)

    def worker(self, name):
        system, tools, desc = WORKERS[name]

        def ask(task):
            r = loop.run(system, task, {n: TOOLS[n] for n in tools}, self.worker_steps)
            self.handoffs.append((name, task, r))
            return r["answer"]

        ask.__name__ = name
        return ask, spec(ask, desc, task=("string", BRIEF[self.brief]))

    def run(self, question, max_steps=6):
        r = loop.run(SUPERVISOR, question, {n: self.worker(n) for n in WORKERS},
                     max_steps, self.parallel)
        r["llm_calls"] = r["steps"] + sum(h[2]["steps"] for h in self.handoffs)
        r["total_tokens"] = r["tokens"] + sum(h[2]["tokens"] for h in self.handoffs)
        r["handoffs"] = self.handoffs
        return r
