"""Lesson 9, part 2: the same research workflow on Temporal.

A worker process is killed in the middle of an activity. A second worker
finishes the run. The history shows what ran once and what ran twice.

Needs a Temporal server:
  TEMPORAL_ADDRESS=localhost:7233 uv run lessons/09_durable/temporal_run.py
  uv run lessons/09_durable/temporal_run.py --dev-server   # SDK downloads the dev server binary
"""
import asyncio
import os
import subprocess
import sys
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

QUEUE = "lab"


# ---- activities: all I/O lives here, like fn in ctx.step(name, fn) ----------
@activity.defn
def price(symbol: str) -> str:
    if activity.info().attempt < 3:  # a flaky API: fails twice
        raise TimeoutError("exchange API timed out")
    return f"{symbol} 65000"


@activity.defn
def plan(question: str) -> list[str]:
    from lab.llm import chat_json
    return chat_json([{"role": "user", "content":
                       f"Question: {question}\nWrite 2 short search queries for API docs. "
                       'Return JSON: {"queries": ["...", "..."]}'}])["queries"][:2]


@activity.defn
def search(query: str) -> str:
    from lab.tools import search_docs
    out = search_docs(query, k=3)
    if os.getenv("DIE_IN_SEARCH"):
        os._exit(1)  # the work is done, the result never reaches the server
    return out


@activity.defn
def answer(question: str, found: list[str]) -> str:
    from lab.llm import chat
    return chat([{"role": "user", "content": "Answer in two sentences, from the sources only.\n\n"
                  + "\n\n".join(found) + f"\n\nQuestion: {question}"}], temperature=0)


# ---- workflow: only orchestration, must be deterministic --------------------
@workflow.defn
class Research:
    @workflow.run
    async def run(self, question: str) -> str:
        opts = dict(start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(initial_interval=timedelta(seconds=0.2),
                                             maximum_attempts=3))
        await workflow.execute_activity(price, "BTCUSDT", **opts)
        queries = await workflow.execute_activity(plan, question, **opts)
        found = [await workflow.execute_activity(search, q, **opts) for q in queries]
        return await workflow.execute_activity(answer, args=[question, found], **opts)


async def worker(addr):
    client = await Client.connect(addr)
    with ThreadPoolExecutor(4) as pool:
        # Unsandboxed only because the workflow lives in this script (__main__).
        # In a real service keep workflows in their own module and keep the sandbox.
        await Worker(client, task_queue=QUEUE, workflows=[Research],
                     activities=[price, plan, search, answer], activity_executor=pool,
                     workflow_runner=UnsandboxedWorkflowRunner()).run()


def spawn(addr, die=False):
    env = {**os.environ, **({"DIE_IN_SEARCH": "1"} if die else {})}
    return subprocess.Popen([sys.executable, __file__, "worker", addr], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def main():
    from lab.evals import load_golden
    env = None
    if os.getenv("TEMPORAL_ADDRESS"):
        client = await Client.connect(os.environ["TEMPORAL_ADDRESS"])
    elif "--dev-server" in sys.argv:
        from temporalio.testing import WorkflowEnvironment
        env = await WorkflowEnvironment.start_local()
        client = env.client
    else:
        sys.exit(__doc__)
    addr = client.service_client.config.target_host
    q = load_golden(multi_hop=True)[0]["q"]

    w1 = spawn(addr, die=True)
    h = await client.start_workflow(Research.run, q, id=f"research-{uuid.uuid4().hex[:8]}",
                                    task_queue=QUEUE)
    await asyncio.to_thread(w1.wait)
    print(f"worker 1 died inside 'search' (exit code {w1.returncode}). Starting worker 2.")
    w2 = spawn(addr)
    try:
        print(f"A: {(await h.result())[:200]}")
    finally:
        w2.kill()

    types, started, last = Counter(), Counter(), {}
    async for e in h.fetch_history_events():
        types[e.event_type] += 1
        if e.HasField("activity_task_scheduled_event_attributes"):
            last[e.event_id] = e.activity_task_scheduled_event_attributes.activity_type.name
        if e.HasField("activity_task_started_event_attributes"):
            a = e.activity_task_started_event_attributes
            started[last[a.scheduled_event_id]] += a.attempt
    print(f"history: {sum(types.values())} events")
    print("attempts per activity type (from history):", dict(started))
    if env:
        await env.shutdown()


if __name__ == "__main__":
    asyncio.run(worker(sys.argv[2]) if sys.argv[1:2] == ["worker"] else main())
