"""The agent runtime as a service: FastAPI in front, the lesson 13 queue and
event store behind it.

POST /runs               -> 202 + run id at once; the run happens in a worker
GET  /runs/{id}          -> status, answer, events so far
GET  /runs/{id}/events   -> the same events as a live stream (SSE)

Admission control (429) when the backlog or one tenant's share is full.
An Idempotency-Key header makes a retried POST return the first run.
"""
import asyncio
import json
import threading
import time
import uuid
from collections import Counter
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from lab.bus import EventStore, Queue


class RunIn(BaseModel):
    question: str
    tenant: str = "default"


class Service:
    def __init__(self, agent, workers=8, max_backlog=None, tenant_limit=None):
        """agent(question, emit) -> answer. emit(type, **data) records a progress event."""
        self.agent, self.n_workers = agent, workers
        self.max_backlog, self.tenant_limit = max_backlog, tenant_limit
        self.queue, self.events = Queue(visibility=600), EventStore()
        self.runs, self.keys, self.open = {}, {}, Counter()  # open = unfinished runs per tenant
        self.lock, self.stop, self.threads = threading.Lock(), threading.Event(), []
        self.app = FastAPI(on_startup=[self.start], on_shutdown=[self.shutdown])
        self.app.post("/runs", status_code=202)(self.create)
        self.app.get("/runs/{run_id}")(self.get)
        self.app.get("/runs/{run_id}/events")(self.stream)
        self.app.get("/healthz")(lambda: {"ok": True, "backlog": sum(self.open.values())})

    def start(self):
        self.threads = [threading.Thread(target=self.worker, daemon=True) for _ in range(self.n_workers)]
        for t in self.threads:
            t.start()

    def shutdown(self):
        self.stop.set()
        for t in self.threads:
            t.join()

    def emit(self, run_id, type, **data):
        with self.lock:  # one version counter per run: events stay in order
            self.runs[run_id]["v"] = self.events.append(run_id, type, data, self.runs[run_id]["v"])

    def create(self, body: RunIn, idempotency_key: str | None = Header(None)):
        key = f"{body.tenant}:{idempotency_key}" if idempotency_key else None
        with self.lock:
            if key in self.keys:  # a retry of a request we already took
                return self.view(self.keys[key])
            if self.max_backlog and sum(self.open.values()) >= self.max_backlog:
                raise HTTPException(429, "runtime is full", {"Retry-After": "1"})
            if self.tenant_limit and self.open[body.tenant] >= self.tenant_limit:
                raise HTTPException(429, "tenant limit reached", {"Retry-After": "1"})
            run_id = uuid.uuid4().hex[:12]
            self.runs[run_id] = {"status": "queued", "tenant": body.tenant, "answer": None, "v": 0,
                                 "created": time.time(), "seconds": None}
            self.open[body.tenant] += 1
            if key:
                self.keys[key] = run_id
        self.emit(run_id, "RunQueued")
        self.queue.send({"run_id": run_id, "question": body.question}, key=run_id)
        return self.view(run_id)

    def view(self, run_id):
        r = self.runs[run_id]
        return {"run_id": run_id, "status": r["status"], "answer": r["answer"], "seconds": r["seconds"]}

    def get(self, run_id: str):
        if run_id not in self.runs:
            raise HTTPException(404, "no such run")
        return {**self.view(run_id), "events": self.events.read(run_id)}

    async def stream(self, run_id: str):
        async def gen():
            sent = 0
            while True:
                events = self.events.read(run_id)
                for e in events[sent:]:
                    yield f"event: {e['type']}\ndata: {json.dumps(e)}\n\n"
                sent = len(events)
                if events and events[-1]["type"] == "RunFinished":
                    return
                await asyncio.sleep(0.05)
        return StreamingResponse(gen(), media_type="text/event-stream")

    def worker(self):
        while not self.stop.is_set():
            job = self.queue.receive()
            if job is None:
                time.sleep(0.005)
                continue
            job_id, body, _, _ = job
            run_id, run = body["run_id"], self.runs[body["run_id"]]
            run["status"] = "running"
            self.emit(run_id, "RunStarted")
            try:
                answer, status = self.agent(body["question"], lambda t, **d: self.emit(run_id, t, **d)), "done"
            except Exception as e:
                answer, status = f"{type(e).__name__}: {e}", "failed"
            with self.lock:
                run.update(status=status, answer=answer, seconds=time.time() - run["created"])
                self.open[run["tenant"]] -= 1
            self.emit(run_id, "RunFinished", status=status)
            self.queue.ack(job_id)
