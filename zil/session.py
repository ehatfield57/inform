"""A game running for the browser windows: its own thread, a debugger, and
snapshots of the game's state.

    s = Session("sources/zork1-r119.zip", seed=1)
    s.subscribe()          -> a queue of events (output, input wanted, paused ...)
    s.send_input("north")
    s.command("step-over")
    s.snapshot()           -> globals, call stack, locals
    s.objects(), s.object(n), s.map()

The game thread blocks while it waits for a command or sits at a breakpoint,
so the snapshots read a game that isn't moving.
"""

import os
import queue
import sys
import threading
import traceback

from .runtime import open_game, IO, Quit, Restart, describe_error, s16
from .compiler import Global, Op, Call, Local, Routine
from .reader import Atom
from . import ztext

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


class Reset(Exception):
    """Thrown inside the game thread to stop it (restart, new game)."""


# ---------------------------------------------------------------- input / output

class WebIO(IO):
    def __init__(self, session):
        self.s = session

    def write(self, text):
        self.s.emit_output(text)

    def read_line(self):
        return self.s.wait_input()

    def read_char(self):
        line = self.s.wait_input(char=True)
        return line[0] if line else "\n"

    def status(self, left, right):
        self.s.status = {"left": left, "right": right}

    def ask_filename(self, purpose, default):
        self.s.emit_output("%s file name (default %s): " % (purpose, default))
        name = self.s.wait_input().strip() or default
        folder = os.path.join(self.s.save_dir)
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, os.path.basename(name))


# ---------------------------------------------------------------- session

DIR_NAMES = {"NORTH": "north", "SOUTH": "south", "EAST": "east", "WEST": "west",
             "NE": "northeast", "NW": "northwest", "SE": "southeast", "SW": "southwest",
             "NORTHEAST": "northeast", "NORTHWEST": "northwest", "SOUTHEAST": "southeast",
             "SOUTHWEST": "southwest", "UP": "up", "DOWN": "down", "IN": "in", "OUT": "out"}

# Operations whose first argument is an object: used to guess which globals hold objects.
OBJECT_OPS = {"MOVE", "REMOVE", "LOC", "FIRST?", "NEXT?", "IN?", "FSET?", "FSET", "FCLEAR",
              "GETP", "PUTP", "GETPT", "PRINTD", "NEXTP"}


class Session:
    def __init__(self, path, seed=None, serial=None, save_dir=None, zilch=None):
        self.path = path
        self.zilch = zilch
        self.seed = seed
        self.serial = serial
        self.save_dir = save_dir or os.path.join(os.getcwd(), "saves")
        self.lock = threading.RLock()
        self.listeners = []
        self.breakpoints = set()          # (file, line)
        self.routine_breaks = set()       # routine names
        self.cond = threading.Condition(self.lock)
        self.inputs = queue.Queue()
        self.thread = None
        self.start_game()

    # -------------------------------------------------------- lifecycle
    def start_game(self):
        self.game = open_game(self.path, seed=self.seed, serial=self.serial, zilch=self.zilch)
        self.I = self.game.interp
        self.img = self.game.img
        self.status = {"left": "", "right": ""}
        self.state = "running"
        self.transcript = []              # [("out"|"in", text)]
        self.pause_info = None
        self.resume_cmd = None
        self.mode = None                  # stepping: into / over / out
        self.step_key = None
        self.step_depth = 0
        self.pause_req = False
        self.turn = 0
        self.visited = []
        self.transitions = []             # (from room, command, to room)
        self.last_here = None
        self.last_command = None
        self.error = None
        self._map_layout = None
        self.object_globals = self.find_object_globals()
        I = self.I
        I.on_node = self.on_node
        I.on_enter = self.on_enter
        self.update_trace()
        self.inputs = queue.Queue()
        rooms = self.rooms()
        self._map_layout = self.layout(rooms, set(rooms))   # before play: from the start room
        threading.stack_size(512 * 1024 * 1024)    # room for deep ZIL recursion
        self.thread = threading.Thread(target=self.run_game, daemon=True)
        self.thread.start()

    def run_game(self):
        try:
            self.I.run(WebIO(self))
            self.state = "ended"
            self.broadcast({"type": "ended"})
        except Reset:
            return
        except Exception as e:
            self.error = describe_error(e)
            self.state = "error"
            self.broadcast({"type": "error", "message": self.error})
            traceback.print_exc()

    def restart(self, seed="keep", path=None):
        if seed != "keep":
            self.seed = seed          # None = random
        if path is not None:
            self.path = path
            self.zilch = None         # a different game: work its compiler out again
        old = self.thread
        with self.lock:
            self.resume_cmd = "reset"
            self.cond.notify_all()
        self.inputs.put(Reset)
        if old is not None:
            old.join(timeout=2)
        self.start_game()
        self.broadcast({"type": "restarted", "game": self.game_info()})

    # -------------------------------------------------------- events
    def subscribe(self):
        q = queue.Queue()
        with self.lock:
            self.listeners.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.listeners:
                self.listeners.remove(q)

    def broadcast(self, ev):
        with self.lock:
            for q in self.listeners:
                q.put(ev)

    def emit_output(self, text):
        self.transcript.append(("out", text))
        self.broadcast({"type": "output", "text": text})

    # -------------------------------------------------------- input
    def wait_input(self, char=False):
        self.note_turn()
        self.state = "input"
        self.broadcast({"type": "input", "char": char, "status": self.status,
                        "turn": self.turn, "where": self.where()})
        line = self.inputs.get()
        if line is Reset:
            raise Reset()
        self.state = "running"
        self.transcript.append(("in", line))
        self.last_command = line
        self.broadcast({"type": "echo", "text": line})
        self.broadcast({"type": "running"})
        return line

    def send_input(self, line):
        self.inputs.put(line)

    def note_turn(self):
        """Called each time the game asks for input: track rooms for the map."""
        self.turn += 1
        here = self.here()
        if here and here != self.last_here:
            if here not in self.visited:
                self.visited.append(here)
            if self.last_here:
                self.transitions.append((self.last_here, self.last_command or "", here))
            self.last_here = here

    def here(self):
        name = Atom("HERE")
        if name in self.img.global_num:
            return self.I.global_value(name)
        if self.img.version <= 3:
            return self.I.rw(self.img.globals_addr)
        return 0

    # -------------------------------------------------------- debugger
    def update_trace(self):
        self.I.trace = bool(self.breakpoints or self.routine_breaks or self.mode or self.pause_req)

    def set_breakpoint(self, file, line, on):
        with self.lock:
            if on:
                self.breakpoints.add((file, line))
            else:
                self.breakpoints.discard((file, line))
            self.update_trace()
        self.broadcast({"type": "breakpoints", "list": self.breakpoint_list()})

    def set_routine_break(self, name, on):
        with self.lock:
            if on:
                self.routine_breaks.add(name)
            else:
                self.routine_breaks.discard(name)
            self.update_trace()
        self.broadcast({"type": "breakpoints", "list": self.breakpoint_list()})

    def breakpoint_list(self):
        return {"lines": sorted([f, l] for f, l in self.breakpoints),
                "routines": sorted(self.routine_breaks)}

    def command(self, cmd):
        """pause, continue, step-into, step-over, step-out."""
        with self.lock:
            if cmd == "pause":
                self.pause_req = True
                self.update_trace()
                self.broadcast({"type": "pause-requested"})
                return
            if self.state != "paused":
                return
            self.resume_cmd = cmd
            self.cond.notify_all()

    def on_node(self, node, fr):
        fr.node = node
        loc = node.loc
        if loc is None:
            return
        key = (loc.file, loc.line)
        reason = None
        if self.pause_req:
            reason = "paused"
        elif self.mode == "into":
            if key != self.step_key or len(self.I.frames) != self.step_depth:
                reason = "step"
        elif self.mode == "over":
            depth = len(self.I.frames)
            if depth < self.step_depth or (depth == self.step_depth and key != self.step_key):
                reason = "step"
        elif self.mode == "out":
            if len(self.I.frames) < self.step_depth:
                reason = "step"
        if reason is None and key in self.breakpoints and fr.line != key:
            reason = "breakpoint"
        fr.line = key
        if reason:
            self.pause(node, fr, reason)

    def on_enter(self, fr):
        if fr.routine.name in self.routine_breaks:
            self.pause_req = True
            self.pause_reason = "routine " + fr.routine.name

    def pause(self, node, fr, reason):
        with self.lock:
            if getattr(self, "pause_reason", None) and reason == "paused":
                reason = self.pause_reason
            self.pause_reason = None
            self.pause_req = False
            self.mode = None
            prev = self.state
            self.state = "paused"
            self.pause_info = {"reason": reason, "loc": _loc(node.loc), "op": _node_name(node)}
            self.broadcast({"type": "paused", "reason": reason, "loc": _loc(node.loc),
                            "stack": self.stack()})
            self.resume_cmd = None
            while self.resume_cmd is None:
                self.cond.wait()
            cmd = self.resume_cmd
            self.resume_cmd = None
            if cmd == "reset":
                raise Reset()
            self.state = prev if prev != "paused" else "running"
            self.pause_info = None
            key = (node.loc.file, node.loc.line)
            depth = len(self.I.frames)
            if cmd == "step-into":
                self.mode, self.step_key, self.step_depth = "into", key, depth
            elif cmd == "step-over":
                self.mode, self.step_key, self.step_depth = "over", key, depth
            elif cmd == "step-out":
                self.mode, self.step_key, self.step_depth = "out", key, depth
            else:
                self.mode = None
            self.update_trace()
            self.broadcast({"type": "running"})

    # -------------------------------------------------------- snapshots
    def game_info(self):
        g = self.img.game
        files = []
        for f in g.file_order:
            files.append({"file": f, "lines": g.texts[f].count("\n") + 1})
        routines = sorted(({"name": r.name, "file": r.loc.file, "line": r.loc.line}
                           for r in self.game.routines.values() if r.loc),
                          key=lambda r: r["name"])
        return {"name": g.sources.name, "version": self.img.version, "files": files,
                "zilch": repr(g.zilch),
                "routines": routines, "seed": self.seed, "state": self.state,
                "status": self.status, "warnings": self.img.warnings[:50]}

    def source(self, file):
        return self.img.game.texts.get(file)

    def where(self):
        fr = self.I.frames[-1] if self.I.frames else None
        if fr is None or fr.node is None or fr.node.loc is None:
            return None
        return _loc(fr.node.loc)

    def stack(self):
        frames = list(self.I.frames)
        out = []
        for i, fr in enumerate(frames):
            if i + 1 < len(frames) and frames[i + 1].call_node is not None:
                node = frames[i + 1].call_node
            else:
                node = fr.node
            out.append({"routine": fr.routine.name, "loc": _loc(node.loc) if node is not None else
                        _loc(fr.routine.loc), "def": _loc(fr.routine.loc),
                        "locals": self.frame_locals(fr)})
        return out

    def frame_locals(self, fr):
        out = []
        for i, name in enumerate(fr.routine.locals):
            v = fr.locals[i]
            out.append({"name": name, "value": v, "signed": s16(v), "hint": self.hint(v)})
        if fr.stack:
            out.append({"name": "(stack)", "value": fr.stack[-1], "signed": s16(fr.stack[-1]),
                        "hint": ""})
        return out

    def hint(self, v, kind=None):
        img = self.img
        if kind == "object" or (kind is None and False):
            if 0 < v < len(img.object_names):
                return self.I.obj_name(v) or img.object_names[v].name
        if kind == "object":
            return "" if v == 0 else "?"
        if v in img.routine_by_addr:
            return "routine " + img.routine_by_addr[v].name.name
        s = img.string_at(v)
        if s is not None:
            return '"' + (s[:40] + "..." if len(s) > 40 else s).replace("\n", " ") + '"'
        if v in img.word_by_addr:
            return "word '" + img.word_by_addr[v].text + "'"
        return ""

    def snapshot(self):
        img, I = self.img, self.I
        globs = []
        for num in sorted(img.global_names):
            name = img.global_names[num]
            v = I.rw(img.globals_addr + 2 * (num - 16))
            kind = "object" if name in self.object_globals else None
            hint = self.hint(v, kind) if kind == "object" else self.hint(v)
            globs.append({"name": name.name, "value": v, "signed": s16(v), "hint": hint,
                          "kind": kind or ""})
        here = self.here()
        return {"state": self.state, "turn": self.turn, "status": self.status,
                "here": here, "here_name": I.obj_name(here) if here else "",
                "globals": globs, "stack": self.stack() if self.state == "paused" else
                self.stack_brief(), "pause": self.pause_info, "error": self.error}

    def stack_brief(self):
        """The call stack while waiting for input."""
        return self.stack()

    def find_object_globals(self):
        """Globals used where an object is expected (MOVE ,X ...), or set to an object."""
        out = set()
        img = self.img
        for name, (value, loc) in img.game.globals.items():
            if isinstance(value, Atom) and value in img.objects:
                out.add(name)
        seen = set()

        def walk(n):
            if id(n) in seen:
                return
            seen.add(id(n))
            if isinstance(n, Op) and n.name in OBJECT_OPS and n.args:
                for a in n.args[:2 if n.name in ("MOVE", "IN?") else 1]:
                    if isinstance(a, Global):
                        out.add(self._global_atom(a))
            for c in n.children():
                if c is not None:
                    walk(c)

        for r in self.game.routines.values():
            for b in r.body:
                walk(b)
        out.discard(None)
        return out

    def _global_atom(self, g):
        num = 16 + (g.a - self.img.globals_addr) // 2
        return self.img.global_names.get(num)

    # -------------------------------------------------------- objects
    def objects(self):
        I, img = self.I, self.img
        out = []
        for n in range(1, len(img.object_names)):
            od = img.game.objects[img.object_names[n]]
            out.append({"n": n, "atom": img.object_names[n].name, "name": I.obj_name(n),
                        "parent": I.orel(n, 0), "sibling": I.orel(n, 1), "child": I.orel(n, 2),
                        "room": od.is_room})
        return {"objects": out, "here": self.here()}

    def object(self, n):
        I, img = self.I, self.img
        if not 0 < n < len(img.object_names):
            return None
        atom = img.object_names[n]
        od = img.game.objects[atom]
        flag_names = {}
        for f, bit in img.flags.items():
            flag_names.setdefault(bit, []).append(f.name)
        attrs = [{"bit": b, "names": flag_names.get(b, [str(b)])}
                 for b in range(32 if img.version <= 3 else 48) if I.attr(n, b)]
        props = []
        for num, a, size in I.props(n):
            pname = img.prop_names.get(num)
            data = bytes(I.mem[a:a + size])
            props.append({"num": num, "name": pname.name if pname else str(num), "size": size,
                          "bytes": data.hex(" "), "value": self.decode_prop(n, num, a, size)})
        kids = []
        c = I.orel(n, 2)
        while c:
            kids.append({"n": c, "name": I.obj_name(c) or img.object_names[c].name})
            c = I.orel(c, 1)
        p = I.orel(n, 0)
        return {"n": n, "atom": atom.name, "name": I.obj_name(n), "room": od.is_room,
                "def": _loc(od.loc), "attrs": attrs, "props": props, "children": kids,
                "parent": {"n": p, "name": (I.obj_name(p) or img.object_names[p].name) if p else ""}}

    def decode_prop(self, o, num, a, size):
        I, img = self.I, self.img
        pname = img.prop_names.get(num)
        n = pname.name if pname else ""
        if pname in img.game.directions:
            ex = self.decode_exit(a, size)
            return ex["text"]
        if n == "SYNONYM":
            return " ".join(self._word(I.rw(a + i)) for i in range(0, size, 2))
        if n == "ADJECTIVE" and img.version <= 3:
            inv = {v: k for k, v in img.adjs.items()}
            return " ".join(img.words[inv[I.mem[a + i]]].text if I.mem[a + i] in inv else "?"
                            for i in range(size))
        if n == "GLOBAL":
            step = 1 if img.version <= 3 else 2
            return ", ".join(self._objname(I.mem[a + i] if step == 1 else I.rw(a + i))
                             for i in range(0, size, step))
        if size == 1:
            return str(I.mem[a])
        if size == 2:
            v = I.rw(a)
            h = self.hint(v)
            return f"{s16(v)}" + (f"  {h}" if h else "")
        return ""

    def _word(self, a):
        w = self.img.word_by_addr.get(a)
        return w.text if w else "?"

    def _objname(self, n):
        if not 0 < n < len(self.img.object_names):
            return str(n)
        return self.I.obj_name(n) or self.img.object_names[n].name

    def decode_exit(self, a, size):
        """An exit property -> {kind, to, text}."""
        I, img = self.I, self.img
        c = img.consts
        sizes = {}
        for k in ("UEXIT", "NEXIT", "FEXIT", "CEXIT", "DEXIT"):
            v = c.get(Atom(k))
            if v is not None:
                sizes[v] = k
        if not sizes:
            sizes = {1: "UEXIT", 2: "NEXIT", 3: "FEXIT", 4: "CEXIT", 5: "DEXIT"}
        kind = sizes.get(size, "?")
        v3 = img.version <= 3
        obj = (lambda off: I.mem[a + off]) if v3 else (lambda off: I.rw(a + off))
        if kind == "UEXIT":
            t = obj(0)
            return {"kind": "always", "to": t, "text": "to " + self._objname(t)}
        if kind == "NEXIT":
            s = img.string_at(I.rw(a)) or ""
            return {"kind": "never", "to": 0, "text": 'blocked: "%s"' % s[:60]}
        if kind == "FEXIT":
            r = img.routine_by_addr.get(I.rw(a))
            return {"kind": "routine", "to": 0, "text": "per " + (r.name.name if r else "?")}
        if kind == "CEXIT":
            t = obj(0)
            flag = I.mem[a + (1 if v3 else 2)]
            fname = img.global_names.get(flag)
            fval = I.rw(img.globals_addr + 2 * (flag - 16)) if flag >= 16 else 0
            return {"kind": "if-flag", "to": t, "cond": fname.name if fname else str(flag),
                    "open": bool(fval),
                    "text": "to %s if %s (now %s)" % (self._objname(t), fname.name if fname else flag,
                                                      "true" if fval else "false")}
        if kind == "DEXIT":
            t = obj(0)
            door = obj(1 if v3 else 2)
            openbit = img.flags.get(Atom("OPENBIT"))
            is_open = bool(openbit is not None and I.attr(door, openbit))
            return {"kind": "if-door", "to": t, "cond": self._objname(door), "open": is_open,
                    "text": "to %s if %s is open (now %s)" % (self._objname(t), self._objname(door),
                                                             "open" if is_open else "closed")}
        return {"kind": "?", "to": 0, "text": "?"}

    # -------------------------------------------------------- map
    def rooms(self):
        img = self.img
        return [img.objects[name] for name, od in img.game.objects.items() if od.is_room]

    def room_exits(self, r):
        I, img = self.I, self.img
        out = []
        for num, a, size in I.props(r):
            pname = img.prop_names.get(num)
            if pname not in img.game.directions:
                continue
            ex = self.decode_exit(a, size)
            ex["dir"] = DIR_NAMES.get(pname.name, pname.name.lower())
            out.append(ex)
        return out

    def map(self):
        rooms = self.rooms()
        room_set = set(rooms)
        if self._map_layout is None:
            self._map_layout = self.layout(rooms, room_set)
        pos = self._map_layout
        data = {"rooms": [], "edges": [], "here": self.here(), "visited": self.visited,
                "turn": self.turn}
        for r in rooms:
            x, y = pos.get(r, (0, 0))
            exits = self.room_exits(r)
            data["rooms"].append({"id": r, "name": self._objname(r), "x": x, "y": y,
                                  "visited": r in self.visited,
                                  "exits": [{k: e[k] for k in ("dir", "kind", "to", "text")}
                                            for e in exits]})
            for e in exits:
                if e["to"] in room_set and e["to"] != r:
                    data["edges"].append({"a": r, "b": e["to"], "dir": e["dir"], "kind": e["kind"],
                                          "open": e.get("open", True), "cond": e.get("cond", "")})
        seen = {(e["a"], e["b"]) for e in data["edges"]}
        for a, cmd, b in self.transitions:
            if a in room_set and b in room_set and (a, b) not in seen:
                seen.add((a, b))
                data["edges"].append({"a": a, "b": b, "dir": cmd, "kind": "walked",
                                      "open": True, "cond": ""})
        data["walked"] = [[a, b] for a, _, b in self.transitions]
        return data

    def layout(self, rooms, room_set):
        """Place every room on a grid by compass direction (zmap_pdf's layout)."""
        try:
            import zmap_pdf
        except ImportError:
            return {r: (i % 12, i // 12) for i, r in enumerate(rooms)}
        data = {"rooms": {}}
        for r in rooms:
            exits = {}
            for e in self.room_exits(r):
                if e["to"] in room_set and e["to"] != r and e["kind"] in ("always", "if-flag",
                                                                           "if-door"):
                    exits.setdefault(e["dir"], str(e["to"]))
            data["rooms"][str(r)] = {"name": self._objname(r), "exits": exits}
        gm = zmap_pdf.GameMap(data)
        # Lay out from the starting room, so the area the player sees first is the
        # most faithful to the compass.
        start = str(self.here() or (rooms[0] if rooms else ""))
        nbrs = {r: [] for r in gm.rooms}
        for a, cmd, b in gm.edges:
            v = zmap_pdf.VEC.get(cmd)
            nbrs[a].append((b, v))
            nbrs[b].append((a, (-v[0], -v[1]) if v else None))
        pos = gm.build(start, nbrs) if start in gm.rooms else None
        if pos is None:
            gm.layout()
            pos = gm.pos
        minx = min(p[0] for p in pos.values())
        miny = min(p[1] for p in pos.values())
        return {int(k): (x - minx, y - miny) for k, (x, y) in pos.items()}


def _loc(loc):
    if loc is None:
        return None
    return {"file": loc.file, "line": loc.line}


def _node_name(node):
    return getattr(node, "name", None) or type(node).__name__
