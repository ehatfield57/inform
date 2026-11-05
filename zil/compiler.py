"""Turn ZIL routine source into trees of nodes the interpreter can run.

Each node keeps the source location of the form it came from, so the debugger
can show which line is running and stop at breakpoints. Names are resolved
here once: .X becomes a local slot, ,X a global variable or a constant (object
number, routine address, flag number, ...).
"""

from .reader import Atom, Form, MList, Vector, Hashed, Char, Segment, mdl_repr
from .mdl import MFalse
from .image import TABLE_FORMS, zil_text, BuildError

A = Atom
GVAL, LVAL, QUOTE = A("GVAL"), A("LVAL"), A("QUOTE")


class CompileError(Exception):
    pass


# ---------------------------------------------------------------- nodes

class Node:
    __slots__ = ("loc",)
    stmt = False          # True for nodes the debugger can stop at

    def children(self):
        return ()


class Const(Node):
    __slots__ = ("v",)

    def __init__(self, v, loc=None):
        self.v, self.loc = v & 0xFFFF, loc

    def ev(self, I, fr):
        return self.v


class Local(Node):
    __slots__ = ("i", "name")

    def __init__(self, i, name, loc=None):
        self.i, self.name, self.loc = i, name, loc

    def ev(self, I, fr):
        return fr.locals[self.i]


class Global(Node):
    __slots__ = ("a", "name")

    def __init__(self, a, name, loc=None):
        self.a, self.name, self.loc = a, name, loc

    def ev(self, I, fr):
        m = I.mem
        return (m[self.a] << 8) | m[self.a + 1]


class Stmt(Node):
    """A node the debugger can stop at."""
    __slots__ = ()
    stmt = True


class SetVar(Stmt):
    __slots__ = ("var", "val")

    def __init__(self, var, val, loc):
        self.var, self.val, self.loc = var, val, loc

    def children(self):
        return (self.val,)

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        v = self.val.ev(I, fr) & 0xFFFF
        var = self.var
        if isinstance(var, Local):
            fr.locals[var.i] = v
        else:
            I.mem[var.a] = v >> 8
            I.mem[var.a + 1] = v & 0xFF
        return v


class Op(Stmt):
    """A built-in operation whose arguments are all evaluated."""
    __slots__ = ("fn", "args", "name")

    def __init__(self, fn, args, name, loc):
        self.fn, self.args, self.name, self.loc = fn, args, name, loc

    def children(self):
        return self.args

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        args = [a.ev(I, fr) for a in self.args]
        try:
            return self.fn(I, *args)
        except (RoutineReturn, BlockReturn, BlockAgain):
            raise
        except Exception as e:
            if getattr(e, "zil_loc", None) is None:
                e.zil_loc = self.loc
                e.zil_op = self.name
            raise


class IoOp(Op):
    """READ and INPUT: remember the node, so a debugger can show where the game waits."""
    __slots__ = ()

    def ev(self, I, fr):
        fr.node = self
        return Op.ev(self, I, fr)


class VarOp(Stmt):
    """INC, DEC, IGRTR?, DLESS?, VALUE on a named variable."""
    __slots__ = ("fn", "var", "args", "name")

    def __init__(self, fn, var, args, name, loc):
        self.fn, self.var, self.args, self.name, self.loc = fn, var, args, name, loc

    def children(self):
        return self.args

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        return self.fn(I, fr, self.var, *[a.ev(I, fr) for a in self.args])


class Call(Stmt):
    __slots__ = ("target", "args", "name")

    def __init__(self, target, args, name, loc):
        self.target, self.args, self.name, self.loc = target, args, name, loc

    def children(self):
        return self.args

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        return I.call(self.target, [a.ev(I, fr) for a in self.args], self)


class Print(Stmt):
    __slots__ = ("text", "ret")

    def __init__(self, text, ret, loc):
        self.text, self.ret, self.loc = text, ret, loc

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        I.out(self.text)
        if self.ret:
            I.out("\n")
            raise RoutineReturn(1)
        return 1


class Cond(Stmt):
    __slots__ = ("clauses",)

    def __init__(self, clauses, loc):
        self.clauses, self.loc = clauses, loc

    def children(self):
        out = []
        for t, body in self.clauses:
            out.append(t)
            out.extend(body)
        return out

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        for test, body in self.clauses:
            v = test.ev(I, fr)
            if v:
                for b in body:
                    v = b.ev(I, fr)
                return v
        return 0


class And(Stmt):
    __slots__ = ("args",)

    def __init__(self, args, loc):
        self.args, self.loc = args, loc

    def children(self):
        return self.args

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        v = 1
        for a in self.args:
            v = a.ev(I, fr)
            if not v:
                return 0
        return v


class Or(Stmt):
    __slots__ = ("args",)

    def __init__(self, args, loc):
        self.args, self.loc = args, loc

    def children(self):
        return self.args

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        for a in self.args:
            v = a.ev(I, fr)
            if v:
                return v
        return 0


class Block(Stmt):
    """REPEAT (loops), PROG and BIND (run once). RETURN leaves the innermost one."""
    __slots__ = ("body", "act", "inits", "loop", "end")

    def __init__(self, body, act, inits, loop, loc, end=None):
        self.body, self.act, self.inits, self.loop, self.loc = body, act, inits, loop, loc
        self.end = end

    def children(self):
        return [n for _, n in self.inits if n is not None] + list(self.body)

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        for i, init in self.inits:
            fr.locals[i] = init.ev(I, fr) & 0xFFFF if init is not None else 0
        while True:
            try:
                v = 1
                for b in self.body:
                    v = b.ev(I, fr)
                if not self.loop:
                    return v
            except BlockReturn as r:
                if r.act is None or r.act is self.act:
                    return r.value
                raise
            except BlockAgain as a:
                if a.act is None or a.act is self.act:
                    continue
                raise


class Seq(Stmt):
    """Run several expressions; the value is the last one's."""
    __slots__ = ("body",)

    def __init__(self, body, loc):
        self.body, self.loc = body, loc

    def children(self):
        return self.body

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        v = 1
        for b in self.body:
            v = b.ev(I, fr)
        return v


class Broken(Stmt):
    """The body of a routine that couldn't be compiled."""
    __slots__ = ("msg",)

    def __init__(self, msg, loc):
        self.msg, self.loc = msg, loc

    def ev(self, I, fr):
        from .runtime import ZilError
        raise ZilError(f"routine {fr.routine.name} couldn't be compiled: {self.msg}")


class Return(Stmt):
    __slots__ = ("val", "act")

    def __init__(self, val, act, loc):
        self.val, self.act, self.loc = val, act, loc

    def children(self):
        return (self.val,) if self.val else ()

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        v = self.val.ev(I, fr) if self.val is not None else 1
        raise BlockReturn(v, self.act)


class RoutineExit(Stmt):
    """RTRUE, RFALSE, RSTACK: return from the routine itself."""
    __slots__ = ("val", "name")

    def __init__(self, val, name, loc):
        self.val, self.name, self.loc = val, name, loc

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        if self.val is None:   # RSTACK
            raise RoutineReturn(fr.stack.pop() if fr.stack else 0)
        raise RoutineReturn(self.val)


class Again(Stmt):
    __slots__ = ("act",)

    def __init__(self, act, loc):
        self.act, self.loc = act, loc

    def ev(self, I, fr):
        if I.trace:
            I.on_node(self, fr)
        raise BlockAgain(self.act)


class Assigned(Node):
    __slots__ = ("i",)

    def __init__(self, i, loc):
        self.i, self.loc = i, loc

    def ev(self, I, fr):
        return 1 if fr.assigned[self.i] else 0


class BlockReturn(Exception):
    __slots__ = ("value", "act")

    def __init__(self, value, act):
        self.value, self.act = value & 0xFFFF, act


class BlockAgain(Exception):
    def __init__(self, act):
        self.act = act


class RoutineReturn(Exception):
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value & 0xFFFF


# ---------------------------------------------------------------- routines

class Routine:
    def __init__(self, name, packed, loc, end):
        self.name, self.packed, self.loc, self.end = name, packed, loc, end
        self.locals = []        # names
        self.nreq = 0
        self.nargs = 0          # required + optional
        self.defaults = []      # node or None, for each optional/aux local
        self.body = []
        self.act = None

    def __repr__(self):
        return f"<ROUTINE {self.name}>"


class Activation:
    """The name of a REPEAT/PROG/ROUTINE that RETURN and AGAIN can target."""
    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name


class Compiler:
    def __init__(self, img, builder, builtins):
        self.img = img
        self.b = builder
        self.builtins = builtins     # name -> (kind, fn)
        self.errors = []

    def compile_all(self):
        routines = {}
        for name, rd in self.b.g.routines.items():
            r = Routine(name.name, self.img.routine_addr[name], rd.loc, rd.end)
            routines[r.packed] = r
        self.by_packed = routines
        for name, rd in self.b.g.routines.items():
            r = routines[self.img.routine_addr[name]]
            try:
                self.compile_routine(r, rd)
            except (CompileError, BuildError) as e:
                # Leftover code can name things the game no longer has (Zork III's
                # I-CANDLES). Keep going; the routine stops the game only if it's called.
                self.errors.append(str(e))
                self.img.warnings.append(f"{e} -- {r.name} will stop the game if it is called")
                r.body = [Broken(str(e), rd.loc)]
                r.defaults = [None] * len(r.locals)
        return routines

    # -------------------------------------------------------- routine
    def compile_routine(self, r, rd):
        self.r = r
        self.acts = {}
        mode = "req"
        params = []
        for p in rd.params:
            if isinstance(p, str):
                m = p.upper()
                mode = {"OPTIONAL": "opt", "OPT": "opt", "AUX": "aux", "EXTRA": "aux"}.get(m, mode)
                continue
            if isinstance(p, MList):
                params.append((p[0], mode, p[1] if len(p) > 1 else None))
            elif isinstance(p, Atom):
                params.append((p, mode, None))
        for name, mode, default in params:
            r.locals.append(name.name)
        self.local_index = {name: i for i, (name, _, _) in enumerate(params)}
        r.nreq = sum(1 for _, m, _ in params if m == "req")
        r.nargs = sum(1 for _, m, _ in params if m in ("req", "opt"))
        if rd.act is not None:
            r.act = self.activation(rd.act)
        # Find every local bound by a REPEAT/PROG so its slot exists before compiling.
        self.collect_block_locals(rd.body)
        r.defaults = [self.expr(d) if d is not None else None for _, _, d in params]
        r.body = [self.expr(x) for x in rd.body]
        if len(r.locals) > 15:
            self.warn(rd.loc, f"routine {r.name} has {len(r.locals)} locals (Z-machine allows 15)")

    def warn(self, loc, msg):
        self.img.warnings.append(f"{loc}: {msg}")

    def activation(self, atom):
        a = self.acts.get(atom)
        if a is None:
            a = self.acts[atom] = Activation(atom.name)
        return a

    def collect_block_locals(self, body):
        def walk(x):
            if isinstance(x, Form) and x and isinstance(x[0], Atom):
                if x[0].name in ("REPEAT", "PROG", "BIND") and len(x) > 1:
                    i = 1
                    if isinstance(x[i], Atom):
                        i += 1
                    if i < len(x) and isinstance(x[i], MList):
                        for bnd in x[i]:
                            nm = bnd[0] if isinstance(bnd, MList) else bnd
                            if isinstance(nm, Atom) and nm not in self.local_index:
                                self.local_index[nm] = len(self.r.locals)
                                self.r.locals.append(nm.name)
                for y in x:
                    walk(y)
            elif isinstance(x, (MList, Vector)):
                for y in x:
                    walk(y)
        for b in body:
            walk(b)

    # -------------------------------------------------------- expressions
    def expr(self, x):
        if isinstance(x, bool):
            return Const(int(x))
        if isinstance(x, int):
            return Const(x)
        if isinstance(x, str):
            return Const(self.img.string(x))
        if isinstance(x, Char):
            return Const(ord(x.c))
        if isinstance(x, MFalse):
            return Const(0)
        if isinstance(x, Atom):
            if x is A("T") or x is A("ELSE"):
                return Const(1)
            return self.gval(x, None)
        if isinstance(x, Form):
            return self.form(x)
        if isinstance(x, Hashed):
            return self.expr(x.value)
        if isinstance(x, MList):
            # A bare (...) where a statement belongs: ZILCH runs its items in order
            # (Zork II's DREARY-ROOM-FCN depends on this).
            return Seq([self.expr(y) for y in x], x.loc)
        raise CompileError(f"{getattr(x, 'loc', '?')}: can't compile {mdl_repr(x)[:60]}")

    def gval(self, atom, loc):
        img = self.img
        if atom in img.global_num:
            n = img.global_num[atom]
            return Global(img.globals_addr + 2 * (n - 16), atom.name, loc)
        if atom in getattr(self, "local_index", {}) and not self._names_something(atom):
            # ,X where X is only a local: ZILCH used the local (Cutthroats'
            # MOVE-SHARED-OBJECTS has <MOVE ,GLOBAL-SURFACE ,PLACE>; see its .zap).
            self.warn(loc, f",{atom.name} is a local in {self.r.name}; using .{atom.name}")
            return Local(self.local_index[atom], atom.name, loc)
        try:
            return Const(self.b.resolve_atom(atom), loc)
        except BuildError as e:
            raise CompileError(f"{loc}: {e} (in {self.r.name})")

    def _names_something(self, atom):
        img, g = self.img, self.b.g
        return (atom in img.objects or atom in img.routine_addr or atom in img.consts
                or atom in g.constants or atom in g.mdl.globals or atom in img.flags)

    def lval(self, atom, loc):
        if atom in self.local_index:
            return Local(self.local_index[atom], atom.name, loc)
        try:
            node = self.gval(atom, loc)
        except CompileError:
            raise CompileError(f"{loc}: unknown local .{atom.name} in {self.r.name}")
        # ZILCH compiled .X as ,X when X isn't a local (Zork III's VIAL-F has .VIAL).
        self.warn(loc, f".{atom.name} isn't a local in {self.r.name}; using ,{atom.name}")
        return node

    def var(self, x, loc):
        """A variable named by an atom (SET X ..., INC X)."""
        if isinstance(x, Form) and x and x[0] in (LVAL, GVAL):
            x = x[1]
        if not isinstance(x, Atom):
            raise CompileError(f"{loc}: expected a variable name, got {mdl_repr(x)}")
        if x in self.local_index:
            return Local(self.local_index[x], x.name, loc)
        if x in self.img.global_num:
            n = self.img.global_num[x]
            return Global(self.img.globals_addr + 2 * (n - 16), x.name, loc)
        raise CompileError(f"{loc}: unknown variable {x.name} in {self.r.name}")

    def form(self, f):
        loc = f.loc
        if not f:
            return Const(0, loc)
        head = f[0]
        if isinstance(head, int) and len(f) in (2, 3):
            # MDL shorthand: <2 ,TBL> is <GET ,TBL 2>, <2 ,TBL val> is <PUT ,TBL 2 val>
            name = "GET" if len(f) == 2 else "PUT"
            args = [self.expr(f[1]), Const(head, loc)] + [self.expr(a) for a in f[2:]]
            return Op(self.builtins[name][1], args, name, loc)
        if not isinstance(head, Atom):
            raise CompileError(f"{loc}: can't call {mdl_repr(head)}")
        n = head.name
        args = f[1:]
        sp = SPECIAL.get(n)
        if sp is not None:
            return sp(self, f, args, loc)
        if n in TABLE_FORMS:
            return Const(self.b.table(f), loc)
        if head in self.img.routine_addr:
            return Call(self.by_packed[self.img.routine_addr[head]], [self.expr(a) for a in args],
                        n, loc)
        bi = self.builtins.get(n)
        if bi is not None:
            kind, fn = bi
            if kind == "var":
                return VarOp(fn, self.var(args[0], loc), [self.expr(a) for a in args[1:]], n, loc)
            if kind == "io":
                return IoOp(fn, [self.expr(a) for a in args], n, loc)
            return Op(fn, [self.expr(a) for a in args], n, loc)
        raise CompileError(f"{loc}: unknown routine or operation {n} (in {self.r.name})")


# ---------------------------------------------------------------- special forms

def _gval(c, f, args, loc):
    return c.gval(args[0], loc)


def _lval(c, f, args, loc):
    return c.lval(args[0], loc)


def _quote(c, f, args, loc):
    return c.expr(args[0])


def _set(c, f, args, loc):
    return SetVar(c.var(args[0], loc), c.expr(args[1]), loc)


def _test(c, x):
    """Compile an expression used as a condition. ZILCH quirk: <SET var constant> as a
    test always counts as true -- the store can't branch, so the test was dropped.
    (Zork III r15's parser needs this for <AND ... <SET VAL 0>>; see its .zap.)"""
    node = c.expr(x)
    if isinstance(node, SetVar) and isinstance(node.val, Const):
        return Seq([node, Const(1, node.loc)], node.loc)
    return node


def _cond(c, f, args, loc):
    clauses = []
    for cl in args:
        if not isinstance(cl, MList) or not cl:
            raise CompileError(f"{loc}: bad COND clause {mdl_repr(cl)[:40]}")
        clauses.append((_test(c, cl[0]), [c.expr(x) for x in cl[1:]]))
    return Cond(clauses, loc)


def _and(c, f, args, loc):
    return And([_test(c, a) for a in args], loc)


def _or(c, f, args, loc):
    return Or([_test(c, a) for a in args], loc)


def _block(loop):
    def make(c, f, args, loc):
        i = 0
        act = None
        if args and isinstance(args[0], Atom):
            act = c.activation(args[0])
            i = 1
        binds = args[i] if i < len(args) else MList()
        inits = []
        for bnd in binds:
            if isinstance(bnd, MList):
                inits.append((c.local_index[bnd[0]], c.expr(bnd[1]) if len(bnd) > 1 else None))
            elif isinstance(bnd, Atom):
                inits.append((c.local_index[bnd], None))
        body = [c.expr(x) for x in args[i + 1:]]
        return Block(body, act, inits, loop, loc, f.end)
    return make


def _return(c, f, args, loc):
    val = c.expr(args[0]) if args else None
    act = c.activation(args[1]) if len(args) > 1 else None
    return Return(val, act, loc)


def _again(c, f, args, loc):
    return Again(c.activation(args[0]) if args else None, loc)


def _rtrue(c, f, args, loc):
    return RoutineExit(1, "RTRUE", loc)


def _rfalse(c, f, args, loc):
    return RoutineExit(0, "RFALSE", loc)


def _rstack(c, f, args, loc):
    return RoutineExit(None, "RSTACK", loc)


def _printi(ret):
    def make(c, f, args, loc):
        if not isinstance(args[0], str):
            raise CompileError(f"{loc}: PRINTI needs a string")
        return Print(zil_text(args[0]), ret, loc)
    return make


def _assigned(c, f, args, loc):
    a = args[0]
    if isinstance(a, Form) and a and a[0] in (LVAL, GVAL):
        a = a[1]
    return Assigned(c.local_index[a], loc)


def _value(c, f, args, loc):
    a = args[0]
    if isinstance(a, Atom):
        return c.var(a, loc)
    return Op(c.builtins["VALUE"][1], [c.expr(a)], "VALUE", loc)


def _gassigned(c, f, args, loc):
    from .mdl import truthy
    v = c.b.g.mdl.eval(f, c.b.g.global_env)
    return Const(1 if truthy(v) else 0, loc)


SPECIAL = {
    "GVAL": _gval, "LVAL": _lval, "QUOTE": _quote,
    "SET": _set, "SETG": _set,
    "COND": _cond, "AND": _and, "OR": _or,
    "REPEAT": _block(True), "PROG": _block(False), "BIND": _block(False),
    "RETURN": _return, "AGAIN": _again,
    "RTRUE": _rtrue, "RFALSE": _rfalse, "RSTACK": _rstack,
    "PRINTI": _printi(False), "PRINTR": _printi(True),
    "ASSIGNED?": _assigned, "VALUE": _value,
    "GASSIGNED?": _gassigned,
}
