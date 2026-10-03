# Design: an agent runtime for hundreds of agents

A design document in the style I would bring to a review. Each part points
to the lesson where the idea is built and measured. Cloud parts (AWS, EKS,
Terraform) are design only - they are not run in this repo.

## 1. Goals and non-goals

**Goals**

- Run multi-step agent workflows that survive process and node failure.
- Hundreds of agent types, thousands of runs at once, many tenants.
- p95 time to first token under 2 s for chat; batch runs can wait.
- Every run can be traced, replayed, and costed per tenant.
- Agent teams ship agents without owning infrastructure.

**Non-goals:** training models, a general workflow product, a UI.

## 2. Architecture

```
client
  |  HTTPS, JWT
API gateway ---- IAM (tenant, roles)
  |
Runs API (stateless)  ---->  Workflow engine (Temporal)  <---- workers (stateless)
  |   202 + run id            history = source of truth           |      |
  |                                                               |      |
  '--> read models (run status, cost)                    LLM gateway   MCP gateway
       events -> bus -> analytics, audit                      |             |
                                                         providers     tool servers
state: session (history) | memory store (per tenant) | blob store (big payloads)
telemetry: OpenTelemetry traces + metrics from every box
```

| Box | Job | Lesson |
| --- | --- | --- |
| Runs API | accept, validate, idempotency, admission control | 17 |
| Workflow engine | durable steps, retries, timers, human approval | 9 |
| Workers | run agent code; hold no state | 6, 7, 16 |
| LLM gateway | routing, failover, quotas, cost | 10 |
| MCP gateway + registry | tools as services, permissions, audit | 15 |
| Memory | long-term facts per tenant and user | 11 |
| Event bus + read models | status, cost, audit, analytics | 13 |
| Telemetry | traces, metrics, online evals | 14, 8 |

## 3. Key decisions (ADR style)

**D1. Durable execution engine (Temporal) over checkpoints in a database.**
Chosen because agent runs are long, wait for humans, and have side effects.
Cost: deterministic workflow code, payload limits, one more system to run.
Rejected: hand-made checkpoints (lesson 7) - fine for one service, but
every team would rebuild retries, timers and versioning. Step Functions -
good on AWS, weaker for long dynamic loops and local tests.

**D2. The agent loop is the workflow; LLM and tool calls are activities.**
Gives replay and exactly one recorded answer per model call. Cost: one
activity per step adds ~10s of ms and history events; very long runs need
continue-as-new. Rejected: one big activity per run (no resume inside).

**D3. Our own thin runtime interface over frameworks.**
`run(input) -> result + events`. LangGraph or our loop sits behind it
(lesson 16). Cost: an adapter to maintain. Gain: a framework change is not
a rewrite, and tracing, budgets and policy live in one place.

**D4. One LLM gateway and one MCP gateway, as shared services.**
Keys, quotas, failover, permissions and audit in two places, not in every
agent. Cost: a hop (~ms) and a shared failure point - so both are
stateless, replicated, and agents fail closed for tools and can fall back
to a direct provider call for models.

**D5. At-least-once everywhere, idempotency keys on every side effect.**
Exactly-once across systems does not exist (lessons 9C, 13C). The workflow
makes the key; the tool server remembers it.

**D6. Tenant isolation by data partition and limits, not by cluster.**
Tenant id comes from the token, never from the request body. Every store
is keyed by tenant; quotas at admission; fair queues. Cost: noisy-tenant
risk is handled by limits, not removed. A tenant with strict rules can get
its own namespace and task queue.

**D7. Backpressure at the edge.** Bounded backlog per tenant, 429 with
Retry-After (lessons 13B, 17B). Batch work uses a separate low-priority
queue.

## 4. API contract (v1)

```
POST   /v1/runs            {agent, input, session_id?}   Idempotency-Key header
       202 {run_id, status}  |  429 {retry_after}  |  400  |  401/403
GET    /v1/runs/{id}       {status, output?, usage{tokens, cost}, error?}
GET    /v1/runs/{id}/events   SSE: run.started, step.completed, tool.called,
                              approval.needed, token.delta, run.finished
POST   /v1/runs/{id}/approve  {decision}        -> signal to the workflow
DELETE /v1/runs/{id}                             -> cancel
```

Events have a type, a sequence number per run, and a schema version. New
fields are added, never changed: clients must ignore what they don't know.

## 5. State

| State | Store | AWS |
| --- | --- | --- |
| Run history (truth) | Temporal | Temporal Cloud, or self-hosted on EKS + Aurora |
| Run status read model, idempotency keys | key-value | DynamoDB (TTL on keys) |
| Session cache, rate-limit counters | in-memory store | ElastiCache (Redis) |
| Long-term memory | database + vector index | Aurora Postgres + pgvector, or OpenSearch |
| Large payloads (tool outputs, documents) | blob store | S3; history keeps the key only |
| Events for analytics and audit | bus | SQS/SNS for fan-out, Kinesis or MSK when order and replay matter |

## 6. Compute and scaling

- **EKS.** One Deployment for the API, one per worker pool (task queue).
  Pods are stateless; a rolling deploy never loses a run.
- **Autoscaling on work, not CPU.** Agent workers wait on I/O. Scale with
  KEDA on task-queue backlog and schedule-to-start latency. Cap replicas by
  the provider quota (lesson 13A: workers beyond the quota add nothing).
- **Pools.** Interactive and batch runs on separate task queues, so batch
  cannot slow chat. Risky tools (code execution) in a sandboxed pool with
  no network.
- **Models.** Bedrock for managed models (through the LLM gateway, with a
  second provider as fallback). SageMaker endpoints only for models we host
  ourselves (embeddings, rerankers).
- **Lambda** for small event handlers (webhooks, memory writes after a
  session). Not for agent runs: 15-minute limit, cold starts.

Sketch of the scaling rule (not run here):

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
spec:
  scaleTargetRef: {name: agent-worker}
  minReplicaCount: 2
  maxReplicaCount: 60          # capped by the provider quota, not by the cluster
  triggers:
    - type: temporal
      metadata: {taskQueue: interactive, targetQueueSize: "5"}
```

## 7. Delivery

- **IaC:** Terraform for cloud resources (VPC, EKS, Aurora, DynamoDB, IAM
  roles per service account). One module per service, one state per
  environment.
- **CI (GitHub Actions):** tests -> contract tests (lesson 16) -> eval
  gate against the baseline (lesson 8) -> image build -> push.
- **CD (ArgoCD):** Git is the desired state. Canary rollout by traffic
  share, with automatic rollback on SLO burn.
- **Prompts, tool schemas and model versions are releases too.** They go
  through the same eval gate.
- **Workflow changes** follow the versioning rule (lesson 9D): old runs
  finish on old code.

## 8. Failure modes

| Failure | What happens | Lesson |
| --- | --- | --- |
| Worker dies mid-run | another worker replays the history and continues | 9 |
| Provider outage | gateway falls back; breaker stops the timeouts | 10 |
| Provider rate limit | queue grows, autoscaler is capped, 429 at the edge | 13, 17 |
| Tool server down | retries for read-only tools, breaker, agent gets a clear error | 15 |
| Poison run | max attempts, then dead letter + alert | 13 |
| Agent loops | step, token and time budget for the whole agent tree | 7, 12 |
| Prompt injection | permissions in code, approval for risky tools | 7, 15 |
| Bad deploy | canary + eval gate + rollback | 8 |
| Stale or leaked memory | update on write, tenant scope in the store | 11 |

## 9. SLOs and what we watch

- Run success rate >= 99% (excluding user errors).
- Chat: time to first token p95 < 2 s; full answer p95 < 15 s.
- Schedule-to-start (queue wait) p95 < 1 s for interactive runs.
- Cost per run and per tenant, with alerts on budget.
- Quality: online eval score on sampled traces; pass^k on the golden set.

## 10. Rollout plan

1. One agent, one tenant, behind the interface, with traces and evals.
2. Add the gateways; move keys and tool permissions out of the agent.
3. Add tenants: quotas, fair queues, per-tenant dashboards.
4. Open to other teams: registry, templates, docs, a paved path.

## 11. Open questions

- Self-hosted Temporal or Temporal Cloud (ops load vs data location rules).
- How much of the event stream is a public contract.
- Memory: who may read what an agent learned about a user (privacy review).
