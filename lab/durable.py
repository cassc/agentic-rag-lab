"""Durable execution from scratch: an event log plus replay.

The workflow is a plain Python function. Every side effect (LLM call, tool
call) goes through ctx.step(). Each finished step is appended to a log file.
After a crash you call the same function again with the same run id: finished
steps return their logged result (replay) and real work starts at the first
step with no result. This is the core idea of Temporal.

Lesson 7 saved the *state* (the message list). This saves the *history* and
rebuilds the state by running the code again.
"""
import json
import os
import time
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "data" / "runs"


class Crash(Exception):
    """Raised on purpose to simulate the process dying."""


class NonDeterminism(Exception):
    """The code asked for a different step than the log has at this position."""


class Ctx:
    def __init__(self, run_id, crash_after=None, crash_before_record=None):
        self.run_id, self.path = run_id, RUNS / f"{run_id}.jsonl"
        self.events = ([json.loads(l) for l in self.path.read_text().splitlines()]
                       if self.path.exists() else [])
        self.pos = 0  # next position in the log
        self.crash_after, self.crash_before_record = crash_after, crash_before_record
        self.ran, self.replayed, self.attempts = 0, 0, 0

    def key(self, name):
        """Idempotency key: the same on every replay of this step."""
        return f"{self.run_id}:{self.pos}:{name}"

    def step(self, name, fn, *args, retries=3, backoff=0.2):
        """Run fn once, ever. The result must be JSON."""
        if self.pos < len(self.events):  # replay: do not run fn again
            e = self.events[self.pos]
            if e["step"] != name:
                raise NonDeterminism(f"log has '{e['step']}' at {self.pos}, code asked '{name}'")
            self.pos += 1
            self.replayed += 1
            return e["result"]
        for attempt in range(1, retries + 1):
            self.attempts += 1
            try:
                out = fn(*args)
                break
            except Exception:
                if attempt == retries:
                    raise
                time.sleep(backoff * 2 ** (attempt - 1))  # exponential backoff
        if self.crash_before_record == name:
            raise Crash(f"died after '{name}' ran, before the log write")
        RUNS.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps({"step": name, "result": out}) + "\n")
            f.flush()
            os.fsync(f.fileno())  # on disk before we go on
        self.pos += 1
        self.ran += 1
        if self.crash_after == name:
            raise Crash(f"died after '{name}' was logged")
        return out
