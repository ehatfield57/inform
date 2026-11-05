"""Read ZIL/MDL source text into Python objects.

Every form, list and vector remembers where it came from (file, line), so the
debugger can show the source for whatever is running.

    Atom      an MDL atom (interned, so `is` works)
    Form      <...>
    MList     (...)
    Vector    [...]
    str       "..."
    Char      !\\c
    int       numbers (decimal, *octal*, #2 binary)
    Segment   !<...>  !.X  !,X
    Hashed    #TYPE value   (e.g. #BYTE 0)
"""

import re


class Atom:
    __slots__ = ("name",)
    _table = {}

    def __new__(cls, name):
        a = cls._table.get(name)
        if a is None:
            a = object.__new__(cls)
            a.name = name
            cls._table[name] = a
        return a

    def __repr__(self):
        return self.name

    def __reduce__(self):
        return (Atom, (self.name,))


class Loc:
    __slots__ = ("file", "line", "col")

    def __init__(self, file, line, col=0):
        self.file, self.line, self.col = file, line, col

    def __repr__(self):
        return f"{self.file}:{self.line}"


class _Seq(list):
    """Base for forms, lists and vectors: a list that remembers its location."""
    __slots__ = ("loc", "end")
    open = close = ""

    def __init__(self, items=(), loc=None, end=None):
        super().__init__(items)
        self.loc = loc
        self.end = end

    def __repr__(self):
        return self.open + " ".join(map(mdl_repr, self)) + self.close

    def __eq__(self, other):
        return type(self) is type(other) and list.__eq__(self, other)

    def __ne__(self, other):
        return not self.__eq__(other)

    __hash__ = None


class Form(_Seq):
    open, close = "<", ">"


class MList(_Seq):
    open, close = "(", ")"


class Vector(_Seq):
    open, close = "[", "]"


class Char:
    __slots__ = ("c",)

    def __init__(self, c):
        self.c = c

    def __eq__(self, other):
        return isinstance(other, Char) and other.c == self.c

    def __hash__(self):
        return hash(("char", self.c))

    def __repr__(self):
        return "!\\" + self.c


class Segment:
    """!<form>, !.X or !,X: splice the value into the enclosing structure."""
    __slots__ = ("obj", "loc")

    def __init__(self, obj, loc=None):
        self.obj, self.loc = obj, loc

    def __repr__(self):
        return "!" + mdl_repr(self.obj)


class Hashed:
    """#TYPE value, e.g. #BYTE 0 or #DECL (...)."""
    __slots__ = ("type", "value", "loc")

    def __init__(self, type_, value, loc=None):
        self.type, self.value, self.loc = type_, value, loc

    def __eq__(self, other):
        return isinstance(other, Hashed) and other.type is self.type and other.value == self.value

    __hash__ = None

    def __repr__(self):
        return f"#{self.type.name} {mdl_repr(self.value)}"


def mdl_repr(x):
    if isinstance(x, str):
        return '"' + x.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if x is True:
        return "T"
    return repr(x)


class ReadError(Exception):
    pass


# Characters that end an atom.
_DELIMS = set(" \t\r\n\f\v<>()[]{}\";',%#!") | {"\x00", "\x1a"}
_NUM_RE = re.compile(r"^-?\d+$")
_OCT_RE = re.compile(r"^\*([0-7]+)\*$")

# Common atoms.
A = Atom
GVAL, LVAL, QUOTE = A("GVAL"), A("LVAL"), A("QUOTE")


class Reader:
    def __init__(self, text, filename="?"):
        self.s = text
        self.i = 0
        self.n = len(text)
        self.file = filename
        self.warnings = []
        self.depth_lists = 0
        # Precompute line starts for fast line lookup.
        self._lines = [0] + [m.end() for m in re.finditer("\n", text)]

    def loc(self, pos=None):
        import bisect
        pos = self.i if pos is None else pos
        ln = bisect.bisect_right(self._lines, pos)
        return Loc(self.file, ln, pos - self._lines[ln - 1])

    def error(self, msg):
        raise ReadError(f"{self.loc()}: {msg}")

    def skip_ws(self):
        s, n = self.s, self.n
        while self.i < n and (s[self.i] in " \t\r\n\f\v\x00\x1a"):
            self.i += 1

    def read_all(self):
        """Read every top-level object. Comments come back as ('comment', obj) and are dropped."""
        out = []
        while True:
            self.skip_ws()
            if self.i < self.n and self.s[self.i] in ">)]}":
                # A stray closing bracket between top-level forms (an extra > in
                # Suspended's people.zil): MDL's reader skipped it, so do we.
                self.warnings.append(f"{self.loc()}: extra '{self.s[self.i]}' skipped")
                self.i += 1
                continue
            obj = self.read()
            if obj is _EOF:
                return out
            if obj is _COMMENT:
                continue
            out.append(obj)

    def read(self):
        """Read one object; returns _EOF at end of input, _COMMENT for a ;comment."""
        self.skip_ws()
        if self.i >= self.n:
            return _EOF
        s = self.s
        c = s[self.i]
        start = self.i
        if c == ";":
            self.i += 1
            self.read_required()
            return _COMMENT
        if c == "<":
            return self.read_seq(Form, ">")
        if c == "(":
            return self.read_seq(MList, ")")
        if c == "[":
            return self.read_seq(Vector, "]")
        if c == "{":
            return self.read_seq(Vector, "}")
        if c == '"':
            return self.read_string()
        if c == "'":
            self.i += 1
            loc = self.loc(start)
            return Form([QUOTE, self.read_required()], loc)
        if c == ",":
            self.i += 1
            loc = self.loc(start)
            return Form([GVAL, self.read_required()], loc)
        if c == "." and self.i + 1 < self.n and s[self.i + 1] not in _DELIMS:
            self.i += 1
            loc = self.loc(start)
            return Form([LVAL, self.read_required()], loc)
        if c == "%":
            # %<...> evaluates at read time; %%<...> evaluates and discards.
            self.i += 1
            discard = False
            if self.i < self.n and s[self.i] == "%":
                self.i += 1
                discard = True
            obj = self.read_required()
            return ReadEval(obj, discard, self.loc(start))
        if c == "#":
            self.i += 1
            t = self.read_required()
            if isinstance(t, int):  # #2 101 = binary
                v = self.read_atom_text()
                return int(v, t)
            if not isinstance(t, Atom):
                self.error("bad # syntax")
            return Hashed(t, self.read_required(), self.loc(start))
        if c == "!":
            nxt = s[self.i + 1] if self.i + 1 < self.n else ""
            if nxt == "\\":
                self.i += 3
                return Char(s[self.i - 1])
            if nxt in "<.,('[":
                self.i += 1
                return Segment(self.read_required(), self.loc(start))
            if nxt == '"':
                # !"..." is a string in some sources
                self.i += 1
                return self.read_string()
        if c in ">)]}":
            self.error(f"unexpected {c!r}")
        return self.read_atom_or_number()

    def read_required(self):
        while True:
            obj = self.read()
            if obj is _EOF:
                self.error("unexpected end of file")
            if obj is _COMMENT:
                continue
            return obj

    def read_seq(self, cls, close):
        loc = self.loc()
        self.i += 1
        items = []
        if cls is MList:
            self.depth_lists += 1
            try:
                return self._read_items(cls, close, loc, items)
            finally:
                self.depth_lists -= 1
        return self._read_items(cls, close, loc, items)

    def _read_items(self, cls, close, loc, items):
        while True:
            self.skip_ws()
            if self.i >= self.n:
                raise ReadError(f"{loc}: unclosed {cls.open}")
            if self.s[self.i] == close:
                self.i += 1
                return cls(items, loc, self.loc())
            # MDL allows <FOO ... !> style closers; also a stray other closer.
            if self.s[self.i] == "!" and self.i + 1 < self.n and self.s[self.i + 1] == close:
                self.i += 2
                return cls(items, loc, self.loc())
            if cls is Form and self.s[self.i] == ")" and self.depth_lists > 0:
                # A ) where > was due (Lurking Horror r203's PRE-GIVE leaves an <AND open):
                # it closes every open <...> up to the ( it belongs to. The ) itself is
                # left for that list.
                self.warnings.append(f"{self.loc()}: ')' closes an open '<'")
                return cls(items, loc, self.loc())
            obj = self.read()
            if obj is _COMMENT:
                continue
            if obj is _EOF:
                raise ReadError(f"{loc}: unclosed {cls.open}")
            items.append(obj)

    def read_string(self):
        self.i += 1
        s, n = self.s, self.n
        out = []
        while self.i < n:
            c = s[self.i]
            if c == "\\":
                out.append(s[self.i + 1])
                self.i += 2
                continue
            if c == '"':
                self.i += 1
                return "".join(out)
            out.append(c)
            self.i += 1
        self.error("unclosed string")

    def read_atom_text(self):
        s, n = self.s, self.n
        out = []
        while self.i < n:
            c = s[self.i]
            if c == "\\":
                out.append(s[self.i + 1])
                self.i += 2
                continue
            if c in _DELIMS:
                # "!-" inside an atom is an oblist trailer (RETURN!-): keep reading.
                if c == "!" and self.i + 1 < n and s[self.i + 1] == "-":
                    out.append("!-")
                    self.i += 2
                    continue
                # A ! that ends a name is dropped: Hollywood Hijinx defines
                # <ROUTINE CANT-VERB-A-PRSO! ...> and calls <CANT-VERB-A-PRSO ...>.
                if c == "!" and out and (self.i + 1 >= n or s[self.i + 1] in " \t\r\n>)]}"):
                    self.i += 1
                    break
                break
            out.append(c)
            self.i += 1
        return "".join(out)

    def read_atom_or_number(self):
        start = self.i
        text = self.read_atom_text()
        if not text:
            self.error(f"unexpected character {self.s[start]!r}")
            self.i += 1
        if _NUM_RE.match(text):
            return int(text)
        m = _OCT_RE.match(text)
        if m:
            return int(m.group(1), 8)
        # Strip oblist trailers: RETURN!- -> RETURN, FOO!-BAR -> FOO
        if "!-" in text:
            text = text.split("!-")[0]
        # NAME:TYPE declares a type (MIM MDL's ADECL), e.g. <GLOBAL FOOD-COUNT:FIX 1> in
        # Lurking Horror. The name is the part before the colon. (*:STRING, a TELL-TOKENS
        # pattern, starts with * and is kept whole.)
        if ":" in text and not text.startswith("*"):
            name, _, typ = text.partition(":")
            if name and typ and typ.replace("-", "").isalnum():
                text = name
        return Atom(text)


class ReadEval:
    """%<...>: evaluated by the loader as soon as it is seen."""
    __slots__ = ("obj", "discard", "loc")

    def __init__(self, obj, discard, loc):
        self.obj, self.discard, self.loc = obj, discard, loc

    def __repr__(self):
        return "%" + mdl_repr(self.obj)


_EOF = object()
_COMMENT = object()


def read_text(text, filename="?", warnings=None):
    r = Reader(text, filename)
    out = r.read_all()
    if warnings is not None:
        warnings.extend(r.warnings)
    return out


def read_file(path, display_name=None):
    with open(path, encoding="latin-1") as f:
        text = f.read()
    return read_text(text, display_name or path), text
