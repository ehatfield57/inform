// Shared by every window: talking to the server, and to the other windows.

const ZIL = {
  win: document.body.dataset.win || "main",
  handlers: {},
  channel: ("BroadcastChannel" in window) ? new BroadcastChannel("zil") : null,
  peerHandlers: {},
};

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  const r = await fetch(path, opts);
  return r.json();
}

// Server events ----------------------------------------------------------

function on(type, fn) {
  (ZIL.handlers[type] = ZIL.handlers[type] || []).push(fn);
}

function connect(onOpen) {
  const es = new EventSource("/events");
  es.onopen = () => {
    document.body.classList.remove("offline");
    if (onOpen) onOpen();
  };
  es.onerror = () => document.body.classList.add("offline");
  es.onmessage = (m) => {
    let ev;
    try { ev = JSON.parse(m.data); } catch (e) { return; }
    for (const fn of (ZIL.handlers[ev.type] || [])) fn(ev);
    for (const fn of (ZIL.handlers["*"] || [])) fn(ev);
  };
  return es;
}

// Other windows ----------------------------------------------------------

function tell(msg) {
  if (ZIL.channel) ZIL.channel.postMessage(Object.assign({ from: ZIL.win }, msg));
}

function onPeer(type, fn) {
  (ZIL.peerHandlers[type] = ZIL.peerHandlers[type] || []).push(fn);
}

if (ZIL.channel) {
  ZIL.channel.onmessage = (m) => {
    const msg = m.data || {};
    if (msg.type === "close" && msg.win === ZIL.win && ZIL.win !== "main") {
      window.close();
      return;
    }
    if (msg.type === "ping" && ZIL.win !== "main") {
      tell({ type: "alive", win: ZIL.win });
      return;
    }
    for (const fn of (ZIL.peerHandlers[msg.type] || [])) fn(msg);
  };
}

// Child windows announce themselves so the main page can show which are open.
if (ZIL.win !== "main") {
  tell({ type: "alive", win: ZIL.win });
  setInterval(() => tell({ type: "alive", win: ZIL.win }), 2000);
  window.addEventListener("beforeunload", () => tell({ type: "gone", win: ZIL.win }));
}

// Helpers ------------------------------------------------------------------

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v);
  }
  for (const k of kids) if (k != null) e.append(k);
  return e;
}

function stateLabel(state) {
  return { input: "waiting for you", running: "running", paused: "paused",
           ended: "game over", error: "error" }[state] || state;
}

function setPill(pill, state) {
  pill.className = "pill " + state;
  pill.textContent = stateLabel(state);
}

function locText(loc) {
  return loc ? `${loc.file}:${loc.line}` : "";
}
