"""A small MDL evaluator for the code that runs while a game loads.

ZIL source is mostly declarations, but macros (DEFMAC), helper functions
(DEFINE) and %<...> read-time forms are real MDL programs that run inside the
compiler. This module runs them. ZIL's own declarations (ROUTINE, OBJECT,
SYNTAX ...) are handed to the loader through `zil_hooks`.

MDL truth: everything is true except FALSE (written <>). 0 is true here.
"""

from .reader import (Atom, Form, MList, Vector, Char, Segment, Hashed, ReadEval,
                     mdl_repr, _Seq)


class MDLError(Exception):
    pass


class MFalse:
    """MDL #FALSE (). Optionally carries a reason list."""
    __slots__ = ("items",)

    def __init__(self, items=()):
        self.items = list(items)

    def __repr__(self):
        return "<>" if not self.items else "#FALSE (%s)" % " ".join(map(mdl_repr, self.items))

    def __eq__(self, other):
        return isinstance(other, MFalse)

    def __hash__(self):
        return 0


FALSE = MFalse()
T = Atom("T")


def truthy(x):
    return not isinstance(x, MFalse)


class ListTail:
    """REST of a list that still shares storage with it, so PUTREST works."""
    __slots__ = ("base", "off")

    def __init__(self, base, off):
        self.base, self.off = base, off

    def items(self):
        return self.base[self.off:]

    def __repr__(self):
        return repr(type(self.base)(self.items()))


# MDL lists are chains of cells: after <PUTREST .A .B>, B *is* the rest of A, so
# extending B later extends A too (Spellbreaker's MULTIFROB depends on this). Our
# lists are Python lists, so PUTREST copies B's items into A and records here that B
# now lives at A[offset:]; later operations on B are sent there.
_ALIAS = {}     # id(list) -> (base list, offset, the list itself)


def deref(x):
    if isinstance(x, list):
        a = _ALIAS.get(id(x))
        if a is not None and a[2] is x:
            return ListTail(a[0], a[1])
    if isinstance(x, ListTail):
        a = _ALIAS.get(id(x.base))
        if a is not None and a[2] is x.base:
            return ListTail(a[0], a[1] + x.off)
    return x


def seq(x):
    """Python list view of any MDL structure."""
    x = deref(x)
    if isinstance(x, ListTail):
        return x.items()
    if isinstance(x, (list, str)):
        return x
    if isinstance(x, MFalse):
        return x.items
    raise MDLError(f"not a structure: {mdl_repr(x)}")


def kind(x):
    if isinstance(x, ListTail):
        return type(x.base)
    return type(x)


A_QUOTE = Atom("QUOTE")


class Subr:
    """A built-in function used as a value (MDL's SUBR), e.g. <SETG ZSTR-OFF ,TIME>."""
    __slots__ = ("atom",)

    def __init__(self, atom):
        self.atom = atom

    def __repr__(self):
        return f"#SUBR {self.atom.name}"


class Function:
    """A DEFINE'd function, FUNCTION literal or DEFMAC body."""

    def __init__(self, name, params, body, is_macro=False):
        self.name, self.body, self.is_macro = name, body, is_macro
        self.params = parse_params(params)

    def __repr__(self):
        return f"#FUNCTION {self.name}"


def parse_params(params):
    """MDL argument list -> list of (name, mode, default, quoted).
    mode: 'req', 'opt', 'aux', 'args' (rest list)."""
    out = []
    mode = "req"
    for p in params:
        if isinstance(p, str):
            m = p.upper()
            mode = {"OPTIONAL": "opt", "OPT": "opt", "AUX": "aux", "EXTRA": "aux",
                    "ARGS": "args", "TUPLE": "args", "NAME": "name", "BIND": "name"}.get(m, mode)
            continue
        quoted = False
        default = None
        if isinstance(p, Form) and p and p[0] is Atom("QUOTE"):
            quoted = True
            p = p[1]
        if isinstance(p, MList):
            name = p[0]
            if isinstance(name, Form) and name and name[0] is Atom("QUOTE"):
                quoted = True
                name = name[1]
            default = p[1] if len(p) > 1 else None
            out.append((name, mode, default, quoted, True))
        elif isinstance(p, Atom):
            out.append((p, mode, None, quoted, False))
        elif isinstance(p, Hashed):  # #DECL etc.
            continue
    return out


class _MapRet(Exception):
    def __init__(self, values):
        self.values = values


class _MapStop(Exception):
    def __init__(self, values):
        self.values = values


class _MapLeave(Exception):
    def __init__(self, value):
        self.value = value


class _Return(Exception):
    def __init__(self, value, act=None):
        self.value, self.act = value, act


class _Again(Exception):
    def __init__(self, act=None):
        self.act = act


class Env:
    __slots__ = ("vars", "parent")

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def lookup(self, atom):
        e = self
        while e is not None:
            if atom in e.vars:
                return e.vars[atom]
            e = e.parent
        raise KeyError(atom)

    def assigned(self, atom):
        e = self
        while e is not None:
            if atom in e.vars:
                return e.vars[atom] is not _UNASSIGNED
            e = e.parent
        return False

    def set(self, atom, value):
        e = self
        while e is not None:
            if atom in e.vars:
                e.vars[atom] = value
                return
            e = e.parent
        self.vars[atom] = value  # MDL would error; be forgiving


_UNASSIGNED = object()


class MDL:
    """The evaluator. `globals` holds SETG values; `zil` is the loader, which
    receives ZIL declarations met at top level."""

    def __init__(self, zil=None):
        self.globals = {}
        self.zil = zil
        self.builtins = {}
        self._install()

    # ------------------------------------------------------------ evaluation
    def eval(self, x, env):
        if isinstance(x, Form):
            if not x:
                return FALSE
            head = x[0]
            if isinstance(head, Atom):
                f = self.builtins.get(head)
                if f is not None:
                    return f(self, x, env)
                fn = self.globals.get(head)
                if fn is None and self.zil is not None:
                    h = self.zil.mdl_hook(head)
                    if h is not None:
                        return h(x, env)
                if isinstance(fn, Function):
                    return self.call_form(fn, x, env)
                if isinstance(fn, Subr):
                    return self.builtins[fn.atom](self, x, env)
                if callable(fn):
                    return fn(*self.eval_args(x, env, 1))
                if fn is None:
                    raise MDLError(f"{x.loc}: unknown function {head.name}")
                # Applying a non-function: <1 .X> is NTH
                if isinstance(fn, int):
                    return seq(self.eval(x[1], env))[fn - 1]
                raise MDLError(f"{x.loc}: not applicable: {head.name}")
            if isinstance(head, int):
                s = self.eval(x[1], env)
                if len(x) > 2:
                    v = self.eval(x[2], env)
                    self._put(s, head, v)
                    return v
                v = seq(s)[head - 1]
                return Char(v) if isinstance(s, str) else v
            fn = self.eval(head, env)
            if isinstance(fn, Function):
                return self.call_form(fn, x, env)
            raise MDLError(f"{x.loc}: can't apply {mdl_repr(head)}")
        if isinstance(x, MList):
            return MList(self.eval_args(x, env), x.loc)
        if isinstance(x, Vector):
            return Vector(self.eval_args(x, env), x.loc)
        if isinstance(x, ReadEval):
            return self.eval(x.obj, env)
        if isinstance(x, Segment):
            raise MDLError("segment outside a structure")
        return x  # atoms, numbers, strings, chars evaluate to themselves

    def eval_args(self, items, env, start=0):
        out = []
        for a in items[start:] if start else items:
            if isinstance(a, Segment):
                v = self.eval(a.obj, env)
                out.extend(seq(v))
            else:
                out.append(self.eval(a, env))
        return out

    def call_form(self, fn, form, env):
        if fn.is_macro:
            expansion = self.expand_macro(fn, form, env)
            return self.eval(expansion, env)
        # Evaluate the args the function doesn't quote.
        raw = form[1:]
        args = []
        pi = 0
        params = [p for p in fn.params if p[1] in ("req", "opt", "args")]
        for a in raw:
            p = params[pi] if pi < len(params) else None
            quoted = p is not None and p[3]
            if p is not None and p[1] != "args":
                pi += 1
            if quoted:
                args.append(a)
            elif isinstance(a, Segment):
                args.extend(seq(self.eval(a.obj, env)))
            else:
                args.append(self.eval(a, env))
        return self.apply(fn, args, env)

    def expand_macro(self, fn, form, env=None):
        """Run a DEFMAC on the (mostly unevaluated) forms of a call."""
        raw = list(form[1:])
        args = []
        pi = 0
        params = [p for p in fn.params if p[1] in ("req", "opt", "args")]
        for a in raw:
            p = params[pi] if pi < len(params) else None
            if p is not None and p[1] != "args":
                pi += 1
            if p is None or p[3] or p[1] == "args":
                args.append(a)
            else:
                args.append(self.eval(a, env or Env()))
        out = self.apply(fn, args, env)
        if isinstance(out, _Seq) and isinstance(form, _Seq) and out.loc is None:
            out.loc = form.loc
        return out

    def apply(self, fn, args, caller=None):
        """Call fn. MDL scope is dynamic, so the callee sees the caller's locals."""
        if isinstance(fn, Subr):
            return self.builtins[fn.atom](self, Form([fn.atom] + [Form([A_QUOTE, a]) for a in args]),
                                          caller or Env())
        if callable(fn) and not isinstance(fn, Function):
            return fn(*args)
        env = Env(caller)
        env.vars[_GLOBAL_MARK] = True
        i = 0
        act = None
        for name, mode, default, quoted, has_default in fn.params:
            if mode == "req":
                if i >= len(args):
                    raise MDLError(f"too few arguments to {fn.name}")
                env.vars[name] = args[i]
                i += 1
            elif mode == "opt":
                if i < len(args):
                    env.vars[name] = args[i]
                    i += 1
                elif has_default:
                    env.vars[name] = self.eval(default, env)
                else:
                    env.vars[name] = _UNASSIGNED
            elif mode == "args":
                env.vars[name] = MList(args[i:])
                i = len(args)
            elif mode == "aux":
                env.vars[name] = self.eval(default, env) if has_default else _UNASSIGNED
            elif mode == "name":
                act = name
                env.vars[name] = ("activation", id(env))
        result = FALSE
        while True:
            try:
                for b in fn.body:
                    result = self.eval(b, env)
                return result
            except _Return as r:
                if r.act is None or r.act == act:
                    return r.value
                raise
            except _Again as a:
                if a.act is None or a.act == act:
                    continue
                raise

    # ------------------------------------------------------------ helpers
    def lval(self, atom, env):
        try:
            v = env.lookup(atom)
        except KeyError:
            raise MDLError(f"unbound local {atom.name}")
        if v is _UNASSIGNED:
            raise MDLError(f"unassigned local {atom.name}")
        return v

    def gval(self, atom):
        if atom in self.globals:
            return self.globals[atom]
        if atom in self.builtins:
            return Subr(atom)          # ,TIME etc.: a built-in function as a value
        if self.zil is not None:
            v = self.zil.mdl_gval(atom)
            if v is not None:
                return v
        raise MDLError(f"unassigned global {atom.name}")

    def _put(self, s, i, v):
        s = deref(s)
        if isinstance(s, ListTail):
            s.base[s.off + i - 1] = v
        else:
            s[i - 1] = v

    def _install(self):
        b = self.builtins
        A = Atom

        def special(name):
            def deco(f):
                for n in name.split():
                    b[A(n)] = f
                return f
            return deco

        def simple(name):
            """A function whose args are all evaluated."""
            def deco(f):
                def wrapper(m, form, env):
                    return f(*m.eval_args(form, env, 1))
                for n in name.split():
                    b[A(n)] = wrapper
                return f
            return deco

        @special("QUOTE")
        def _quote(m, form, env):
            return form[1]

        @special("LVAL")
        def _lval(m, form, env):
            return m.lval(form[1], env)

        @special("GVAL")
        def _gval(m, form, env):
            return m.gval(form[1])

        @special("SET")
        def _set(m, form, env):
            v = m.eval(form[2], env)
            env.set(form[1], v)
            return v

        @special("SETG")
        def _setg(m, form, env):
            name = m.eval(form[1], env) if not isinstance(form[1], Atom) else form[1]
            v = m.eval(form[2], env)
            m.globals[name] = v
            if m.zil is not None:
                m.zil.on_setg(name, v, form)
            return v

        @special("COND")
        def _cond(m, form, env):
            for clause in form[1:]:
                if not isinstance(clause, MList) or not clause:
                    continue
                v = m.eval(clause[0], env)
                if truthy(v):
                    for e in clause[1:]:
                        v = m.eval(e, env)
                    return v
            return FALSE

        @special("AND")
        def _and(m, form, env):
            v = T
            for e in form[1:]:
                v = m.eval(e, env)
                if not truthy(v):
                    return v
            return v

        @special("OR")
        def _or(m, form, env):
            v = FALSE
            for e in form[1:]:
                v = m.eval(e, env)
                if truthy(v):
                    return v
            return v

        @simple("NOT")
        def _not(x):
            return FALSE if truthy(x) else T

        def _prog(m, form, env, repeat):
            i = 1
            act = None
            if isinstance(form[i], Atom):
                act = form[i]
                i += 1
            binds = form[i]
            body = form[i + 1:]
            e = Env(env)
            for bnd in binds:
                if isinstance(bnd, MList):
                    e.vars[bnd[0]] = m.eval(bnd[1], e)
                elif isinstance(bnd, Atom):
                    e.vars[bnd] = _UNASSIGNED
            while True:
                try:
                    v = T
                    for x in body:
                        v = m.eval(x, e)
                    if not repeat:
                        return v
                except _Return as r:
                    if r.act is None or r.act == act:
                        return r.value
                    raise
                except _Again as a:
                    if a.act is None or a.act == act:
                        continue
                    raise

        b[A("PROG")] = lambda m, f, e: _prog(m, f, e, False)
        b[A("BIND")] = lambda m, f, e: _prog(m, f, e, False)
        b[A("REPEAT")] = lambda m, f, e: _prog(m, f, e, True)

        @special("RETURN")
        def _return(m, form, env):
            v = m.eval(form[1], env) if len(form) > 1 else T
            act = form[2] if len(form) > 2 else None
            raise _Return(v, act)

        @special("AGAIN")
        def _again(m, form, env):
            raise _Again(form[1] if len(form) > 1 else None)

        @special("FUNCTION")
        def _function(m, form, env):
            i = 1
            name = "FUNCTION"
            if isinstance(form[1], Atom):
                name = form[1].name
                i = 2
            fn = Function(name, form[i], form[i + 1:])
            return fn

        @special("DEFINE")
        def _define(m, form, env):
            name = form[1]
            i = 2
            if isinstance(form[i], Atom):  # activation name
                i += 1
            m.globals[name] = Function(name.name, form[i], form[i + 1:])
            return name

        @special("DEFMAC")
        def _defmac(m, form, env):
            name = form[1]
            i = 2
            if isinstance(form[i], Atom):
                i += 1
            m.globals[name] = Function(name.name, form[i], form[i + 1:], is_macro=True)
            return name

        @special("MAPF MAPR")
        def _mapf(m, form, env):
            fin = m.eval(form[1], env)
            fn = m.eval(form[2], env)
            structs = [seq(m.eval(s, env)) for s in form[3:]]
            is_r = form[0] is A("MAPR")
            out = []
            i = 0
            try:
                while True:
                    if structs and any(i >= len(s) for s in structs):
                        break
                    if is_r:
                        args = [ListTail(s, i) if isinstance(s, list) else s[i:] for s in structs]
                    else:
                        args = [s[i] for s in structs]
                    try:
                        out.append(m.apply(fn, args, env))
                    except _MapRet as r:
                        out.extend(r.values)
                    i += 1
            except _MapStop as s:
                out.extend(s.values)
            except _MapLeave as l:
                return l.value
            if isinstance(fin, MFalse):
                return out[-1] if out else FALSE
            return m.apply(fin, out) if not isinstance(fin, Function) else m.apply(fin, out)

        @simple("MAPRET")
        def _mapret(*vals):
            raise _MapRet(list(vals))

        @simple("MAPSTOP")
        def _mapstop(*vals):
            raise _MapStop(list(vals))

        @simple("MAPLEAVE")
        def _mapleave(v=T):
            raise _MapLeave(v)

        # structure builders -------------------------------------------------
        b[A("LIST")] = lambda m, f, e: MList(m.eval_args(f, e, 1))
        b[A("FORM")] = lambda m, f, e: Form(m.eval_args(f, e, 1))
        b[A("VECTOR")] = lambda m, f, e: Vector(m.eval_args(f, e, 1))
        b[A("ILIST")] = lambda m, f, e: MList([m.eval(f[2], e) if len(f) > 2 else FALSE
                                               for _ in range(m.eval(f[1], e))])
        b[A("IVECTOR")] = lambda m, f, e: Vector([m.eval(f[2], e) if len(f) > 2 else FALSE
                                                  for _ in range(m.eval(f[1], e))])
        b[A("IUVECTOR")] = b[A("IVECTOR")]       # uniform vectors behave the same here
        b[A("UVECTOR")] = b[A("VECTOR")]
        b[A("ISTRING")] = lambda m, f, e: "".join(
            (lambda c: c.c if isinstance(c, Char) else str(c))(m.eval(f[2], e)) if len(f) > 2 else " "
            for _ in range(m.eval(f[1], e)))
        # Builtin "functions" as values (for <MAPF ,LIST ...>)
        self.globals[A("LIST")] = lambda *a: MList(a)
        self.globals[A("VECTOR")] = lambda *a: Vector(a)
        self.globals[A("FORM")] = lambda *a: Form(a)
        self.globals[A("STRING")] = lambda *a: "".join(_to_str(x) for x in a)
        self.globals[A("+")] = lambda *a: sum(a)
        # We act like ZILCH, the compiler: sources test these to pick compiled code
        # over the versions meant to run inside MDL.
        # Table forms called while loading (Seastalker's <MAPF ,PLTABLE ...>) give back
        # the table's description; image.py lays it out like any other table.
        for tname in ("TABLE", "LTABLE", "PTABLE", "PLTABLE", "ITABLE"):
            self.globals[A(tname)] = (lambda n: lambda *a: Form([A(n)] + list(a)))(tname)
        # The output channel, and a stand-in for the keyboard: some compile files ask the
        # person compiling a question (Suspect's m3.zil: "Debugging? (Y or N)"). A
        # release build answered N.
        self.globals[A("OUTCHAN")] = A("OUTCHAN")
        self.globals[A("INCHAN")] = A("INCHAN")
        self.globals[A("ZILCH")] = T
        self.globals[A("PREDGEN")] = T
        self.globals[A("T")] = T

        @simple("STRING")
        def _string(*a):
            return "".join(_to_str(x) for x in a)

        @simple("NTH")
        def _nth(s, n=1):
            v = seq(s)[n - 1]
            return Char(v) if isinstance(s, str) else v     # a string's elements are characters

        @simple("REST")
        def _rest(s, n=1):
            s = deref(s)
            if isinstance(s, str):
                return s[n:]
            if isinstance(s, ListTail):
                return ListTail(s.base, s.off + n)
            if isinstance(s, list):
                return ListTail(s, n)
            raise MDLError(f"REST of {mdl_repr(s)}")

        @simple("BACK")
        def _back(s, n=1):
            if isinstance(s, ListTail):
                return ListTail(s.base, s.off - n)
            raise MDLError("BACK of non-tail")

        @simple("TOP")
        def _top(s):
            return s.base if isinstance(s, ListTail) else s

        @simple("PUTREST")
        def _putrest(s, new):
            orig = s
            s = deref(s)
            new_items = list(seq(new))
            base, off = (s.base, s.off) if isinstance(s, ListTail) else (s, 0)
            del base[off + 1:]
            base.extend(new_items)
            if isinstance(new, list) and not isinstance(new, str):
                _ALIAS[id(new)] = (base, off + 1, new)       # new now lives inside base
            return orig

        @simple("PUT")
        def _put(s, i, v):
            self._put(s, i, v)
            return s

        @simple("EMPTY?")
        def _empty(s):
            return T if len(seq(s)) == 0 else FALSE

        @simple("LENGTH")
        def _length(s):
            return len(seq(s))

        @simple("LENGTH?")
        def _lengthp(s, n):
            ln = len(seq(s))
            return ln if ln <= n else FALSE

        @simple("CHTYPE")
        def _chtype(x, t):
            n = t.name
            if n == "FIX" and isinstance(x, Char):
                return ord(x.c)                  # <CHTYPE !\> FIX> is the character code
            if n == "FIX" and isinstance(x, str) and len(x) == 1:
                return ord(x)
            if n == "CHARACTER" and isinstance(x, int):
                return Char(chr(x))
            if n == "FIX" and isinstance(x, int):
                return x
            items = list(seq(x)) if not isinstance(x, (int, Atom)) else x
            if n == "FORM":
                return Form(items)
            if n == "LIST":
                return MList(items)
            if n == "VECTOR":
                return Vector(items)
            if n == "FALSE":
                return MFalse(items)
            return Hashed(t, x)

        @simple("TYPE")
        def _type(x):
            return A(type_name(x))

        @simple("PRIMTYPE")
        def _primtype(x):
            t = type_name(x)
            return A({"FORM": "LIST", "LIST": "LIST", "VECTOR": "VECTOR", "STRING": "STRING",
                      "ATOM": "ATOM", "FIX": "WORD", "FALSE": "LIST"}.get(t, t))

        @simple("TYPE?")
        def _typep(x, *types):
            t = type_name(x)
            for ty in types:
                if ty.name == t:
                    return ty
            return FALSE

        @simple("SPNAME PNAME")
        def _spname(a):
            return a.name

        @simple("PARSE")
        def _parse(s):
            from .reader import read_text
            objs = read_text(s)
            return objs[0] if objs else FALSE

        @simple("ATOM")
        def _atom(s):
            return A(s)

        @simple("LOOKUP")
        def _lookup(s, oblist=None):
            return A(s) if s in Atom._table else FALSE

        @simple("ASCII")
        def _ascii(x):
            return ord(x.c) if isinstance(x, Char) else Char(chr(x))

        @simple("=? N=?")
        def _eqp(a, b):
            return T if _mdl_equal(a, b) else FALSE

        b[A("N=?")] = lambda m, f, e: FALSE if _mdl_equal(*m.eval_args(f, e, 1)) else T

        @simple("==?")
        def _eqeq(a, b):
            if isinstance(a, (int, str, Char)) or isinstance(b, (int, str, Char)):
                return T if a == b and type(a) is type(b) else FALSE
            return T if a is b or (isinstance(a, MFalse) and isinstance(b, MFalse)) else FALSE

        b[A("N==?")] = lambda m, f, e: FALSE if truthy(_eqeq(*m.eval_args(f, e, 1))) else T

        # arithmetic ---------------------------------------------------------
        @simple("+")
        def _add(*a):
            return sum(a)

        @simple("-")
        def _sub(a, *r):
            if not r:
                return -a
            for x in r:
                a -= x
            return a

        @simple("*")
        def _mul(*a):
            v = 1
            for x in a:
                v *= x
            return v

        @simple("/")
        def _div(a, *r):
            for x in r:
                a = int(a / x)
            return a

        @simple("MOD")
        def _mod(a, b):
            return a % b

        @simple("MIN")
        def _min(*a):
            return min(a)

        @simple("MAX")
        def _max(*a):
            return max(a)

        @simple("ABS")
        def _abs(a):
            return abs(a)

        def cmp(fn):
            return lambda *a: T if fn(*a) else FALSE

        for n, fn in [("G?", lambda a, b: a > b), ("L?", lambda a, b: a < b),
                      ("G=?", lambda a, b: a >= b), ("L=?", lambda a, b: a <= b),
                      ("0?", lambda a: a == 0), ("1?", lambda a: a == 1)]:
            simple(n)(cmp(fn))

        @simple("ORB")
        def _orb(*a):
            v = 0
            for x in a:
                v |= x
            return v

        @simple("ANDB")
        def _andb(*a):
            v = -1
            for x in a:
                v &= x
            return v

        @simple("LSH")
        def _lsh(a, n):
            return a << n if n >= 0 else a >> -n

        # environment --------------------------------------------------------
        @special("GASSIGNED? GBOUND?")
        def _gassigned(m, form, env):
            a = m.eval(form[1], env) if not isinstance(form[1], Atom) else form[1]
            if a in m.globals:
                return T
            if m.zil is not None and m.zil.mdl_gval(a) is not None:
                return T
            return FALSE

        @special("ASSIGNED? BOUND?")
        def _assigned(m, form, env):
            a = form[1] if isinstance(form[1], Atom) else m.eval(form[1], env)
            return T if env.assigned(a) else FALSE

        @simple("EVAL")
        def _eval(x, env_=None):
            return self.eval(x, Env())

        b[A("APPLY")] = lambda m, f, e: m.apply(*(lambda v: (v[0], v[1:], e))(m.eval_args(f, e, 1)))

        @simple("ERROR")
        def _error(*a):
            raise MDLError("ERROR: " + " ".join(map(mdl_repr, a)))

        @simple("PRINC PRIN1 PRINT")
        def _princ(*a):
            if self.zil is not None:
                self.zil.on_princ(_to_str(a[0]) if a else "")    # a 2nd arg is the channel
            return a[0] if a else T

        @simple("IMAGE")
        def _image(*a):
            return a[0] if a else T       # prints a raw character (the bell, when loaded)

        @simple("MAKE-GVAL")
        def _make_gval(a):
            return Form([A("GVAL"), a])

        @simple("TYI")
        def _tyi(*a):
            return Char("N")

        @simple("MEMQ")
        def _memq(x, s):
            items = seq(s)
            for i, y in enumerate(items):
                if (isinstance(x, Char) and (y == x.c if isinstance(y, str) else y == x)) or y is x or (
                        isinstance(x, int) and y == x):
                    return s[i:] if isinstance(s, str) else ListTail(s, i) if isinstance(s, list) else T
            return FALSE

        @simple("CRLF TERPRI")
        def _crlf(*a):
            return T

        @special("GDECL DECL? USE PACKAGE ENDPACKAGE ENTRY RENTRY BLOCK ENDBLOCK SNAME "
                 "SETG20 FLOAD FLUSH-ME-FREQUENT-WORDS "
                 # MDL housekeeping in older sources: memory, garbage collection, loading
                 "GC BLOAT ENDLOAD SNAME FREEZE GC-MON")
        def _ignore(m, form, env):
            return T

        @simple("TIME")
        def _time(*a):
            return 0           # MDL's CPU clock; sources only use it to time loading

        @simple("ITEM")
        def _item(*a):
            return T

    def define_global(self, name, value):
        self.globals[Atom(name)] = value


_GLOBAL_MARK = Atom("%%GLOBAL-ENV%%")


def _to_str(x):
    if isinstance(x, str):
        return x
    if isinstance(x, Char):
        return x.c
    if isinstance(x, Atom):
        return x.name
    if isinstance(x, int):
        return str(x)
    if isinstance(x, (list, ListTail)):
        return "".join(_to_str(y) for y in seq(x))
    return mdl_repr(x)


def type_name(x):
    if isinstance(x, MFalse):
        return "FALSE"
    if isinstance(x, bool):
        return "ATOM"
    if isinstance(x, int):
        return "FIX"
    if isinstance(x, str):
        return "STRING"
    if isinstance(x, Atom):
        return "ATOM"
    if isinstance(x, Char):
        return "CHARACTER"
    if isinstance(x, Function):
        return "MACRO" if x.is_macro else "FUNCTION"
    k = kind(x)
    if k is Form:
        return "FORM"
    if k is MList:
        return "LIST"
    if k is Vector:
        return "VECTOR"
    if isinstance(x, Hashed):
        return x.type.name
    if callable(x):
        return "SUBR"
    return type(x).__name__.upper()


def _mdl_equal(a, b):
    if isinstance(a, ListTail):
        a = kind(a)(a.items())
    if isinstance(b, ListTail):
        b = kind(b)(b.items())
    if type(a) is not type(b):
        return False
    if isinstance(a, _Seq):
        return len(a) == len(b) and all(_mdl_equal(x, y) for x, y in zip(a, b))
    return a == b
