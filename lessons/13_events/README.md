# Lesson 13 - Event-driven runtime: queues, backpressure, event sourcing

## The idea

An agent run takes 20 seconds to 20 minutes. An HTTP request that waits for
it will time out, and the server that holds it cannot be restarted. So split
**accepting** work from **doing** work:

```
API  -> queue ->  workers (stateless)  -> LLM / tools
 |                    |
 '--- status <--- event log (the truth) ---> read models
```

The API writes a job and answers at once ("202, here is your run id").
Workers pull jobs. Everything a run does is written as an event. This gives
you scaling (add workers), failure isolation (a dead worker loses nothing),
and a full history.

`lab/bus.py` (~80 lines, SQLite) has the two parts. It is a stand-in for the
real brokers, with the same rules:

| Here | SQS | Kafka | Redis Streams |
| --- | --- | --- | --- |
| `receive()` hides a job for `visibility` s | visibility timeout | consumer offset, not committed | pending entries list |
| `ack()` | DeleteMessage | commit offset | XACK |
| `max_attempts` -> state `dead` | redrive to a DLQ | your own DLQ topic | XCLAIM + your own DLQ |
| `send(key=...)` dedupe | FIFO dedupe id | idempotent producer | your own key check |
| `EventStore` stream + version | (use DynamoDB) | a topic, keyed by run id | a stream per run |

## Run it

```sh
uv run lessons/13_events/run.py      # A-E, no LLM calls, ~15 s
```

A "run" here is a 0.1 s sleep, so the numbers show the runtime, not the
model.

## Results

**A. Workers and the real limit** (40 runs):

| Workers | Provider concurrency limit | Time |
| --- | --- | --- |
| 1 | none | 4.02 s |
| 4 | none | 1.01 s |
| 16 | none | 0.31 s |
| 16 | 4 | **1.01 s** |

Workers are cheap: an agent run is almost all waiting on I/O. The limit is
the provider's rate limit (tokens per minute, concurrent requests). 16
workers behind a limit of 4 are as fast as 4. Scale workers on **queue
depth and age**, and cap them by the provider quota - not by CPU.

**B. Backpressure.** 100 runs/s arrive for 2 s; 4 workers finish 40 runs/s.

| Policy | Accepted | Refused | Backlog | Wait p50 | Wait p95 |
| --- | --- | --- | --- | --- | --- |
| accept all | 200 | 0 | 120 | 1.48 s | 2.78 s |
| refuse above 20 unfinished | 100 | 100 | 20 | 0.39 s | 0.40 s |

A queue does not add capacity. It only moves the wait. With no limit the
backlog and the wait grow for as long as the overload lasts, and every user
gets a slow answer. With a limit, half the callers get a fast "429, try
later" and the other half get a fast run. Which one is right is a product
decision; having **no** limit is not a decision.

**C. At-least-once delivery.** The worker "dies" after the side effect and
before the ack on 10 of 50 jobs:

| Consumer | Side effects for 50 jobs |
| --- | --- |
| plain | **60** |
| idempotent (remembers job ids it has done) | 50 |

Same lesson as 9C, one layer down. The other half is the producer: a client
that retries `send` three times with the same key made **1** job, not 3.

**D. Poison message.** One job fails every time. After 3 attempts it moved
to the dead-letter state; the other 9 finished. Without `max_attempts` it
would come back forever and burn tokens each time. Alert on the dead-letter
count: every row there is a bug or a bad input.

**E. Event sourcing + CQRS.**

- State is a fold over events: `run-1` -> `done, 2 steps, 1600 tokens`.
- Time travel: the same fold up to seq 4 -> `waiting for human, 1 step`.
  This is how you answer "what did the agent know when it did that?".
- A **read model** is another fold with another shape: tokens per tenant
  (`acme 1600, beta 400`). It can be dropped and rebuilt from the log.
  Writes go to the log, reads go to read models: that split is CQRS.
- Two workers on one run: the stale one got `Conflict: run-1 is past version
  3`. The version check on append (optimistic concurrency) is what stops two
  workers from both continuing a run.

## Ordering, and why it is per run

Global order across all runs is expensive and nobody needs it. Order matters
**inside** one run. So use the run id as the partition key (Kafka key, SQS
FIFO message group): events of one run stay in order, different runs go in
parallel.

## What I would do in production

- Outbox pattern: write the state change and the outgoing event in one
  database transaction, publish from the outbox. No "saved but not sent".
- Per-tenant queues or weighted fair pick, so one tenant's burst cannot
  starve the others.
- Priorities: interactive runs before batch runs.
- Snapshots for long streams, so a fold does not read 50k events.
- A workflow engine (lesson 9) already is an event-sourced runtime with a
  queue. Build your own bus only for what the engine does not cover:
  fan-out to other systems, analytics, audit.

## Review questions

**Q: Why run agents behind a queue and not inside the HTTP request?**
> Runs are long and fail in the middle. A queue lets the API answer at once,
> lets stateless workers scale and restart, keeps work when a worker dies,
> and gives one place to apply limits and priorities.

**Q: What does at-least-once delivery mean for agent workers?**
> A job can arrive twice (worker died before the ack). So the consumer must
> be idempotent: remember processed ids, or pass an idempotency key to the
> side effect. In my test a plain consumer made 60 side effects for 50
> jobs.

**Q: What is backpressure and how do you apply it?**
> A signal upstream that the system is full. Bound the queue, reject or
> delay new work (429 + Retry-After), limit per tenant. A queue with no
> bound turns overload into a long wait for everyone: p95 went from 0.4 s
> to 2.8 s in my test, and it keeps growing while the overload lasts.

**Q: What limits the throughput of an agent platform?**
> Usually the provider's rate limit, not your CPU. 16 workers behind a
> concurrency limit of 4 ran as fast as 4. Scale on queue depth and age, cap
> by quota, and spread the quota fairly over tenants.

**Q: What are event sourcing and CQRS, and why use them for agents?**
> Event sourcing stores every change as an event; state is computed from
> them. CQRS splits the write model (append events) from read models built
> for queries. For agents this gives an audit log, replay for debugging,
> resume after a crash, and cheap new views (cost per tenant) without
> touching the write path.

**Q: What is a dead-letter queue for?**
> A job that keeps failing is moved aside after N attempts so it cannot
> block or loop. You alert on it, inspect it, fix the cause, and replay it.
