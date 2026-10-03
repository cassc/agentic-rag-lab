"""Lesson 13: an event-driven agent runtime - queue + workers, backpressure,
at-least-once delivery, dead letters, event sourcing and a read model (CQRS).
No LLM here: a "run" is a sleep, so the numbers are about the runtime only."""
import sys
import threading
import time
from collections import Counter
from lab.bus import Conflict, EventStore, Queue

only = sys.argv[1] if len(sys.argv) > 1 else "ABCDE"


def work(q, handle, n_workers, stop_when):
    """Run n worker threads until stop_when() is true."""
    def loop():
        while not stop_when():
            job = q.receive()
            if job is None:
                time.sleep(0.005)
            else:
                handle(*job)
    threads = [threading.Thread(target=loop) for _ in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


# A. More workers help until something else is the limit.
if "A" in only:
    print("\n## A. workers and the provider limit (40 runs, 0.1 s of 'LLM' each)")
    for n, limit in ((1, 99), (4, 99), (16, 99), (16, 4)):
        q, llm = Queue(visibility=5), threading.Semaphore(limit)  # limit = provider concurrency
        for i in range(40):
            q.send({"run": i})

        def handle(job_id, body, attempt, waited):
            with llm:
                time.sleep(0.1)
            q.ack(job_id)

        t = time.time()
        work(q, handle, n, lambda: q.count("done") == 40)
        print(f"   workers={n:2} provider limit={limit:2}: {time.time() - t:.2f}s")

# B. Producers faster than consumers: the queue grows, or you refuse work.
if "B" in only:
    print("\n## B. backpressure (100 runs/s arrive for 2 s; 4 workers finish 40 runs/s)")
    for max_depth in (None, 20):
        q, waits, refused = Queue(visibility=5), [], 0

        def handle(job_id, body, attempt, waited):
            waits.append(waited)
            time.sleep(0.1)
            q.ack(job_id)

        done = threading.Event()
        pool = threading.Thread(target=work, args=(q, handle, 4, done.is_set))
        pool.start()
        for i in range(200):
            if max_depth and q.count("ready") >= max_depth:  # jobs not finished yet
                refused += 1  # the API would answer 429 "try later"
            else:
                q.send({"run": i})
            time.sleep(0.01)
        depth = q.count("ready")
        while q.count("done") < 200 - refused:
            time.sleep(0.05)
        done.set()
        pool.join()
        waits.sort()
        print(f"   max depth={max_depth}: accepted {200 - refused}, refused {refused}, "
              f"backlog when arrivals stop {depth}, wait p50 {waits[len(waits) // 2]:.2f}s "
              f"p95 {waits[int(len(waits) * .95)]:.2f}s")

# C. A worker dies after the side effect, before the ack. The job comes back.
if "C" in only:
    print("\n## C. at-least-once delivery (50 jobs; the worker 'dies' on every 5th, once)")
    for idempotent in (False, True):
        q, charged, seen, lock = Queue(visibility=0.2), Counter(), set(), threading.Lock()
        for i in range(50):
            q.send({"order": i}, key=f"order-{i}")

        def handle(job_id, body, attempt, waited):
            with lock:
                if not (idempotent and job_id in seen):  # the consumer's own dedupe
                    charged[body["order"]] += 1  # the side effect
                    seen.add(job_id)
            if body["order"] % 5 == 0 and attempt == 1:
                return  # crash: no ack
            q.ack(job_id)

        work(q, handle, 4, lambda: q.count("done") == 50)
        print(f"   idempotent consumer={idempotent}: side effects {sum(charged.values())} for 50 jobs")
    q = Queue()
    ids = {q.send({"order": 1}, key="order-1") for _ in range(3)}
    print(f"   producer retried send 3 times with the same key: {q.count('ready')} job, ids {ids}")

# D. A job that always fails must not block the queue or loop forever.
if "D" in only:
    print("\n## D. poison message and the dead-letter queue")
    q, tries = Queue(visibility=0.05, max_attempts=3), Counter()
    for i in range(10):
        q.send({"run": i})

    def handle(job_id, body, attempt, waited):
        tries[body["run"]] += 1
        if body["run"] == 3:
            return  # always fails
        q.ack(job_id)

    work(q, handle, 2, lambda: q.count("done") + q.count("dead") == 10)
    print(f"   done {q.count('done')}, dead {q.count('dead')}, attempts on the poison job {tries[3]}")


# E. Event sourcing: the log is the truth, state is a fold over it.
def apply(state, e):
    """One event -> next state of a run. Pure function."""
    if e["type"] == "RunStarted":
        return {"status": "running", "steps": 0, "tokens": 0, "tenant": e["tenant"]}
    if e["type"] == "StepDone":
        return {**state, "steps": state["steps"] + 1, "tokens": state["tokens"] + e["tokens"]}
    if e["type"] == "ApprovalNeeded":
        return {**state, "status": "waiting for human"}
    if e["type"] == "Approved":
        return {**state, "status": "running"}
    if e["type"] == "RunFinished":
        return {**state, "status": "done"}
    return state


def fold(events):
    state = {}
    for e in events:
        state = apply(state, e)
    return state


if "E" in only:
    print("\n## E. event sourcing and a read model (CQRS)")
    es, v = EventStore(), {}
    script = [("run-1", "RunStarted", {"tenant": "acme"}), ("run-2", "RunStarted", {"tenant": "beta"}),
              ("run-1", "StepDone", {"tokens": 900}), ("run-1", "ApprovalNeeded", {"tool": "place_order"}),
              ("run-2", "StepDone", {"tokens": 400}), ("run-2", "RunFinished", {}),
              ("run-1", "Approved", {"by": "alice"}), ("run-1", "StepDone", {"tokens": 700}),
              ("run-1", "RunFinished", {})]
    for stream, type, data in script:  # the write side: only appends
        v[stream] = es.append(stream, type, data, v.get(stream, 0))
    print("   run-1 now:        ", fold(es.read("run-1")))
    print("   run-1 as of seq 4:", fold(es.read("run-1", upto=4)))
    usage = Counter()  # the read side: a different shape, built from the same events
    for e in es.read():
        if e["type"] == "RunStarted":
            v[e["stream"] + ":tenant"] = e["tenant"]
        if e["type"] == "StepDone":
            usage[v[e["stream"] + ":tenant"]] += e["tokens"]
    print("   read model, tokens per tenant:", dict(usage))
    try:
        es.append("run-1", "StepDone", {"tokens": 1}, expected=3)  # a stale worker
    except Conflict as e:
        print(f"   stale writer: Conflict: {e}")
