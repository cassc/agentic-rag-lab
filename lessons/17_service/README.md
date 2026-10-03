# Lesson 17 - The runtime as a service: API contract, load, tenants

## The idea

Lessons 9-16 built the parts. This lesson puts an HTTP API in front and
asks what happens when many clients use it at once.

The contract follows from one fact: **a run is slow, a request must be
fast.** So the API never waits for a run.

| Call | Answer | Why |
| --- | --- | --- |
| `POST /runs` `{question, tenant}` | `202` + `run_id`, at once | the run goes to the queue (lesson 13) |
| `POST` with `Idempotency-Key` header | the **first** run again | clients retry on timeouts; a retry must not start a second run |
| `GET /runs/{id}` | status, answer, events so far | polling |
| `GET /runs/{id}/events` | live event stream (SSE) | progress while the run works |
| any `POST` when full | `429` + `Retry-After` | backpressure reaches the client |
| `GET /healthz` | ok + backlog | for the load balancer and autoscaler |

`lab/service.py` (~110 lines): FastAPI + the lesson 13 queue and event
store + worker threads. The design document that goes with it:
[docs/design/agent-runtime.md](../../docs/design/agent-runtime.md)
(architecture, decisions with trade-offs, AWS / Kubernetes mapping).

## Run it

```sh
uv run lessons/17_service/run.py          # A-E. Load tests run in-process: no port is opened
uv run lessons/17_service/run.py serve    # a real server on 127.0.0.1:8770 (loopback only)
curl -s -X POST 127.0.0.1:8770/runs -H 'content-type: application/json' \
     -d '{"question": "What does error -1021 mean?", "tenant": "acme"}'
curl -N 127.0.0.1:8770/runs/<run_id>/events
```

In A-D a "run" is a 0.2 s sleep, 8 workers, one Python process. The numbers
show the runtime's behaviour, not a production capacity.

## Results

**A. The API stays fast while runs are slow.** 100 runs sent at once:
`POST` p95 93 ms; runs finished p50 1.39 s, p95 2.37 s. (8 workers x 5
runs/s = 40 runs/s, so the last of 100 waits ~2.5 s. The queue is doing
its job.)

**B. Overload.** 300 runs at once:

| Policy | Accepted | Refused | Run done p50 | p95 |
| --- | --- | --- | --- | --- |
| accept all | 300 | 0 | 3.74 s | 7.05 s |
| at most 40 unfinished runs | 40 | 260 | 0.62 s | 1.02 s |

The same trade as lesson 13B, now seen from the client. The limit should
come from the latency you promise: "p95 under 1 s" at 40 runs/s means a
backlog of about 40.

**C. Idempotent POST.** The client sends the same request 5 times:

| Header | Run ids | Agent executions |
| --- | --- | --- |
| none | 5 | 5 |
| `Idempotency-Key: order-42` | 1 | 1 |

The key is scoped per tenant, so two tenants cannot collide.

**D. Noisy tenant.** "big" sends 120 runs, then "small" sends 5:

| Tenant limit | big: accepted / refused | small: run done p50 |
| --- | --- | --- |
| none | 120 / 0 | **3.13 s** (behind all of big's runs) |
| 16 unfinished runs per tenant | 16 / 104 | 0.56 s |

One shared FIFO queue lets one tenant take the whole runtime. A per-tenant
limit fixes it with 5 lines. Better (not built here): a queue per tenant
and a worker that takes from them in turn (fair queueing), so "big" is
slowed down, not refused.

**E. A real run through the API**, with events as they happen:

```
POST /runs -> 202 {'run_id': 'e6fb6b8d5bb5', 'status': 'queued', 'answer': None}
+  0.0s  RunQueued
+  0.1s  RunStarted
+  1.7s  ToolCalled   {'tool': 'get_symbol_filters', 'args': {'symbol': 'BTCUSDT'}}
+ 12.7s  Usage        {'steps': 2, 'tokens': 1566}
+ 12.7s  RunFinished  {'status': 'done'}
```

11 seconds pass between the tool call and the end. That is the second LLM
call. For a chat UI you would also stream the model's tokens as events
(lesson 10E), so the user sees text and not a spinner.

## What is missing here (on purpose)

| Missing | Where it comes from |
| --- | --- |
| Runs survive a restart | Temporal (lesson 9) or a durable queue + database |
| Auth: who is the tenant | the gateway / IAM in front (JWT, mTLS). Never trust `tenant` from the body |
| Model failover, quotas | LLM gateway (lesson 10) |
| Traces across API -> queue -> worker | pass `traceparent` in the job (lesson 14) |
| More than one process | stateless API pods + a shared queue and store |
| Fair scheduling, priorities | per-tenant queues |
| Cancel a run | `DELETE /runs/{id}` -> a cancel signal to the workflow |

## Review questions

**Q: Design the API for a long-running agent.**
> `POST /runs` returns 202 and a run id at once; the work goes to a queue.
> `GET /runs/{id}` for status, an SSE or WebSocket stream for progress,
> a webhook for server-to-server. Idempotency key on POST. 429 with
> Retry-After when full. Cancel endpoint. Version the API and the event
> schema.

**Q: Why an idempotency key, when the queue already dedupes?**
> The retry happens before the queue: the client's POST timed out and it
> does not know if the run started. The server must map (tenant, key) to
> the first run and return it. In my test 5 retries made 5 runs without
> the key and 1 with it.

**Q: How do you stop one tenant from starving the others?**
> Limits per tenant at admission (concurrent runs, tokens per minute), and
> fair scheduling in the queue (a queue per tenant, round robin or
> weighted). Without it, 5 runs of a small tenant waited 3.1 s behind 120
> of a big one; with a limit, 0.56 s.

**Q: How do you choose the queue limit?**
> From the latency promise: limit = target wait x service rate. Then
> measure. Without a limit, p95 grew to 7 s for 300 runs; with a limit of
> 40 it stayed at 1 s and the rest got a fast 429.

**Q: How do you scale this to hundreds of agents?**
> Stateless API and workers; state in the queue, the workflow engine and
> the database. Autoscale workers on queue depth and age, capped by the
> provider quota. Partition by tenant. One LLM gateway for quotas and
> failover. Trace everything. Details: the design document.

**Q: What do you load test in an agent runtime?**
> With a fake model first: API latency, queue wait, overload behaviour,
> fairness, restart in the middle. That finds runtime bugs cheaply. Then a
> smaller test with the real model for provider limits and cost.
