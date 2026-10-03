"""A job queue and an event store on SQLite. A stand-in for SQS / Kafka /
Redis Streams, small enough to read, with the same rules.

Queue: at-least-once delivery. receive() hides a job for `visibility` seconds.
       ack() removes it. No ack (the worker died) -> the job comes back.
       After max_attempts it goes to the dead-letter state.
EventStore: append-only events per stream, with a version check on append.
"""
import json
import sqlite3
import threading
import time


class Conflict(Exception):
    """Someone else appended to this stream first."""


class Db:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.lock = threading.Lock()  # one writer at a time, like one partition leader

    def q(self, sql, *args):
        with self.lock:
            return self.db.execute(sql, args).fetchall()


class Queue(Db):
    def __init__(self, visibility=1.0, max_attempts=3, path=":memory:"):
        super().__init__(path)
        self.visibility, self.max_attempts = visibility, max_attempts
        self.q("CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, key TEXT UNIQUE, body TEXT,"
               " sent REAL, visible_at REAL DEFAULT 0, attempts INT DEFAULT 0, state TEXT DEFAULT 'ready')")

    def send(self, body, key=None):
        """key = dedupe key. The same key twice makes one job. Returns the job id."""
        self.q("INSERT OR IGNORE INTO jobs (key, body, sent) VALUES (?, ?, ?)",
               key, json.dumps(body), time.time())
        return self.q("SELECT id FROM jobs WHERE key = ?", key)[0][0] if key else \
            self.q("SELECT max(id) FROM jobs")[0][0]

    def receive(self):
        """Claim one job, or None. Returns (id, body, attempt, seconds waited)."""
        now = time.time()
        with self.lock:
            self.db.execute("UPDATE jobs SET state = 'dead' WHERE state = 'ready' AND attempts >= ?"
                            " AND visible_at <= ?", (self.max_attempts, now))
            row = self.db.execute("SELECT id, body, attempts, sent FROM jobs WHERE state = 'ready'"
                                  " AND visible_at <= ? ORDER BY id LIMIT 1", (now,)).fetchone()
            if not row:
                return None
            self.db.execute("UPDATE jobs SET attempts = attempts + 1, visible_at = ? WHERE id = ?",
                            (now + self.visibility, row[0]))
        return row[0], json.loads(row[1]), row[2] + 1, now - row[3]

    def ack(self, job_id):
        self.q("UPDATE jobs SET state = 'done' WHERE id = ?", job_id)

    def count(self, state):
        return self.q("SELECT count(*) FROM jobs WHERE state = ?", state)[0][0]


class EventStore(Db):
    def __init__(self, path=":memory:"):
        super().__init__(path)
        self.q("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT,"
               " stream TEXT, version INT, type TEXT, data TEXT, UNIQUE (stream, version))")

    def append(self, stream, type, data, expected):
        """expected = the version the writer last saw. A stale writer gets Conflict."""
        try:
            self.q("INSERT INTO events (stream, version, type, data) VALUES (?, ?, ?, ?)",
                   stream, expected + 1, type, json.dumps(data))
        except sqlite3.IntegrityError:
            raise Conflict(f"{stream} is past version {expected}") from None
        return expected + 1

    def read(self, stream=None, upto=None):
        rows = self.q("SELECT seq, stream, version, type, data FROM events WHERE (? IS NULL OR stream = ?)"
                      " AND (? IS NULL OR seq <= ?) ORDER BY seq", stream, stream, upto, upto)
        return [{"seq": s, "stream": st, "version": v, "type": t, **json.loads(d)}
                for s, st, v, t, d in rows]
