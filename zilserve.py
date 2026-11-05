#!/usr/bin/env python3
"""zilserve.py - play a ZIL game in the browser, with its source and insides on view.

Starts a small web server on this computer only (127.0.0.1) and opens the main page.
Windows you can open:

    Source     the ZIL source: breakpoints, pause, step into / over / out, call stack
    State      globals, the locals of each routine on the stack, the object tree
    Map        the rooms you've visited, drawn as you go (or the whole map)

The main page is the game itself; its side panel has a switch for each other window,
the story and seed, and Start again. Every window shows the same running game, so
you can spread them over several screens. Stop the server with Ctrl-C. More in
zil/README.md.

Examples:
  python3 zilserve.py sources/zork1-r119.zip --seed 1
  python3 zilserve.py sources/zork3-mac-r15.zip --seed 1 --port 8800
  python3 zilserve.py sources/zork2-r63.zip --no-browser     # then open the address it prints

In the Source window: click a line number for a breakpoint; F5 continue, F6 pause,
F10 step over, F11 step into, Shift+F11 step out.
"""

import argparse
import glob
import json
import os
import queue
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from zil.session import Session          # noqa: E402

WEB = os.path.join(HERE, "zil", "web")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".ico": "image/x-icon"}

SESSION = None
SOURCES = os.path.join(HERE, "sources")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    # -------------------------------------------------------- helpers
    def send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return {}

    # -------------------------------------------------------- GET
    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        path = url.path
        s = SESSION
        if path == "/events":
            return self.events()
        if path == "/api/info":
            return self.send(200, s.game_info())
        if path == "/api/state":
            return self.send(200, s.snapshot())
        if path == "/api/transcript":
            return self.send(200, {"transcript": s.transcript, "state": s.state,
                                   "status": s.status})
        if path == "/api/source":
            text = s.source(q.get("file", ""))
            if text is None:
                return self.send(404, {"error": "no such file"})
            return self.send(200, {"file": q["file"], "text": text})
        if path == "/api/objects":
            return self.send(200, s.objects())
        if path == "/api/object":
            o = s.object(int(q.get("n", "0")))
            return self.send(200 if o else 404, o or {"error": "no such object"})
        if path == "/api/map":
            return self.send(200, s.map())
        if path == "/api/breakpoints":
            return self.send(200, s.breakpoint_list())
        if path == "/api/games":
            games = sorted(os.path.basename(p) for p in glob.glob(os.path.join(SOURCES, "*.zip")))
            return self.send(200, {"games": games, "current": os.path.basename(s.path)})
        # static files
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB, name))
        if not full.startswith(WEB) or not os.path.isfile(full):
            return self.send(404, "not found", "text/plain")
        with open(full, "rb") as fh:
            data = fh.read()
        self.send(200, data, TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))

    def events(self):
        """Server-sent events: one long response, one JSON message per event."""
        s = SESSION
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = s.subscribe()
        try:
            self.wfile.write(b"retry: 1000\n\n")
            self.wfile.flush()
            while True:
                try:
                    ev = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    continue
                # Merge runs of output into one message.
                if ev.get("type") == "output":
                    text = [ev["text"]]
                    while True:
                        try:
                            nxt = q.get_nowait()
                        except queue.Empty:
                            nxt = None
                            break
                        if nxt.get("type") == "output":
                            text.append(nxt["text"])
                        else:
                            break
                    self.wfile.write(("data: %s\n\n" % json.dumps(
                        {"type": "output", "text": "".join(text)})).encode("utf-8"))
                    if nxt is not None:
                        self.wfile.write(("data: %s\n\n" % json.dumps(nxt)).encode("utf-8"))
                else:
                    self.wfile.write(("data: %s\n\n" % json.dumps(ev)).encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            s.unsubscribe(q)
            self.close_connection = True

    # -------------------------------------------------------- POST
    def do_POST(self):
        url = urlparse(self.path)
        b = self.body()
        s = SESSION
        p = url.path
        if p == "/api/input":
            s.send_input(str(b.get("line", "")))
            return self.send(200, {"ok": True})
        if p == "/api/debug":
            s.command(b.get("cmd", ""))
            return self.send(200, {"ok": True})
        if p == "/api/breakpoint":
            if "routine" in b:
                s.set_routine_break(str(b["routine"]), bool(b.get("on", True)))
            else:
                s.set_breakpoint(str(b.get("file")), int(b.get("line", 0)), bool(b.get("on", True)))
            return self.send(200, s.breakpoint_list())
        if p == "/api/restart":
            seed = b.get("seed")
            game = b.get("game")
            path = None
            if game:
                path = os.path.join(SOURCES, os.path.basename(game))
                if not os.path.isfile(path):
                    return self.send(404, {"error": "no such game"})
            if "seed" not in b:
                seed = "keep"
            elif seed in (None, ""):
                seed = None
            else:
                seed = int(seed)
            try:
                s.restart(seed=seed, path=path)
            except Exception as e:      # a game that won't load
                return self.send(500, {"error": str(e)})
            return self.send(200, {"ok": True})
        self.send(404, {"error": "unknown"})


def main():
    global SESSION
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="folder of .zil files, or a zip of them (see sources/)")
    ap.add_argument("--seed", type=int, help="random seed, for reproducible runs")
    ap.add_argument("--serial", help="serial number to report")
    ap.add_argument("--port", type=int, default=8765, help="web server port (default 8765)")
    ap.add_argument("--zilch", choices=["old", "new"],
                    help="which compiler generation to copy (normally worked out from the source)")
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser")
    args = ap.parse_args()
    try:
        SESSION = Session(args.source, seed=args.seed, serial=args.serial, zilch=args.zilch,
                          save_dir=os.path.join(HERE, "saves"))
    except Exception as e:
        print("Could not load %s: %s" % (args.source, e))
        sys.exit(1)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    url = "http://127.0.0.1:%d/" % args.port
    print("Playing %s at %s  (Ctrl-C to stop)" % (os.path.basename(args.source), url))
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
