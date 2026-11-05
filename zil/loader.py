"""Load a ZIL game: run its files top to bottom and collect the declarations.

    game = load("sources/zork1-r119.zip")      # or a folder of .zil files

Top-level MDL code (SETG, COND, macros, %<...>) runs as it is met. ZIL
declarations (ROUTINE, OBJECT, ROOM, GLOBAL, CONSTANT, SYNTAX, ...) are
recorded here; image.py then lays them out in memory.
"""

import os
import re
import zipfile

from .reader import (Atom, Form, MList, Vector, Segment, Hashed, ReadEval, Loc,
                     read_text, mdl_repr, _Seq)
from .mdl import MDL, MDLError, Env, Function, FALSE, T, truthy

A = Atom
QUOTE = A("QUOTE")


class LoadError(Exception):
    pass


# ZIL versions: the <VERSION ...> names and the Z-machine version they make.
VERSIONS = {"ZIP": 3, "EZIP": 4, "XZIP": 5, "YZIP": 6, "3": 3, "4": 4, "5": 5, "6": 6, "8": 8}


class RoutineDef:
    def __init__(self, name, act, params, body, loc, end):
        self.name, self.act, self.params, self.body = name, act, params, body
        self.loc, self.end = loc, end


class ObjectDef:
    def __init__(self, name, is_room, props, loc, order):
        self.name, self.is_room, self.props, self.loc = name, is_room, props, loc
        self.order = order


class SyntaxDef:
    def __init__(self, verb, parts, action, preaction, action_name, loc):
        self.verb = verb            # Atom
        self.parts = parts          # list of ('prep', Atom) / ('obj', find_flag, [loc atoms])
        self.action = action        # Atom (routine)
        self.preaction = preaction  # Atom or None
        self.action_name = action_name
        self.loc = loc


class Sources:
    """The .zil files of one game, from a folder or a zip."""

    def __init__(self, path):
        self.path = path
        self.files = {}   # lower-case base name (no extension) -> (display name, text)
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                for n in z.namelist():
                    if n.endswith("/"):
                        continue
                    self._add(n, z.read(n).decode("latin-1"))
        else:
            for root, _, files in os.walk(path):
                for f in files:
                    p = os.path.join(root, f)
                    with open(p, encoding="latin-1") as fh:
                        self._add(os.path.relpath(p, path), fh.read())
        self.name = os.path.splitext(os.path.basename(path.rstrip("/")))[0]

    def _add(self, name, text):
        base = os.path.basename(name)
        stem, ext = os.path.splitext(base)
        if ext.lower() in (".zil", ".mud", ".zl"):
            self.files[stem.lower()] = (base, text)

    def find(self, name):
        key = os.path.splitext(os.path.basename(name))[0].lower()
        return self.files.get(key)

    def main_file(self):
        """The file that isn't inserted by any other: usually <game>.zil."""
        stem = re.sub(r"-(r\d+|rlater|rmid\d*|beta.*|mac.*|invclues.*|s\d+).*$", "",
                      self.name.lower())
        if stem in self.files:
            return stem
        inserted = set()
        for _, text in self.files.values():
            for m in re.finditer(r'INSERT-FILE\s+"([^"]+)"', text, re.I):
                inserted.add(os.path.basename(m.group(1)).lower())
        roots = [k for k in self.files if k not in inserted]
        if len(roots) == 1:
            return roots[0]
        roots.sort(key=lambda k: -self.files[k][1].upper().count("INSERT-FILE"))
        if roots:
            return roots[0]
        raise LoadError("can't tell which file is the main one")


class Game:
    """Everything declared by a game's source, in declaration order."""

    def __init__(self, sources):
        self.sources = sources
        self.version = 3
        self.texts = {}            # display file name -> source text
        self.file_order = []
        self.routines = {}         # Atom -> RoutineDef
        self.objects = {}          # Atom -> ObjectDef
        self.globals = {}          # Atom -> (value form, loc)
        self.constants = {}        # Atom -> (value form, loc)
        self.syntaxes = []
        self.synonyms = []         # (main Atom, [Atoms])  from <SYNONYM ...>
        self.adj_synonyms = []
        self.buzz = []             # Atoms in order
        self.directions = []
        self.propdefs = {}         # Atom -> (spec list, loc)
        self.vocab = []            # extra words: (Atom, part of speech) from VOC etc.
        self.bit_synonyms = []
        self.zstart = A("GO")
        self.messages = []         # PRINC output while loading
        self.serial = None
        self.release = None
        self._order = 0
        self.mdl = MDL(self)
        self.global_env = Env()
        m = re.search(r"-r(\d+)", sources.name)
        if m:
            self.release = int(m.group(1))
        self.flags = []            # flag atoms in order of first use
        self._flagset = set()
        self.properties = []       # property atoms in order of first use (non-direction)
        self._propset = set()
        self.word_events = []      # (order, Atom word, part of speech, extra)

    # ------------------------------------------------------------ loading
    def load(self):
        main = self.sources.main_file()
        self.insert_file(main)
        return self

    def insert_file(self, name):
        found = self.sources.find(name)
        if found is None:
            raise LoadError(f"missing source file {name}")
        display, text = found
        if display in self.texts:
            return
        self.texts[display] = text
        self.file_order.append(display)
        for obj in read_text(text, display):
            self.top_level(obj)

    def top_level(self, obj):
        try:
            if isinstance(obj, ReadEval):
                # %<...> at top level: whatever form it produces is compiled too.
                v = self.mdl.eval(obj.obj, self.global_env)
                if not obj.discard and isinstance(v, Form):
                    self.top_level(v)
            elif isinstance(obj, Form):
                self.mdl.eval(obj, self.global_env)
            # strings and other bare objects at top level are comments
        except MDLError as e:
            loc = getattr(obj, "loc", None)
            raise LoadError(f"{loc}: {e}") from None

    def next_order(self):
        self._order += 1
        return self._order

    # ------------------------------------------------------------ MDL interface
    def mdl_hook(self, head):
        return self._hooks.get(head.name) and (lambda f, e, h=self._hooks[head.name]: h(self, f, e))

    def mdl_gval(self, atom):
        if atom in self.constants:
            v = self.constants[atom][0]
            if isinstance(v, int):
                return v
            return atom
        if atom in self.globals or atom in self.objects or atom in self.routines:
            return atom
        return None

    def on_setg(self, name, value, form):
        pass

    def on_princ(self, text):
        self.messages.append(text)

    # ------------------------------------------------------------ helpers
    def expand(self, x, env=None):
        """Expand macros and %<...> inside routine code (recursively)."""
        env = env or self.global_env
        if isinstance(x, ReadEval):
            v = self.mdl.eval(x.obj, env)
            if x.discard:
                return _DROP
            if isinstance(v, _Seq) and v.loc is None:
                v.loc = x.loc
            return self.expand(v, env)
        if isinstance(x, Form):
            if not x:
                return x
            head = x[0]
            if head is QUOTE:
                return x
            if isinstance(head, Atom):
                fn = self.mdl.globals.get(head)
                if isinstance(fn, Function) and fn.is_macro:
                    try:
                        out = self.mdl.expand_macro(fn, x, env)
                    except MDLError as e:
                        raise LoadError(f"{x.loc}: in macro {head.name}: {e}") from None
                    _set_locs(out, x.loc)
                    return self.expand(out, env)
            return self._expand_items(x, env)
        if isinstance(x, (MList, Vector)):
            return self._expand_items(x, env)
        if isinstance(x, Segment):
            return Segment(self.expand(x.obj, env), x.loc)
        if isinstance(x, Hashed):
            return x
        return x

    def _expand_items(self, x, env):
        out = type(x)([], x.loc, x.end)
        for item in x:
            e = self.expand(item, env)
            if e is _DROP:
                continue
            if isinstance(e, Segment) and isinstance(e.obj, (MList, Vector)):
                out.extend(e.obj)
                continue
            out.append(e)
        return out

    def note_flag(self, atom):
        if atom not in self._flagset:
            self._flagset.add(atom)
            self.flags.append(atom)

    def note_prop(self, atom):
        if atom not in self._propset and atom not in self.directions:
            self._propset.add(atom)
            self.properties.append(atom)

    def word(self, atom, pos, extra=None):
        self.word_events.append((self.next_order(), atom, pos, extra))

    _hooks = {}


_DROP = object()


def _set_locs(x, loc):
    if isinstance(x, _Seq):
        if x.loc is None:
            x.loc = loc
        for y in x:
            _set_locs(y, loc)
    elif isinstance(x, Segment):
        _set_locs(x.obj, loc)


def hook(*names):
    def deco(f):
        for n in names:
            Game._hooks[n] = f
        return f
    return deco


def _name(x):
    """Atom or string -> Atom."""
    if isinstance(x, str):
        return A(x.upper())
    return x


@hook("VERSION")
def _version(g, form, env):
    v = form[1]
    key = v.name if isinstance(v, Atom) else str(v)
    if key not in VERSIONS:
        raise MDLError(f"unknown VERSION {key}")
    g.version = VERSIONS[key]
    for extra in form[2:]:
        if isinstance(extra, Atom) and extra.name == "TIME":
            g.time_game = True
    return T


@hook("INSERT-FILE", "FLOAD", "IFILE")
def _insert(g, form, env):
    name = g.mdl.eval(form[1], env)
    g.insert_file(name)
    return T


@hook("ROUTINE")
def _routine(g, form, env):
    name = form[1]
    i = 2
    act = None
    if isinstance(form[i], Atom):
        act = form[i]
        i += 1
    params = form[i]
    body = [g.expand(b, env) for b in form[i + 1:]
            if not (isinstance(b, Hashed) and b.type.name == "DECL")]
    body = [b for b in body if b is not _DROP]
    g.routines[name] = RoutineDef(name, act, g.expand(params, env), body, form.loc, form.end)
    return name


@hook("OBJECT", "ROOM")
def _object(g, form, env):
    name = form[1]
    props = []
    for p in form[2:]:
        p = g.expand(p, env)
        if p is _DROP:
            continue
        if not isinstance(p, MList) or not p:
            continue
        pname = p[0]
        if pname.name == "FLAGS":
            for f in p[1:]:
                g.note_flag(f)
        elif pname.name in ("SYNONYM",):
            for w in p[1:]:
                g.word(_name(w), "OBJECT")
        elif pname.name in ("ADJECTIVE",):
            for w in p[1:]:
                g.word(_name(w), "ADJECTIVE")
        elif pname.name == "PSEUDO":
            for w in p[1::2]:
                g.word(_name(w), "OBJECT")
        is_loc = pname.name in ("IN", "LOC") and len(p) == 2 and isinstance(p[1], Atom)
        if not is_loc and pname.name not in ("DESC", "FLAGS"):
            g.note_prop(pname)
        props.append(p)
    if name in g.objects:
        # A second definition replaces the first but keeps its place.
        g.objects[name].props = props
        g.objects[name].is_room = form[0].name == "ROOM"
    else:
        g.objects[name] = ObjectDef(name, form[0].name == "ROOM", props, form.loc, g.next_order())
    return name


@hook("GLOBAL", "LOWCORE")
def _global(g, form, env):
    name = form[1]
    value = g.expand(form[2], env) if len(form) > 2 else FALSE
    g.globals[name] = (value, form.loc)
    return name


@hook("CONSTANT")
def _constant(g, form, env):
    name = form[1]
    value = g.expand(form[2], env)
    if isinstance(value, Form) and value and value[0].name not in ("TABLE", "LTABLE", "ITABLE",
                                                                    "PTABLE", "PLTABLE"):
        try:
            value = g.mdl.eval(value, env)
        except MDLError:
            pass
    g.constants[name] = (value, form.loc)
    if isinstance(value, int):
        g.mdl.globals[name] = value
    return name


@hook("PROPDEF")
def _propdef(g, form, env):
    name = form[1]
    g.propdefs[name] = (form[2:], form.loc)
    g.note_prop(name)
    return name


@hook("DIRECTIONS")
def _directions(g, form, env):
    for d in form[1:]:
        g.directions.append(d)
        g.word(d, "DIRECTION")
    return T


@hook("BUZZ")
def _buzz(g, form, env):
    for w in form[1:]:
        w = _name(w)
        g.buzz.append(w)
        g.word(w, "BUZZ")
    return T


@hook("SYNONYM")
def _synonym(g, form, env):
    g.synonyms.append((_name(form[1]), [_name(w) for w in form[2:]]))
    return T


@hook("ADJ-SYNONYM", "VERB-SYNONYM", "PREP-SYNONYM", "DIR-SYNONYM")
def _typed_synonym(g, form, env):
    g.synonyms.append((_name(form[1]), [_name(w) for w in form[2:]]))
    return T


@hook("BIT-SYNONYM")
def _bit_synonym(g, form, env):
    g.bit_synonyms.append((form[1], list(form[2:])))
    return T


@hook("SYNTAX")
def _syntax(g, form, env):
    items = list(form[1:])
    verb = _name(items[0])
    parts = []
    i = 1
    while i < len(items) and items[i] is not A("="):
        x = items[i]
        if x is A("OBJECT"):
            find = None
            locs = None
            while i + 1 < len(items) and isinstance(items[i + 1], MList):
                lst = items[i + 1]
                if lst and lst[0] is A("FIND"):
                    find = lst[1]
                    g.note_flag(find)
                else:
                    locs = list(lst)
                i += 1
            parts.append(("obj", find, locs))
        else:
            parts.append(("prep", _name(x)))
            g.word(_name(x), "PREPOSITION")
        i += 1
    rest = items[i + 1:]
    action = rest[0] if rest else None
    preaction = rest[1] if len(rest) > 1 and rest[1] is not None else None
    if isinstance(preaction, Form) and not preaction:  # <> = no preaction
        preaction = None
    action_name = rest[2] if len(rest) > 2 else None
    g.syntaxes.append(SyntaxDef(verb, parts, action, preaction, action_name, form.loc))
    return T


@hook("VOC")
def _voc(g, form, env):
    w = _name(g.mdl.eval(form[1], env))
    pos = form[2].name if len(form) > 2 and isinstance(form[2], Atom) else None
    g.word(w, pos)
    return Form([A("GVAL"), A("W?" + w.name)])


@hook("FREQUENT-WORDS?", "ID", "ZSTR-OFF", "ZSTR-ON", "LONG-WORDS?", "ORDER-OBJECTS?",
      "ORDER-TREE?", "ORDER-FLAGS?", "ORDER-PROPS?", "COMPILATION-FLAG", "SETG20",
      "FUNNY-GLOBALS?", "NEVER-ZAP-TO-SOURCE-DIRECTORY?", "TELL-TOKENS", "ADD-TELL-TOKENS",
      "SPLICE", "ZZPACKAGE", "ENDZPACKAGE", "PUTPROP", "CHECKPOINT", "PRINC-SYNTAX",
      "SNAME", "DEFAULTS-DEFINED", "NEW-ADD-WORD", "DEFAULT-DEFINITION",
      "DELAY-DEFINITION", "REPLACE-DEFINITION")
def _ignored(g, form, env):
    return T


@hook("ZSTART")
def _zstart(g, form, env):
    g.zstart = form[1]
    return T


@hook("IFFLAG")
def _ifflag(g, form, env):
    # <IFFLAG (FLAG expr) (ELSE expr)> -- compile-time choice
    for clause in form[1:]:
        if not isinstance(clause, MList) or not clause:
            continue
        test = clause[0]
        ok = test is A("ELSE") or test is T
        if not ok and isinstance(test, (Atom, str)):
            ok = truthy(g.mdl.globals.get(_name(test), FALSE))
        elif not ok:
            ok = truthy(g.mdl.eval(test, env))
        if ok:
            v = T
            for e in clause[1:]:
                v = g.mdl.eval(e, env)
            return v
    return FALSE


def load(path):
    return Game(Sources(path)).load()
