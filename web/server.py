"""Serve the cards page and let Claude Code quiz you: uv run web/server.py"""
import json
import re
import subprocess
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST, PORT = "127.0.0.1", 8765
WEB = Path(__file__).parent
ROOT = WEB.parent
PROMPT = (WEB / "quiz_prompt.md").read_text()
ORIGINS = {f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"}
SESSION = re.compile(r"^[0-9a-f-]{36}$")


def ask_claude(message: str, session_id: str | None) -> dict:
    cmd = ["claude", "-p", "--output-format", "json", "--append-system-prompt", PROMPT,
           "--tools", "Read,Grep,Glob", "--strict-mcp-config"]
    if session_id:
        cmd += ["--resume", session_id]
    out = subprocess.run(cmd, input=message, cwd=ROOT, capture_output=True, text=True, timeout=300)
    if out.returncode:
        raise RuntimeError(out.stderr.strip() or out.stdout.strip() or "claude failed")
    data = json.loads(out.stdout)
    return {"reply": data.get("result", ""), "session_id": data.get("session_id")}


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/api/chat":
            return self.send_error(404)
        if self.headers.get("Origin") not in ORIGINS:
            return self.send_error(403, "bad origin")
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        sid = body.get("session_id")
        if sid and not SESSION.match(sid):
            return self.send_error(400, "bad session id")
        msg = body.get("message", "").strip()
        if not sid:
            msg = f"Quiz me on: {body.get('lesson', 'all lessons')}. {msg}".strip()
        try:
            res, code = ask_claude(msg, sid), 200
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            res, code = {"error": str(e)}, 500
        data = json.dumps(res).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print(f"Open http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), partial(Handler, directory=WEB)).serve_forever()
