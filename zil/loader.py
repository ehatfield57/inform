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
        self.extras = {}  # compiler output kept with the source: *.zap, *.record
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
        elif ext.lower() in (".zap", ".xzap", ".record"):
            # The compiler's own output: evidence for how it laid things out.
            self.extras[base.lower()] = text

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
        self.read_warnings = []    # oddities the reader skipped over
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
        self.tell_tokens = None    # from <TELL-TOKENS ...>, for the built-in TELL

    # ------------------------------------------------------------ loading
    def load(self, zilch=None):
        main = self.sources.main_file()
        self.insert_file(main)
        self.add_implied_objects()
        self.zilch = detect_zilch(self, zilch)
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
        for obj in read_text(text, display, self.read_warnings):
            self.top_level(obj)

    def top_level(self, obj):
        try:
            if isinstance(obj, ReadEval):
                # %<...> at top level: whatever form it produces is compiled too.
                v = self.mdl.eval(obj.obj, self.global_env)
                if not obj.discard and isinstance(v, (Form, MList, Vector)):
                    self.top_level(v)       # a form, or a list of them (Hollywood Hijinx)
            elif isinstance(obj, Form):
                self.mdl.eval(obj, self.global_env)
            elif isinstance(obj, (Vector, MList)):
                # MDL evaluates what's inside: Witness wraps some ROOMs in [ ... ]
                for item in obj:
                    self.top_level(item)
            # strings and other bare objects at top level are comments
        except MDLError as e:
            loc = getattr(obj, "loc", None)
            raise LoadError(f"{loc}: {e}") from None

    def add_implied_objects(self):
        """An object named as a location, (IN X), but never defined: ZILCH made an
        empty object X (Witness r23's DRIVEWAY-GATE, in its witnessdat.zap)."""
        for name, od in list(self.objects.items()):
            for p in od.props:
                if (p and p[0].name in ("IN", "LOC") and len(p) == 2 and isinstance(p[1], Atom)
                        and p[1] not in self.objects):
                    self.objects[p[1]] = ObjectDef(p[1], False, [], od.loc, self.next_order())
                    self.read_warnings.append(
                        f"{od.loc}: {p[1].name} is never defined; made an empty object, as ZILCH did")

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
            v = self.expand(x.value, env)          # #BYTE %<+ 2 8 128> (Spellbreaker)
            return Hashed(x.type, v, x.loc) if v is not _DROP else x
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
    if isinstance(x, int):
        return A(str(x))          # a number used as a word, e.g. (ADJECTIVE 1)
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
        # A value that calls an MDL function, like Spellbreaker's
        # (THINGS <PSEUDO (DIMITHIO BORPHEE ANSWER-PSEUDO) ...>), runs now, while
        # loading, so the words it adds with VOC reach the dictionary.
        if any(isinstance(v, Form) and v and isinstance(v[0], Atom)
               and isinstance(g.mdl.globals.get(v[0]), Function)
               and not g.mdl.globals[v[0]].is_macro for v in p[1:]):
            p = MList([p[0]] + [g.mdl.eval(v, env) if isinstance(v, Form) and v and
                                isinstance(g.mdl.globals.get(v[0]), Function) else v
                                for v in p[1:]], p.loc)
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
        elif pname.name == "PSEUDO" and len(p) > 1 and isinstance(p[1], str):
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


POS_NAMES = {"NOUN": "OBJECT", "OBJECT": "OBJECT", "ADJ": "ADJECTIVE", "ADJECTIVE": "ADJECTIVE",
             "VERB": "VERB", "PREP": "PREPOSITION", "PREPOSITION": "PREPOSITION",
             "DIR": "DIRECTION", "DIRECTION": "DIRECTION", "BUZZ": "BUZZ", "BUZZ-WORD": "BUZZ"}


@hook("ADJ-SYNONYM", "VERB-SYNONYM", "PREP-SYNONYM", "DIR-SYNONYM")
def _typed_synonym(g, form, env):
    # <VERB-SYNONYM HAND GIVE ...> copies only the verb meaning: HAND is also a noun,
    # but GIVE isn't (Stationfall's dictionary).
    pos = {"ADJ": "ADJECTIVE", "VERB": "VERB", "PREP": "PREPOSITION",
           "DIR": "DIRECTION"}[form[0].name.split("-")[0]]
    g.synonyms.append((_name(form[1]), [_name(w) for w in form[2:]], pos))
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
    if i < len(items) and isinstance(items[i], MList):
        # <SYNTAX GO (DUCK) UNDER OBJECT ...>: DUCK is another word for this verb (in
        # Plundered Hearts' dictionary GO, DUCK and WADE share one verb number).
        g.synonyms.append((verb, [_name(w) for w in items[i]], "VERB"))
        i += 1
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
    pos = g.mdl.eval(form[2], env) if len(form) > 2 else None
    pos = POS_NAMES.get(pos.name, pos.name) if isinstance(pos, Atom) else None
    # With no part of speech ZILCH made it an object word (Spellbreaker's dictionary
    # has DIMITHIO as an object word, from <VOC "DIMITHIO">).
    g.word(w, pos or "OBJECT")
    return Form([A("GVAL"), A("W?" + w.name)])


@hook("FREQUENT-WORDS?", "ID", "ZSTR-OFF", "ZSTR-ON", "LONG-WORDS?", "ORDER-OBJECTS?",
      "ORDER-TREE?", "ORDER-FLAGS?", "ORDER-PROPS?", "COMPILATION-FLAG", "SETG20",
      "FUNNY-GLOBALS?", "NEVER-ZAP-TO-SOURCE-DIRECTORY?",
      "SPLICE", "ZZPACKAGE", "ENDZPACKAGE", "PUTPROP", "CHECKPOINT", "PRINC-SYNTAX",
      "SNAME", "DEFAULTS-DEFINED", "NEW-ADD-WORD", "DEFAULT-DEFINITION",
      "DELAY-DEFINITION", "REPLACE-DEFINITION")
def _ignored(g, form, env):
    return T


@hook("LINK", "ROOT")
def _link(g, form, env):
    # <LINK '<INSERT-FILE "PARLOR" T> "P" <ROOT>>: a typing shortcut for the MDL
    # command line (Hollywood Hijinx). Nothing to do with the game.
    return T


@hook("TELL-TOKENS", "ADD-TELL-TOKENS")
def _tell_tokens(g, form, env):
    """The newer ZILCH's built-in TELL: <TELL-TOKENS (CRLF CR) <CRLF>  D * <PRINTD .X> ...>.
    Each entry is one or more names, then a pattern (* takes an argument, ,PRSO must
    appear literally), then the form to use, with .X standing for the argument."""
    entries = []
    items = list(form[1:])
    i = 0
    while i < len(items):
        names = items[i]
        names = [n for n in names] if isinstance(names, MList) else [names]
        i += 1
        pattern = []
        while i < len(items) and not (isinstance(items[i], Form) and items[i]
                                      and items[i][0] not in (A("GVAL"), A("LVAL"))):
            pattern.append(items[i])
            i += 1
        expansion = items[i] if i < len(items) else None
        i += 1
        entries.append(([n.name for n in names if isinstance(n, Atom)], pattern, expansion))
    if form[0].name == "TELL-TOKENS":
        g.tell_tokens = entries
    else:
        g.tell_tokens = entries + (g.tell_tokens or [])
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


# ---------------------------------------------------------------- compiler generations

class Zilch:
    """How the compiler that built a game behaved, where compilers differed.

    generation "new": the MIM-based ZILCH of 1985 on (Zork I r119, Zork II r63).
    generation "old": the earlier ZILCH (Zork III r15): each container's first-defined
    object stays first, and the others follow newest first.
    """

    def __init__(self, generation, reason):
        self.generation = generation
        self.reason = reason
        self.tree_first_stays = generation == "old"

    def __repr__(self):
        return f"ZILCH {self.generation} ({self.reason})"


def detect_zilch(game, forced=None):
    if forced:
        return Zilch(forced, "chosen with --zilch")
    ex = game.sources.extras
    dat = [t for n, t in ex.items() if n.endswith("dat.zap")]
    if dat:
        order = _tree_order_from_zap(game, dat[0])
        if order:
            return Zilch(order, "object tree in the compiler's data assembly")
    for n, t in ex.items():
        if n.endswith(".record"):
            head = t[:200]
            if "MIM" in head or "ZILCH of" in head:
                return Zilch("new", "compiler named in " + n)
    # No direct evidence. Sources in the older style (MDL memory set-up with <BLOAT ...>
    # in the main file) were built by the older ZILCH in every zip whose .zap shows the
    # answer (the two exceptions have their own .zap). Some older-compiler games lack
    # it (Spellbreaker), so this is only a guess; --zilch overrides it.
    main = game.file_order[0] if game.file_order else None
    if main and "<BLOAT" in game.texts[main]:
        return Zilch("old", "guess: older-style source (<BLOAT> in the main file)")
    return Zilch("new", "default")


def _tree_order_from_zap(game, text):
    """Compare the compiled object tree with the source's definition order.
    Returns "old", "new" or None if it can't tell."""
    links = {}
    for m in re.finditer(r"^\s*\.OBJECT\s+([^\n;]+)", text, re.M):
        f = [x.strip() for x in m.group(1).split(",")]
        if len(f) >= 5:
            links[f[0]] = (f[-4], f[-3], f[-2])          # parent, sibling, child
    if not links:
        return None
    defined = [n.name for n in game.objects]
    pos = {n: i for i, n in enumerate(defined)}
    votes = {"old": 0, "new": 0}
    for name, (parent, sib, child) in links.items():
        kids = []
        c = child
        while c and c != "0" and c in links and len(kids) < 500:
            kids.append(c)
            c = links[c][1]
        kids = [k for k in kids if k in pos]
        if len(kids) < 3:
            continue
        by_def = sorted(kids, key=lambda k: pos[k])
        if kids == list(reversed(by_def)):
            votes["new"] += 1
        elif kids == [by_def[0]] + list(reversed(by_def[1:])):
            votes["old"] += 1
    if votes["old"] == votes["new"]:
        return None
    return "old" if votes["old"] > votes["new"] else "new"


def load(path, zilch=None):
    return Game(Sources(path)).load(zilch)
