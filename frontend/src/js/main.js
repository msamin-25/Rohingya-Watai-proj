// App entry point. All text from the server is inserted with textContent (never innerHTML).
import { api, ApiError, helperKey } from "./api.js";
import { describeResult, QUALITY } from "./messages.js";
import { MAX_SECONDS, micAvailable, startRecording } from "./recorder.js";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const TAKES_GOAL = 3;
const UNTAUGHT = "__untaught__";

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c != null) el.append(c);
  return el;
}

const state = { phrases: [], unlocked: false, busy: false };

// ---------- tabs ----------
function showTab(name) {
  for (const tab of $$("[role=tab]")) {
    const on = tab.id === `tab-${name}`;
    tab.setAttribute("aria-selected", String(on));
    $(`#${tab.getAttribute("aria-controls")}`).hidden = !on;
  }
  if (name !== "speak" && state.unlocked) refreshAll();
}
$$("[role=tab]").forEach((t) => t.addEventListener("click", () => showTab(t.id.replace("tab-", ""))));

// ---------- speech output (English, on-device voice) ----------
function speak(text) {
  if (!("speechSynthesis" in window) || !text) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-CA";
  u.rate = 0.9;
  speechSynthesis.speak(u);
}

// ---------- shared recording helper ----------
async function recordWith(button, { idleLabel, onDone }) {
  const label = button.querySelector(".mic-label") ?? button;
  const timerEl = button.querySelector(".mic-timer");
  if (state.busy && !button.recording) return;
  if (button.recording) {
    const rec = button.recording;
    button.recording = null;
    button.classList.remove("recording");
    button.disabled = true;
    label.textContent = "…";
    try {
      await onDone(await rec.stop());
    } catch (err) {
      alert(`Could not read the recording: ${err.message}`);
    } finally {
      button.disabled = false;
      label.textContent = idleLabel;
      if (timerEl) timerEl.textContent = "";
      state.busy = false;
    }
    return;
  }
  if (!micAvailable()) {
    alert("The microphone needs a secure page. Open http://localhost:8000 (not an IP address).");
    return;
  }
  state.busy = true;
  try {
    button.recording = await startRecording({
      onTick: (s) => {
        if (timerEl) timerEl.textContent = `${s.toFixed(1)}s`;
        if (s >= MAX_SECONDS && button.recording) button.click();
      },
    });
    button.classList.add("recording");
    label.textContent = "■ Stop";
    if (timerEl) timerEl.textContent = "0.0s";
  } catch (err) {
    state.busy = false;
    alert(err?.name === "NotAllowedError" ? "Microphone permission was denied." : `Could not start the microphone: ${err.message}`);
  }
}

// ---------- SPEAK ----------
const mic = $("#mic");
mic.addEventListener("click", () =>
  recordWith(mic, {
    idleLabel: "Tap to speak",
    onDone: async ({ wav, quality }) => {
      let result;
      if (quality.problem) {
        result = { status: quality.problem, message: QUALITY[quality.problem] };
      } else {
        showResult({ tone: "busy", title: "Listening…", body: "" });
        try {
          result = await api.interpret(wav);
        } catch (err) {
          result = { status: "error", message: err.message };
        }
      }
      const view = describeResult(result);
      showResult(view);
      speak(view.speak);
    },
  }),
);

function showResult({ tone, title, body, speak: say }) {
  const box = $("#result");
  box.hidden = false;
  box.className = `result ${tone}`;
  box.replaceChildren(
    h("p", { class: "result-title" }, title),
    body ? h("p", { class: "result-body" }, body) : null,
    say ? h("button", { class: "secondary", onclick: () => speak(say) }, "🔊 Say it again") : null,
  );
}

// ---------- unlock (helper key) ----------
$(".key-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const key = e.target.key.value.trim();
  helperKey.set(key);
  try {
    await api.checkKey();
    e.target.reset();
    setUnlocked(true);
  } catch {
    helperKey.clear();
    alert("That helper key is not right. Copy RVB_ADMIN_TOKEN from .env.");
  }
});

function setUnlocked(on) {
  state.unlocked = on;
  $$("[data-locked]").forEach((el) => (el.hidden = on));
  $$("[data-unlocked]").forEach((el) => (el.hidden = !on));
  if (on) refreshAll();
}

function handleAuth(err) {
  if (err instanceof ApiError && err.status === 401) {
    helperKey.clear();
    setUnlocked(false);
    return true;
  }
  return false;
}

async function refreshAll() {
  try {
    const [{ phrases }, { takes }] = await Promise.all([api.phrases(), api.takes()]);
    state.phrases = phrases;
    renderTeach();
    renderTestPicker();
    renderTakes(takes);
  } catch (err) {
    if (!handleAuth(err)) console.error(err);
  }
}

// ---------- TEACH ----------
function renderTeach() {
  const list = $("#teach-list");
  list.replaceChildren(
    ...state.phrases.map((p) => {
      const msg = h("span", { class: "msg", role: "status" });
      const btn = h("button", { class: "rec" }, "● Record take");
      btn.addEventListener("click", () =>
        recordWith(btn, {
          idleLabel: "● Record take",
          onDone: async ({ wav, quality }) => {
            if (quality.problem) return (msg.textContent = QUALITY[quality.problem]);
            try {
              await api.addTake(wav, { kind: "teach", speaker: $("#teach-speaker").value, phrase_id: p.id });
              msg.textContent = "Saved ✓";
              await refreshAll();
            } catch (err) {
              if (!handleAuth(err)) msg.textContent = err.message;
            }
          },
        }),
      );
      const done = Math.min(p.teach_takes, TAKES_GOAL);
      const dots = h("span", { class: "dots", "aria-label": `${p.teach_takes} takes` }, ...Array.from({ length: TAKES_GOAL }, (_, i) => h("i", { class: i < done ? "on" : "" })));
      return h(
        "li",
        { class: "phrase" },
        h("div", { class: "phrase-text" }, h("span", { class: "english" }, p.english), h("span", { class: `badge ${p.category}` }, p.category)),
        h("div", { class: "phrase-actions" }, dots, h("span", { class: "count" }, `${p.teach_takes} taught`), btn, msg),
      );
    }),
  );
}

// ---------- PHRASES & TESTS ----------
function renderTestPicker() {
  const sel = $("#test-phrase");
  const current = sel.value;
  sel.replaceChildren(
    ...state.phrases.map((p) => h("option", { value: p.id }, `${p.english}${p.teach_takes ? "" : " (not taught)"}`)),
    h("option", { value: UNTAUGHT }, "A phrase I never taught"),
  );
  if (current) sel.value = current;
  $("#test-note-wrap").hidden = sel.value !== UNTAUGHT;
}
$("#test-phrase").addEventListener("change", () => ($("#test-note-wrap").hidden = $("#test-phrase").value !== UNTAUGHT));

const testBtn = $("#test-record");
testBtn.addEventListener("click", () =>
  recordWith(testBtn, {
    idleLabel: "● Record test",
    onDone: async ({ wav, quality }) => {
      const msg = $("#test-msg");
      if (quality.problem) return (msg.textContent = QUALITY[quality.problem]);
      const pid = $("#test-phrase").value;
      try {
        await api.addTake(wav, {
          kind: "test",
          speaker: $("#test-speaker").value,
          phrase_id: pid === UNTAUGHT ? "" : pid,
          note: pid === UNTAUGHT ? $("#test-note").value : "",
        });
        msg.textContent = "Test take saved ✓";
        await refreshAll();
      } catch (err) {
        if (!handleAuth(err)) msg.textContent = err.message;
      }
    },
  }),
);

function renderTakes(takes) {
  const english = Object.fromEntries(state.phrases.map((p) => [p.id, p.english]));
  const rows = [...takes].reverse().map((t) => {
    const play = h("button", { class: "small-btn secondary", "aria-label": "Play" }, "▶");
    play.addEventListener("click", async () => {
      const url = URL.createObjectURL(await api.takeAudio(t.id));
      const a = new Audio(url);
      a.onended = () => URL.revokeObjectURL(url);
      a.play();
    });
    const del = h("button", { class: "small-btn danger", "aria-label": "Delete" }, "✕");
    del.addEventListener("click", async () => {
      if (!confirm("Delete this recording?")) return;
      await api.deleteTake(t.id).catch(handleAuth);
      refreshAll();
    });
    const label = t.phrase_id ? english[t.phrase_id] ?? t.phrase_id : `Never taught${t.note ? `: ${t.note}` : ""}`;
    return h(
      "tr",
      {},
      h("td", {}, label),
      h("td", {}, h("span", { class: `badge ${t.kind}` }, t.kind)),
      h("td", {}, t.speaker),
      h("td", {}, new Date(t.created_at).toLocaleString()),
      h("td", { class: "nowrap" }, play, " ", del),
    );
  });
  $("#takes-body").replaceChildren(...(rows.length ? rows : [h("tr", {}, h("td", { colspan: "5", class: "empty" }, "No recordings yet."))]));
}

$("#del-speaker-btn").addEventListener("click", async () => {
  const speaker = $("#del-speaker").value.trim();
  if (!speaker) return alert("Type the speaker label to delete.");
  if (!confirm(`Delete ALL recordings by "${speaker}"? This cannot be undone.`)) return;
  try {
    const { deleted } = await api.deleteBySpeaker(speaker);
    alert(`Deleted ${deleted} recording(s).`);
  } catch (err) {
    if (!handleAuth(err)) alert(err.message);
  }
  refreshAll();
});

$("#export").addEventListener("click", async () => {
  try {
    const blob = await api.exportZip();
    const url = URL.createObjectURL(blob);
    const a = h("a", { href: url, download: "rvb-recordings.zip" });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  } catch (err) {
    if (!handleAuth(err)) alert(err.message);
  }
});

$("#add-phrase").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api.addPhrase(f.english.value, f.category.value);
    f.reset();
    refreshAll();
  } catch (err) {
    if (!handleAuth(err)) alert(err.message);
  }
});

// ---------- start ----------
if (helperKey.get()) {
  api.checkKey().then(() => setUnlocked(true), () => helperKey.clear());
}
if (!micAvailable()) {
  showResult({ tone: "warn", title: "Microphone not available here.", body: "Open http://localhost:8000 in Chrome, Edge, Firefox or Safari." });
}
