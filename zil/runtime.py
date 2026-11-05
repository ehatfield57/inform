"""Run a compiled ZIL game.

    from zil import open_game
    game = open_game("sources/zork1-r119.zip", seed=1)
    game.run(io)

The data (objects, globals, tables, dictionary) lives in `mem`, laid out like
a real Z-machine game. Routines run as trees from compiler.py. A debugger can
watch every step through `trace` / `on_node`.
"""

import base64
import json
import random
import sys
import zlib

# Each ZIL call is several Python calls deep, and games recurse (FINISH asks again
# by calling itself), so allow far more than Python's default 1000.
sys.setrecursionlimit(max(sys.getrecursionlimit(), 100000))

from .compiler import (Compiler, RoutineReturn, BlockReturn, BlockAgain, Routine)
from .image import build, Builder, STRING_BASE, ROUTINE_BASE
from .loader import load
from . import ztext


class ZilError(Exception):
    pass


class Quit(Exception):
    pass


class Restart(Exception):
    pass


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


class Frame:
    __slots__ = ("routine", "locals", "assigned", "stack", "node", "caller", "call_node", "line")

    def __init__(self, routine, caller, call_node):
        self.line = None             # last source line run here (for breakpoints)
        self.routine = routine
        self.locals = [0] * len(routine.locals)
        self.assigned = [False] * len(routine.locals)
        self.stack = []
        self.node = None
        self.caller = caller
        self.call_node = call_node


class IO:
    """What the interpreter needs from the outside world. Subclass this."""

    def write(self, text):
        raise NotImplementedError

    def read_line(self):
        raise NotImplementedError

    def read_char(self):
        line = self.read_line()
        return line[0] if line else "\n"

    def status(self, left, right):
        pass

    def ask_filename(self, purpose, default):
        return default

    # The upper window (version 4 on): a grid of characters the game draws itself,
    # usually a status line. The lower window is the scrolling text above.
    width = 80
    height = 24

    def split(self, lines):
        pass

    def erase_upper(self):
        pass

    def upper_write(self, text):
        pass

    def set_cursor(self, row, col):
        pass

    def get_cursor(self):
        return (1, 1)

    def erase_line(self):
        pass

    def show_upper(self):
        """Called before input: show the upper window if it changed."""
        pass

    def key_ready(self, seconds):
        """For timed input: True if a key is pressed within `seconds`."""
        return False


class Interp:
    def __init__(self, img, routines, seed=None):
        self.img = img
        self.version = img.version
        self.routines = routines             # packed -> Routine
        self.initial = bytes(img.mem)
        self.mem = bytearray(img.mem)
        self.seed = seed
        self.rng = random.Random(seed)
        self.trace = False                    # set by a debugger
        self.frames = []
        self.io = None
        self.globals_addr = img.globals_addr
        self.obj_entries = img.obj_entries
        self.esize = img.obj_esize
        self.objtab = img.obj_entries - 2 * (31 if self.version <= 3 else 63)
        self.transcript = []                  # every piece of output, for UIs
        self.on_output = None
        self.on_read = None                   # called before each input (for UIs)
        self.on_move = None
        self.save_slots = {}
        by_name = {r.name: r for r in routines.values()}
        start = img.game.zstart.name
        if start not in by_name:
            raise ZilError(f"no routine {start} to start the game")
        self.start = by_name[start]
        self.by_name = by_name

    # ------------------------------------------------------------ running
    def run(self, io):
        self.io = io
        while True:
            try:
                self.frames = []
                self.reset_screen()
                self.call(self.start, [])
                return
            except Restart:
                self.mem[:] = self.initial
                continue
            except Quit:
                return

    def reset_screen(self):
        """Screen state and the header fields an interpreter fills in (as zplay.py does)."""
        self.window = 0
        self.mem_streams = []
        self.stream1 = True
        self.font = 1
        m, v, io = self.mem, self.version, self.io
        if v <= 3:
            m[1] = (m[1] & ~0x70 & 0xFF) | 0x20     # status line, split screen available
        else:
            m[1] = 0x1C                              # bold, italic, fixed pitch available
        m[0x11] &= ~(0x08 | 0x20 | 0x80) & 0xFF      # no pictures, mouse or sound
        m[0x1E] = 6
        m[0x1F] = ord("A")
        if v >= 4:
            m[0x20] = min(io.height, 255)
            m[0x21] = min(io.width, 255)
        if v >= 5:
            self.ww(0x22, io.width)
            self.ww(0x24, io.height)
            m[0x26] = m[0x27] = 1
            m[0x2C], m[0x2D] = 2, 9
        m[0x32], m[0x33] = 1, 0
        io.split(0)

    def call(self, r, args, call_node=None):
        if not isinstance(r, Routine):
            r = self.routines.get(r)
            if r is None:
                return 0
        if len(args) > len(r.locals):
            args = args[:len(r.locals)]     # the Z-machine drops extra arguments
        fr = Frame(r, self.frames[-1] if self.frames else None, call_node)
        loc = fr.locals
        for i, v in enumerate(args):
            loc[i] = v & 0xFFFF
            fr.assigned[i] = True
        self.frames.append(fr)
        try:
            for i in range(len(args), len(loc)):
                d = r.defaults[i] if i < len(r.defaults) else None
                if d is not None:
                    loc[i] = d.ev(self, fr) & 0xFFFF
            if self.trace:
                self.on_enter(fr)
            v = 0
            while True:
                try:
                    for b in r.body:
                        v = b.ev(self, fr)
                    break
                except BlockAgain as a:
                    if a.act is None or a.act is r.act:
                        continue
                    raise
            return v & 0xFFFF
        except RoutineReturn as rr:
            return rr.value
        except BlockReturn as br:
            if br.act is None or br.act is r.act:
                return br.value
            raise
        except (BlockAgain, Quit, Restart):
            raise
        except Exception as e:
            # Record the ZIL call stack on the way out, for the error message.
            if not hasattr(e, "zil_stack"):
                e.zil_stack = []
            e.zil_stack.append((r.name, call_node.loc if call_node is not None else None))
            raise
        finally:
            self.frames.pop()
            if self.trace:
                self.on_leave(fr)

    def apply(self, packed, *args):
        if packed == 0:
            return 0
        r = self.routines.get(packed)
        if r is None:
            raise ZilError(f"APPLY of {packed:#x}, which isn't a routine")
        return self.call(r, list(args))

    # debugger hooks (replaced by a debugger)
    def on_node(self, node, fr):
        fr.node = node

    def on_enter(self, fr):
        pass

    def on_leave(self, fr):
        pass

    # ------------------------------------------------------------ output
    def out(self, s):
        if not s:
            return
        if self.mem_streams:
            # <DIROUT 3 table>: text goes into the table (games measure text this way)
            t = self.mem_streams[-1]
            for ch in s:
                self.mem[t[0] + 2 + t[1]] = self.to_zscii(ch) if ch != "\n" else 13
                t[1] += 1
            return
        if self.window == 1:
            self.io.upper_write(s)
            return
        if not self.stream1:
            return
        self.transcript.append(s)
        if self.on_output:
            self.on_output(s)
        self.io.write(s)

    # ------------------------------------------------------------ memory
    def rw(self, a):
        return (self.mem[a] << 8) | self.mem[a + 1]

    def ww(self, a, v):
        self.mem[a] = (v >> 8) & 0xFF
        self.mem[a + 1] = v & 0xFF

    def global_value(self, name):
        n = self.img.global_num[name]
        return self.rw(self.globals_addr + 2 * (n - 16))

    def read_var(self, n, fr=None):
        fr = fr or self.frames[-1]
        if n == 0:
            return fr.stack.pop() if fr.stack else 0
        if n < 16:
            return fr.locals[n - 1]
        return self.rw(self.globals_addr + 2 * (n - 16))

    def write_var(self, n, v, fr=None):
        fr = fr or self.frames[-1]
        v &= 0xFFFF
        if n == 0:
            fr.stack.append(v)
        elif n < 16:
            fr.locals[n - 1] = v
        else:
            self.ww(self.globals_addr + 2 * (n - 16), v)

    # ------------------------------------------------------------ objects
    def oaddr(self, o):
        if o == 0 or o >= len(self.img.object_names):
            raise ZilError(f"bad object number {o}")
        return self.obj_entries + (o - 1) * self.esize

    def orel(self, o, which):          # 0 parent, 1 sibling, 2 child
        a = self.oaddr(o)
        if self.version <= 3:
            return self.mem[a + 4 + which]
        return self.rw(a + 6 + 2 * which)

    def set_orel(self, o, which, v):
        a = self.oaddr(o)
        if self.version <= 3:
            self.mem[a + 4 + which] = v
        else:
            self.ww(a + 6 + 2 * which, v)

    def remove(self, o):
        p = self.orel(o, 0)
        if p == 0:
            return
        c = self.orel(p, 2)
        if c == o:
            self.set_orel(p, 2, self.orel(o, 1))
        else:
            while c:
                nxt = self.orel(c, 1)
                if nxt == o:
                    self.set_orel(c, 1, self.orel(o, 1))
                    break
                c = nxt
        self.set_orel(o, 0, 0)
        self.set_orel(o, 1, 0)

    def move(self, o, dest):
        self.remove(o)
        self.set_orel(o, 1, self.orel(dest, 2))
        self.set_orel(dest, 2, o)
        self.set_orel(o, 0, dest)
        if self.on_move:
            self.on_move(o, dest)

    def attr(self, o, n):
        a = self.oaddr(o) + n // 8
        return 1 if self.mem[a] & (0x80 >> (n % 8)) else 0

    def set_attr(self, o, n, on):
        a = self.oaddr(o) + n // 8
        if on:
            self.mem[a] |= 0x80 >> (n % 8)
        else:
            self.mem[a] &= ~(0x80 >> (n % 8)) & 0xFF

    def prop_table(self, o):
        return self.rw(self.oaddr(o) + self.esize - 2)

    def obj_name(self, o):
        if o == 0:
            return ""
        pt = self.prop_table(o)
        if self.mem[pt] == 0:
            return ""
        return ztext.decode(self.mem, pt + 1)[0]

    def props(self, o):
        """[(number, data address, size)] in table order. Object 0 has none."""
        if o == 0:
            return []
        pt = self.prop_table(o)
        a = pt + 1 + 2 * self.mem[pt]
        out = []
        m = self.mem
        while m[a]:
            b = m[a]
            if self.version <= 3:
                num, size, a = b & 31, (b >> 5) + 1, a + 1
            elif b & 0x80:
                num, size, a = b & 63, (m[a + 1] & 63) or 64, a + 2
            else:
                num, size, a = b & 63, 2 if b & 0x40 else 1, a + 1
            out.append((num, a, size))
            a += size
        return out

    def find_prop(self, o, p):
        for num, a, size in self.props(o):
            if num == p:
                return a, size
            if num < p:
                break
        return 0, 0

    def prop_size_at(self, a):
        if a == 0:
            return 0
        b = self.mem[a - 1]
        if self.version <= 3:
            return (b >> 5) + 1
        if b & 0x80:
            return (b & 63) or 64
        return 2 if b & 0x40 else 1

    # ------------------------------------------------------------ text
    def decode_at(self, a):
        return ztext.decode(self.mem, a)[0]

    def string_at(self, packed):
        s = self.img.string_at(packed)
        if s is None:
            raise ZilError(f"PRINT of {packed:#x}, which isn't a string")
        return s

    # ------------------------------------------------------------ input
    def status_line(self):
        if self.version > 3:
            return
        g = lambda n: self.rw(self.globals_addr + 2 * n)
        left = self.obj_name(g(0)) if g(0) else ""
        a, b = s16(g(1)), s16(g(2))
        if self.mem[1] & 0x02:
            right = "Time: %d:%02d %s" % ((a % 12) or 12, b, "pm" if a >= 12 else "am")
        else:
            right = "Score: %d  Moves: %d" % (a, b)
        self.io.status(left, right)

    def read(self, text, parse):
        self.status_line()
        if self.version >= 4:
            self.io.show_upper()
        if self.on_read:
            self.on_read()
        line = self.io.read_line()
        self.transcript.append(line + "\n")
        m = self.mem
        chars = [self.to_zscii(c) for c in line.lower()]
        if self.version <= 4:
            chars = chars[: max(m[text] - 1, 0)]
            for i, z in enumerate(chars):
                m[text + 1 + i] = z
            m[text + 1 + len(chars)] = 0
            start = text + 1
        else:
            chars = chars[: m[text]]
            for i, z in enumerate(chars):
                m[text + 2 + i] = z
            m[text + 1] = len(chars)
            start = text + 2
        if parse:
            self.tokenise(chars, start - text, parse)
        return 13

    def to_zscii(self, ch):
        o = ord(ch)
        return o if 32 <= o < 127 else 32

    def tokenise(self, chars, offset, parse):
        m = self.mem
        seps = set(m[self.img.dict_addr + 1: self.img.dict_addr + 1 + m[self.img.dict_addr]])
        words = []
        i, n = 0, len(chars)
        while i < n:
            c = chars[i]
            if c == 32:
                i += 1
            elif c in seps:
                words.append((i, 1))
                i += 1
            else:
                j = i
                while j < n and chars[j] != 32 and chars[j] not in seps:
                    j += 1
                words.append((i, j - i))
                i = j
        words = words[: m[parse]]
        m[parse + 1] = len(words)
        for k, (off, ln) in enumerate(words):
            text = "".join(chr(c) for c in chars[off: off + ln])
            w = self.img.words.get(ztext.encode_word(text, self.version))
            e = parse + 2 + 4 * k
            self.ww(e, w.addr if w else 0)
            m[e + 2] = ln
            m[e + 3] = off + offset

    # ------------------------------------------------------------ save / restore
    def save_state(self):
        return {"format": "zilplay-1", "game": self.img.game.sources.name,
                "memory": base64.b64encode(zlib.compress(bytes(self.mem))).decode("ascii")}

    def load_state(self, state):
        if state.get("format") != "zilplay-1" or state.get("game") != self.img.game.sources.name:
            raise ValueError("that save file is from a different game")
        mem = zlib.decompress(base64.b64decode(state["memory"]))
        if len(mem) != len(self.mem):
            raise ValueError("that save file doesn't fit this game")
        self.mem[:] = mem

    def do_save(self):
        name = self.io.ask_filename("Save", self.img.game.sources.name + ".zsav")
        if not name:
            return 0
        try:
            with open(name, "w") as fh:
                json.dump(self.save_state(), fh)
            return 1
        except OSError as e:
            self.out("[%s]\n" % e)
            return 0

    def do_restore(self):
        name = self.io.ask_filename("Restore", self.img.game.sources.name + ".zsav")
        if not name:
            return 0
        try:
            with open(name) as fh:
                self.load_state(json.load(fh))
            return 1
        except (OSError, ValueError, KeyError) as e:
            self.out("[Could not restore: %s]\n" % e)
            return 0


# ---------------------------------------------------------------- built-in operations
# Each takes the interpreter and evaluated arguments and returns a 16-bit value.

B = {}


def op(names, kind="plain"):
    def deco(f):
        for n in names.split():
            B[n] = (kind, f)
        return f
    return deco


def _w(x):
    return x & 0xFFFF


@op("+ ADD")
def _add(I, *a):
    v = 0
    for x in a:
        v += s16(x)
    return _w(v)


@op("- SUB")
def _sub(I, a, *r):
    if not r:
        return _w(-s16(a))
    v = s16(a)
    for x in r:
        v -= s16(x)
    return _w(v)


@op("* MUL")
def _mul(I, *a):
    v = 1
    for x in a:
        v *= s16(x)
    return _w(v)


@op("/ DIV")
def _div(I, a, *r):
    v = s16(a)
    for x in r:
        d = s16(x)
        if d == 0:
            raise ZilError("division by zero")
        q = abs(v) // abs(d)
        v = q if (v < 0) == (d < 0) else -q
    return _w(v)


@op("MOD")
def _mod(I, a, b):
    a, b = s16(a), s16(b)
    if b == 0:
        raise ZilError("division by zero")
    r = abs(a) % abs(b)
    return _w(-r if a < 0 else r)


@op("MIN")
def _min(I, *a):
    return _w(min(s16(x) for x in a))


@op("MAX")
def _max(I, *a):
    return _w(max(s16(x) for x in a))


@op("ABS")
def _abs(I, a):
    return _w(abs(s16(a)))


@op("RANDOM")
def _random(I, r):
    r = s16(r)
    if r > 0:
        return I.rng.randint(1, r)
    I.rng.seed(-r if r < 0 else None)
    return 0


@op("EQUAL? ==? =?")
def _equal(I, a, *rest):
    return 1 if a in rest else 0


@op("N==? N=?")
def _nequal(I, a, *rest):
    return 0 if a in rest else 1


@op("L? LESS?")
def _less(I, a, b):
    return 1 if s16(a) < s16(b) else 0


@op("G? GRTR?")
def _greater(I, a, b):
    return 1 if s16(a) > s16(b) else 0


@op("L=?")
def _le(I, a, b):
    return 1 if s16(a) <= s16(b) else 0


@op("G=?")
def _ge(I, a, b):
    return 1 if s16(a) >= s16(b) else 0


@op("ZERO? 0? NOT F?")
def _zero(I, a):
    return 1 if a == 0 else 0


@op("1?")
def _one(I, a):
    return 1 if a == 1 else 0


@op("T?")
def _tp(I, a):
    return 1 if a else 0


@op("BAND ANDB")
def _band(I, *a):
    v = 0xFFFF
    for x in a:
        v &= x
    return v


@op("BOR ORB")
def _bor(I, *a):
    v = 0
    for x in a:
        v |= x
    return v


@op("BCOM")
def _bcom(I, a):
    return ~a & 0xFFFF


@op("BTST")
def _btst(I, a, b):
    return 1 if a & b == b else 0


@op("SHIFT LSH")
def _shift(I, a, n):
    n = s16(n)
    return _w(a << n if n >= 0 else a >> -n)


@op("ASH ASHIFT")
def _ash(I, a, n):
    n = s16(n)
    return _w(s16(a) << n if n >= 0 else s16(a) >> -n)


# variables by name ------------------------------------------------------

def _getv(I, fr, var):
    from .compiler import Local
    if isinstance(var, Local):
        return fr.locals[var.i]
    return I.rw(var.a)


def _setv(I, fr, var, v):
    from .compiler import Local
    v &= 0xFFFF
    if isinstance(var, Local):
        fr.locals[var.i] = v
    else:
        I.ww(var.a, v)
    return v


@op("INC", "var")
def _inc(I, fr, var):
    return _setv(I, fr, var, _getv(I, fr, var) + 1)


@op("DEC", "var")
def _dec(I, fr, var):
    return _setv(I, fr, var, _getv(I, fr, var) - 1)


@op("IGRTR?", "var")
def _igrtr(I, fr, var, n):
    v = _setv(I, fr, var, _getv(I, fr, var) + 1)
    return 1 if s16(v) > s16(n) else 0


@op("DLESS?", "var")
def _dless(I, fr, var, n):
    v = _setv(I, fr, var, _getv(I, fr, var) - 1)
    return 1 if s16(v) < s16(n) else 0


@op("VALUE")
def _value(I, n):
    return I.read_var(n)


@op("PUSH")
def _push(I, v):
    I.frames[-1].stack.append(v)
    return v


@op("POP")
def _pop(I, *a):
    st = I.frames[-1].stack
    return st.pop() if st else 0


# objects ----------------------------------------------------------------

# Object 0 means "no object": questions about it answer 0 and changes do nothing,
# as most Z-machine interpreters allow (games do sometimes ask, e.g. an object left
# out of a release but still named in a GLOBAL list).

@op("MOVE")
def _move(I, o, dest):
    if o and dest:
        I.move(o, dest)
    return 1


@op("REMOVE")
def _remove(I, o):
    if o:
        I.remove(o)
    return 1


@op("LOC")
def _loc(I, o):
    return I.orel(o, 0) if o else 0


@op("FIRST?")
def _first(I, o):
    return I.orel(o, 2) if o else 0


@op("NEXT?")
def _next(I, o):
    return I.orel(o, 1) if o else 0


@op("IN?")
def _in(I, o, p):
    return 1 if o and I.orel(o, 0) == p else 0


@op("FSET?")
def _fsetp(I, o, f):
    return I.attr(o, f) if o else 0


@op("FSET")
def _fset(I, o, f):
    if o:
        I.set_attr(o, f, True)
    return 1


@op("FCLEAR")
def _fclear(I, o, f):
    if o:
        I.set_attr(o, f, False)
    return 1


@op("GETP")
def _getp(I, o, p):
    a, size = I.find_prop(o, p)
    if a == 0:
        return I.rw(I.objtab + 2 * (p - 1))
    if size == 1:
        return I.mem[a]
    return I.rw(a)


@op("PUTP")
def _putp(I, o, p, v):
    a, size = I.find_prop(o, p)
    if a == 0:
        raise ZilError(f"PUTP: object {I.obj_name(o)!r} has no property {p}")
    if size == 1:
        I.mem[a] = v & 0xFF
    else:
        I.ww(a, v)
    return 1


@op("GETPT")
def _getpt(I, o, p):
    return I.find_prop(o, p)[0]


@op("PTSIZE")
def _ptsize(I, a):
    return I.prop_size_at(a)


@op("NEXTP")
def _nextp(I, o, p):
    ps = I.props(o)
    if p == 0:
        return ps[0][0] if ps else 0
    for i, (num, _, _) in enumerate(ps):
        if num == p:
            return ps[i + 1][0] if i + 1 < len(ps) else 0
    raise ZilError(f"NEXTP: no property {p}")


# tables -----------------------------------------------------------------

@op("GET NTH")
def _get(I, t, i):
    return I.rw((t + 2 * s16(i)) & 0xFFFF)


@op("PUT")
def _put(I, t, i, v):
    I.ww((t + 2 * s16(i)) & 0xFFFF, v)
    return 1     # store operations count as true when their value is used


@op("GETB")
def _getb(I, t, i):
    return I.mem[(t + s16(i)) & 0xFFFF]


@op("PUTB")
def _putb(I, t, i, v):
    I.mem[(t + s16(i)) & 0xFFFF] = v & 0xFF
    return 1


@op("REST")
def _rest(I, t, n=1):
    return _w(t + s16(n))


@op("BACK")
def _back(I, t, n=1):
    return _w(t - s16(n))


@op("COPYT")
def _copyt(I, src, dst, n):
    n = s16(n)
    if dst == 0:
        for i in range(abs(n)):
            I.mem[src + i] = 0
    elif n < 0 or dst < src:
        for i in range(abs(n)):
            I.mem[dst + i] = I.mem[src + i]
    else:
        for i in reversed(range(n)):
            I.mem[dst + i] = I.mem[src + i]
    return 1


@op("INTBL?")
def _intbl(I, v, t, n, form=0x82):
    size = form & 0x7F if form else 2
    for i in range(n):
        a = t + i * size
        x = I.rw(a) if form & 0x80 or not form else I.mem[a]
        if x == v:
            return a
    return 0


# calls ------------------------------------------------------------------

@op("APPLY CALL")
def _apply(I, r, *args):
    return I.apply(r, *args)


# output -----------------------------------------------------------------

@op("PRINT")
def _print(I, p):
    I.out(I.string_at(p))
    return 1


@op("PRINTD")
def _printd(I, o):
    I.out(I.obj_name(o))
    return 1


@op("PRINTN")
def _printn(I, n):
    I.out(str(s16(n)))
    return 1


@op("PRINTC")
def _printc(I, c):
    I.out("\n" if c == 13 else chr(c))
    return 1


@op("PRINTB")
def _printb(I, a):
    I.out(I.decode_at(a))
    return 1


@op("CRLF")
def _crlf(I):
    I.out("\n")
    return 1


# input and the system -------------------------------------------------------

@op("READ", "io")
def _read(I, text, parse=0, *more):
    return I.read(text, parse)


@op("QUIT")
def _quit(I):
    raise Quit()


@op("RESTART")
def _restart(I):
    raise Restart()


@op("SAVE")
def _save(I, *a):
    return I.do_save()


@op("RESTORE")
def _restore(I, *a):
    return I.do_restore()


@op("VERIFY")
def _verify(I):
    return 1


@op("USL")
def _usl(I):
    I.status_line()
    return 1


# the screen (version 4 on) --------------------------------------------------

@op("SPLIT")
def _split(I, n):
    I.io.split(n)
    return 1


@op("SCREEN")
def _screen_(I, w):
    I.window = w
    if w == 1:
        I.io.set_cursor(1, 1)
    return 1


@op("CLEAR")
def _clear(I, w):
    w = s16(w)
    if w == -1:
        I.io.split(0)
        I.io.erase_upper()
        I.window = 0
    elif w in (-2, 1):
        I.io.erase_upper()
    return 1


@op("ERASE")
def _erase(I, v=1):
    if I.window == 1 and v == 1:
        I.io.erase_line()
    return 1


@op("CURSET")
def _curset(I, line, col=1, *rest):
    if I.window == 1 and s16(line) > 0:
        I.io.set_cursor(line, col)
    return 1


@op("CURGET")
def _curget(I, tbl):
    row, col = I.io.get_cursor() if I.window == 1 else (I.io.height, 1)
    I.ww(tbl, row)
    I.ww(tbl + 2, col)
    return 1


@op("FONT")
def _font(I, f):
    if f == 0:
        return I.font
    if f in (1, 4):
        prev, I.font = I.font, f
        return prev
    return 0


@op("DIROUT")
def _dirout(I, n, table=0, *a):
    n = s16(n)
    if n == 1:
        I.stream1 = True
    elif n == -1:
        I.stream1 = False
    elif n == 2:
        I.mem[0x11] |= 1
    elif n == -2:
        I.mem[0x11] &= 0xFE
    elif n == 3:
        I.mem_streams.append([table, 0])
    elif n == -3 and I.mem_streams:
        t, count = I.mem_streams.pop()
        I.ww(t, count)
    return 1


@op("PRINTT")
def _printt(I, text, width, height=1, skip=0):
    row_, col = I.io.get_cursor()
    for r in range(height):
        row = "".join("\n" if z == 13 else chr(z) for z in I.mem[text: text + width])
        text += width + skip
        if I.window == 1:
            I.io.upper_write(row)
            if r < height - 1:
                row_ += 1
                I.io.set_cursor(row_, col)
        else:
            I.out(row + ("\n" if r < height - 1 else ""))
    return 1


@op("ISAVE IRESTORE")
def _isave(I, *a):
    return 0xFFFF       # -1: undo isn't available (the call stack can't be saved)


@op("HLIGHT BUFOUT DIRIN SOUND COLOR DISPLAY DCLEAR MARGIN WINPOS WINSIZE WINATTR WINGET "
    "WINPUT SCROLL MOUSE-LIMIT PICINF MENU PRINTF")
def _screen(I, *a):
    return 1            # text styles and buffering don't change the text itself


@op("INPUT", "io")
def _input(I, dev=1, time=0, routine=0, *rest):
    I.io.show_upper()
    if time and routine:
        # Timed key read: every time/10 seconds with no key, call the routine; if it
        # returns true, stop waiting (as zplay.py does, capped for scripts).
        for _ in range(2000):
            if I.io.key_ready(time / 10):
                break
            if I.apply(routine):
                return 0
    c = I.io.read_char()
    if c in ("\r", "\n"):
        return 13
    if c in ("\x7f", "\x08"):
        return 8
    if c == "\x1b":
        return 27
    if "\x81" <= c <= "\x84":
        return 129 + ord(c) - 0x81
    return ord(c[0]) if c else 13


@op("ORIGINAL?")
def _original(I):
    return 1


# ---------------------------------------------------------------- opening a game

class OpenGame:
    """A loaded, built and compiled game, ready to run."""

    def __init__(self, path, seed=None, serial=None, zilch=None):
        self.game = load(path, zilch)
        self.img = build(self.game, serial=serial)
        self.builder = self.img.builder
        comp = Compiler(self.img, self.builder, B)
        self.routines = comp.compile_all()
        self.compile_errors = comp.errors
        self.warnings = self.img.warnings
        self.interp = Interp(self.img, self.routines, seed)

    def run(self, io):
        self.interp.run(io)


def open_game(path, seed=None, serial=None, zilch=None):
    return OpenGame(path, seed, serial, zilch)


def describe_error(e):
    """A ZIL-level description of an error raised while running: what failed, where
    in the source, and the chain of routine calls that led there."""
    lines = [f"{type(e).__name__}: {e}"]
    loc = getattr(e, "zil_loc", None)
    if loc is not None:
        lines.append(f"  in <{getattr(e, 'zil_op', '?')} ...> at {loc}")
    for name, call_loc in getattr(e, "zil_stack", []):
        where = f" (called at {call_loc})" if call_loc is not None else ""
        lines.append(f"  in routine {name}{where}")
    return "\n".join(lines)
