const $ = (id) => document.getElementById(id);
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};

let slides = [], i = 0, answers = {};

function build(id, only) {
  const lessons = id === "all" ? LESSONS : LESSONS.filter((l) => l.id === id);
  const s = [];
  if (!only) {
    for (const l of lessons) {
      for (const c of l.cards) s.push({ kind: "Concept", l, ...c });
      for (const c of l.qa) s.push({ kind: "Likely question", l, ...c });
    }
  }
  for (const l of lessons) {
    QUIZ[l.id].forEach((item, n) => {
      const key = l.id + "-" + n;
      if (!only || only.has(key)) s.push({ kind: "Quiz", l, item, key });
    });
  }
  s.push({ kind: "Result" });
  return s;
}

function start(id, only) {
  slides = build(id, only);
  answers = {};
  i = only ? 0 : Math.min(+store.get("pos:" + id) || 0, slides.length - 1);
  render();
}

function render() {
  const s = slides[i], card = $("card");
  $("kind").textContent = s.l ? `${s.kind} - L${s.l.id} ${s.l.title}` : s.kind;
  $("pos").textContent = `${i + 1} / ${slides.length}`;
  $("bar").style.width = ((i + 1) / slides.length) * 100 + "%";
  $("prev").disabled = i === 0;
  $("next").disabled = i === slides.length - 1;
  card.className = s.kind.split(" ")[0].toLowerCase();
  if (s.kind === "Concept") card.innerHTML = `<h2>${s.t}</h2><div>${s.b}</div>`;
  else if (s.kind === "Likely question") {
    card.innerHTML = `<h2>${s.q}</h2>` + (s.shown
      ? `<div class="answer">${s.a}</div>`
      : `<button class="reveal">Show answer (space)</button>`);
  } else if (s.kind === "Quiz") renderQuiz(s, card);
  else renderResult(card);
  store.set("pos:" + $("lesson").value, i);
}

function renderQuiz(s, card) {
  const picked = answers[s.key];
  card.innerHTML = `<h2>${s.item.q}</h2>` + s.item.o.map((o, n) => {
    let cls = "";
    if (picked !== undefined) cls = n === s.item.a ? "right" : n === picked ? "wrong" : "";
    return `<button class="opt ${cls}" data-n="${n}" ${picked !== undefined ? "disabled" : ""}>${o}</button>`;
  }).join("") + (picked !== undefined ? `<p class="explain">${s.item.e}</p>` : "");
}

function renderResult(card) {
  const qs = slides.filter((s) => s.kind === "Quiz");
  const right = qs.filter((s) => answers[s.key] === s.item.a).length;
  const wrong = qs.filter((s) => answers[s.key] !== s.item.a).map((s) => s.key);
  card.innerHTML = `<h2>Score: ${right} / ${qs.length}</h2>` +
    (wrong.length ? `<button id="retry">Retry wrong or skipped (${wrong.length})</button>` : "<p>All right.</p>") +
    `<button id="restart">Start again</button>` +
    `<p>Next: open <b>Quiz with Claude</b> for open questions and graded answers.</p>`;
  card.dataset.wrong = wrong.join(",");
}

function go(d) { i = Math.max(0, Math.min(slides.length - 1, i + d)); render(); }

$("card").addEventListener("click", (e) => {
  const s = slides[i], t = e.target;
  if (t.classList.contains("reveal")) { s.shown = true; render(); }
  else if (t.classList.contains("opt")) { answers[s.key] = +t.dataset.n; render(); }
  else if (t.id === "retry") start($("lesson").value, new Set($("card").dataset.wrong.split(",")));
  else if (t.id === "restart") { store.set("pos:" + $("lesson").value, 0); start($("lesson").value); }
});
$("prev").onclick = () => go(-1);
$("next").onclick = () => go(1);
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
  if (e.key === "ArrowRight") go(1);
  else if (e.key === "ArrowLeft") go(-1);
  else if (e.key === " " && slides[i].kind === "Likely question") {
    e.preventDefault();
    slides[i].shown = !slides[i].shown;
    render();
  }
});

const sel = $("lesson");
sel.innerHTML = `<option value="all">All lessons</option>` +
  LESSONS.map((l) => `<option value="${l.id}">L${l.id} ${l.title}</option>`).join("");
sel.value = store.get("lesson") || "01";
sel.onchange = () => { store.set("lesson", sel.value); start(sel.value); };
start(sel.value);
