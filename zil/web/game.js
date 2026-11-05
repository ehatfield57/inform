// The play screen: status line, scrolling text and the command line.
// Used by the main page and by game.html. Needs these elements:
//   #left #right (status line), #out (game text), #line (input), #why (note by the input)

(function () {
  const out = document.getElementById("out");
  const line = document.getElementById("line");
  const why = document.getElementById("why");
  let waiting = false, charMode = false;
  const history = [];
  let hpos = 0;

  function scrollDown() { out.scrollTop = out.scrollHeight; }

  function addText(t) {
    out.append(document.createTextNode(t));
    scrollDown();
  }
  function addCommand(t) {
    out.append(el("span", { class: "cmd", text: t }), "\n");
    scrollDown();
  }

  function setWaiting(on, reason) {
    waiting = on;
    line.disabled = !on;
    why.textContent = reason || "";
    if (on) line.focus();
  }

  function showStatus(s) {
    if (!s) return;
    document.getElementById("left").textContent = s.left || " ";
    document.getElementById("right").textContent = s.right || "";
  }

  async function load() {
    const t = await api("/api/transcript");
    out.textContent = "";
    for (const [kind, text] of t.transcript) {
      if (kind === "out") addText(text); else addCommand(text);
    }
    showStatus(t.status);
    setWaiting(t.state === "input", t.state === "paused" ? "paused in the debugger" :
                                     t.state === "ended" ? "the game has ended" : "");
  }

  on("output", (ev) => addText(ev.text));
  on("echo", (ev) => addCommand(ev.text));
  on("input", (ev) => { charMode = ev.char; showStatus(ev.status); setWaiting(true, ev.char ? "press a key" : ""); });
  on("running", () => setWaiting(false, ""));
  on("paused", (ev) => setWaiting(false, "paused at " + locText(ev.loc)));
  on("ended", () => setWaiting(false, "the game has ended"));
  on("error", (ev) => { addText("\n[" + ev.message + "]\n"); setWaiting(false, "error"); });
  on("restarted", load);

  line.addEventListener("keydown", (e) => {
    if (!waiting) return;
    if (charMode) {
      e.preventDefault();
      const k = e.key.length === 1 ? e.key : (e.key === "Enter" ? "\n" : "");
      if (k) { setWaiting(false); api("/api/input", { line: k === "\n" ? "" : k }); }
      return;
    }
    if (e.key === "Enter") {
      const v = line.value;
      line.value = "";
      if (v.trim()) history.push(v);
      hpos = history.length;
      setWaiting(false);
      api("/api/input", { line: v });
    } else if (e.key === "ArrowUp") {
      if (hpos > 0) { hpos--; line.value = history[hpos]; }
      e.preventDefault();
    } else if (e.key === "ArrowDown") {
      if (hpos < history.length) { hpos++; line.value = history[hpos] || ""; }
      e.preventDefault();
    }
  });
  out.addEventListener("click", () => { if (!getSelection().toString()) line.focus(); });

  window.ZILGame = { load };
})();
