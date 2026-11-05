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
import zlib

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
                self.call(self.start, [])
                return
            except Restart:
                self.mem[:] = self.initial
                continue
            except Quit:
                return

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
        """[(number, data address, size)] in table order."""
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

@op("MOVE")
def _move(I, o, dest):
    I.move(o, dest)
    return 1


@op("REMOVE")
def _remove(I, o):
    I.remove(o)
    return 1


@op("LOC")
def _loc(I, o):
    return I.orel(o, 0)


@op("FIRST?")
def _first(I, o):
    return I.orel(o, 2)


@op("NEXT?")
def _next(I, o):
    return I.orel(o, 1)


@op("IN?")
def _in(I, o, p):
    return 1 if I.orel(o, 0) == p else 0


@op("FSET?")
def _fsetp(I, o, f):
    return I.attr(o, f)


@op("FSET")
def _fset(I, o, f):
    I.set_attr(o, f, True)
    return 1


@op("FCLEAR")
def _fclear(I, o, f):
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


@op("SPLIT SCREEN HLIGHT CURSET CURGET ERASE CLEAR BUFOUT DIRIN SOUND COLOR FONT DISPLAY "
    "DCLEAR MARGIN WINPOS WINSIZE WINATTR WINGET WINPUT SCROLL MOUSE-LIMIT PICINF MENU "
    "PRINTF")
def _screen(I, *a):
    return 1


@op("DIROUT")
def _dirout(I, n, *a):
    return 1


@op("INPUT", "io")
def _input(I, *a):
    c = I.io.read_char()
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
