let sessionId = null;

function addMsg(text, cls) {
  const d = document.createElement("div");
  d.className = "msg " + cls;
  d.textContent = text;
  $("log").appendChild(d);
  $("log").scrollTop = $("log").scrollHeight;
  return d;
}

async function send(message) {
  const sel = $("lesson");
  const wait = addMsg("Claude is thinking...", "bot");
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId, lesson: sel.options[sel.selectedIndex].text }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.status);
    sessionId = data.session_id;
    wait.textContent = data.reply;
    wait.innerHTML = wait.innerHTML.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  } catch (e) {
    wait.className = "msg err";
    wait.textContent = location.protocol === "file:"
      ? "Chat needs the server. Run: uv run web/server.py, then open http://127.0.0.1:8765"
      : "Error: " + e.message;
  }
}

function newQuiz() {
  sessionId = null;
  $("log").innerHTML = "";
  send("start");
}

$("chat-toggle").onclick = () => {
  $("chat").hidden = !$("chat").hidden;
  if (!$("chat").hidden && !$("log").children.length) newQuiz();
};
$("chat-new").onclick = newQuiz;
$("chat-form").onsubmit = (e) => {
  e.preventDefault();
  const text = $("msg").value.trim();
  if (!text) return;
  $("msg").value = "";
  addMsg(text, "me");
  send(text);
};
$("msg").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("chat-form").requestSubmit(); }
});
