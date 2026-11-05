"""Lay out a loaded game's data in Z-machine memory.

Routines stay as source trees (see compiler.py), but everything the game reads
as bytes -- objects, properties, globals, tables, the dictionary and the
parser's syntax tables -- is placed in a real byte array, the way ZILCH would
have, so routines like the parser that poke at bytes work unchanged.

Routines and strings get "packed addresses" (just numbers) in their own ranges
so they can be stored in properties and tables like the real thing.
"""

from .reader import Atom, Form, MList, Vector, Hashed, Char, ReadEval, _Seq, mdl_repr
from .mdl import MFalse, truthy, MDLError
from . import ztext

A = Atom
ROUTINE_BASE = 0x1000      # packed addresses for routines start here
STRING_BASE = 0x3000       # ... and for strings here

PS = {"OBJECT": 128, "VERB": 64, "ADJECTIVE": 32, "DIRECTION": 16, "PREPOSITION": 8,
      "BUZZ-WORD": 4, "BUZZ": 4}
P1 = {"OBJECT": 0, "VERB": 1, "ADJECTIVE": 2, "DIRECTION": 3, "PREPOSITION": 0, "BUZZ": 0}


class BuildError(Exception):
    pass


class Word:
    __slots__ = ("text", "key", "pos", "addr")

    def __init__(self, text, key):
        self.text, self.key = text, key
        self.pos = {}       # part of speech -> (order, value)
        self.addr = 0


class Image:
    """The laid-out game. Built from a loader.Game by build()."""

    def __init__(self, game):
        self.game = game
        self.version = game.version
        self.mem = bytearray(64)
        self.objects = {}          # Atom -> number
        self.object_names = [None]  # number -> Atom
        self.routine_addr = {}     # Atom -> packed
        self.routine_by_addr = {}  # packed -> RoutineDef
        self.strings = []          # index -> text
        self.string_index = {}     # text -> packed
        self.global_num = {}       # Atom -> variable number (16..)
        self.global_names = {}     # variable number -> Atom
        self.flags = {}            # Atom -> bit
        self.props = {}            # Atom -> number
        self.prop_names = {}
        self.consts = {}           # Atom -> int (every named constant)
        self.words = {}            # key bytes -> Word
        self.word_by_addr = {}
        self.tables = []           # (address, size, label, loc)
        self.verbs = {}            # Atom -> verb number
        self.actions = {}          # action Atom (V?..) -> number
        self.preps = {}
        self.adjs = {}
        self.buzz = {}
        self.warnings = list(game.read_warnings)
        self.static_base = 0

    # ------------------------------------------------------------ memory
    def alloc(self, data, label=None, loc=None):
        addr = len(self.mem)
        self.mem += bytes(data)
        if len(self.mem) > 0xFFFF:
            raise BuildError("game data doesn't fit in 64K")
        if label is not None:
            self.tables.append((addr, len(data), label, loc))
        return addr

    def ww(self, a, v):
        self.mem[a] = (v >> 8) & 0xFF
        self.mem[a + 1] = v & 0xFF

    def rw(self, a):
        return (self.mem[a] << 8) | self.mem[a + 1]

    # ------------------------------------------------------------ strings
    def string(self, text):
        text = zil_text(text)
        p = self.string_index.get(text)
        if p is None:
            p = STRING_BASE + len(self.strings)
            self.strings.append(text)
            self.string_index[text] = p
        return p

    def string_at(self, packed):
        i = packed - STRING_BASE
        if 0 <= i < len(self.strings):
            return self.strings[i]
        return None

    # ------------------------------------------------------------ words
    def word(self, text):
        key = ztext.encode_word(text, self.version)
        w = self.words.get(key)
        if w is None:
            w = Word(text.lower(), key)
            self.words[key] = w
        return w

    def word_addr(self, atom_or_text):
        t = atom_or_text.name if isinstance(atom_or_text, Atom) else atom_or_text
        return self.word(t).addr


CRLF_CHAR = ["|"]      # the line-break character; <SETG CRLF-CHARACTER !\~> changes it


def zil_text(s):
    """ZIL string -> printed text: | is a line break; a line break in the source is
    a space."""
    bar = CRLF_CHAR[0]
    s = s.replace("\r\n", "\n")
    if bar != "|":
        s = s.replace("|", "\0").replace(bar, "|")   # use | below, keep real |s
    s = s.replace("|\n", "|")        # a | at the end of a source line is one line break
    # ZILCH squeezed ".  " typed in the source to ". ", before line breaks became
    # spaces (so ". " at the end of a source line still prints two spaces).
    s = s.replace(".  ", ". ")
    s = s.replace("\n", " ")
    return s.replace("|", "\n").replace("\0", "|")


def build(game, serial=None):
    cc = game.mdl.globals.get(Atom("CRLF-CHARACTER"))
    CRLF_CHAR[0] = cc.c if isinstance(cc, Char) else "|"
    img = Image(game)
    b = Builder(img, game)
    b.run(serial)
    img.builder = b          # the compiler uses it to resolve names in routines
    return img


class Builder:
    def __init__(self, img, game):
        self.img = img
        self.g = game
        self.undefined = set()
        self.v = game.version

    def warn(self, msg):
        self.img.warnings.append(msg)

    # ------------------------------------------------------------ main
    def run(self, serial):
        img, g = self.img, self.g
        self.number_flags()
        self.number_props()
        self.number_objects()
        self.number_routines()
        self.number_globals()
        self.collect_words()
        self.number_vocab()
        self.define_constants()
        self.layout_dictionary()
        # globals table
        self.globals_addr = img.alloc(bytes(2 * 240))
        # object table: defaults + entries; filled in after the property tables exist
        nprops = 31 if self.v <= 3 else 63
        esize = 9 if self.v <= 3 else 14
        self.objtab = img.alloc(bytes(2 * nprops + esize * len(img.object_names[1:])))
        self.prop_defaults()
        self.layout_objects()
        self.layout_syntax()
        self.resolve_constant_tables()
        self.init_globals()
        self.write_header(serial)

    # ------------------------------------------------------------ numbering
    def number_flags(self):
        img, g = self.img, self.g
        limit = 32 if self.v <= 3 else 48
        # Names declared with <BIT-SYNONYM main ...> share main's bit, so they don't
        # take a number of their own (Hollywood Hijinx has 21 of them).
        aliases = {s_ for _, syns in g.bit_synonyms for s_ in syns}
        flags = [f for f in g.flags if f not in aliases]
        for name, _ in g.bit_synonyms:
            if name not in flags:
                flags.append(name)
        if len(flags) > limit:
            raise BuildError(f"too many flags ({len(flags)} > {limit})")
        # ZILCH gave the highest numbers to the first flags met.
        for i, f in enumerate(flags):
            img.flags[f] = limit - 1 - i
        for name, syns in g.bit_synonyms:
            for s in syns:
                img.flags[s] = img.flags[name]
        for f, n in img.flags.items():
            img.consts[f] = n

    def number_props(self):
        img, g = self.img, self.g
        top = 31 if self.v <= 3 else 63
        n = top
        for d in g.directions:
            img.props[d] = n
            n -= 1
        img.low_direction = n + 1
        img.direction_numbers = [img.props[d] for d in g.directions]   # MAP-DIRECTIONS order
        for p in g.properties:
            if p in img.props:
                continue
            if n < 1:
                raise BuildError("too many properties")
            img.props[p] = n
            n -= 1
        self.next_prop = n
        for p, num in img.props.items():
            img.prop_names[num] = p

    def prop_number(self, atom):
        img = self.img
        if atom not in img.props:
            if self.next_prop < 1:
                raise BuildError("too many properties")
            img.props[atom] = self.next_prop
            img.prop_names[self.next_prop] = atom
            self.next_prop -= 1
        return img.props[atom]

    def number_objects(self):
        img, g = self.img, self.g
        # Numbered in reverse order of definition. That is close to what the older ZILCH
        # did (Zork III r15, Witness, Suspended .zap files); the later one used hash order.
        # It matters: objects defined early (NOT-HERE-OBJECT and other globals) get high
        # numbers, so they can't be mistaken for a direction's property number (20-31)
        # when a game compares PRSO with them during a walk (Enchanter does).
        for i, name in enumerate(reversed(list(g.objects)), 1):
            img.objects[name] = i
            img.object_names.append(name)
        limit = 255 if self.v <= 3 else 65535
        if len(img.object_names) - 1 > limit:
            raise BuildError("too many objects")

    def number_routines(self):
        img, g = self.img, self.g
        for i, (name, rd) in enumerate(g.routines.items()):
            p = ROUTINE_BASE + i
            img.routine_addr[name] = p
            img.routine_by_addr[p] = rd

    def number_globals(self):
        img, g = self.img, self.g
        names = list(g.globals)
        if self.v <= 3:
            # The v3 status line reads globals 0-2: location, score, moves. ZILCH made
            # them even when the source doesn't declare them (Planetfall never declares
            # MOVES; its planetfalldat.zap has HERE, SCORE, MOVES first).
            first = [A(n) for n in ("HERE", "SCORE", "MOVES")]
            for n in first:
                if n not in g.globals:
                    g.globals[n] = (0, None)
            names = first + [n for n in names if n not in first]
        if len(names) > 240:
            raise BuildError("too many globals")
        for i, n in enumerate(names):
            img.global_num[n] = 16 + i
            img.global_names[16 + i] = n

    # ------------------------------------------------------------ vocabulary
    def collect_words(self):
        """Find every W?word mentioned in code or data, so the dictionary has it."""
        g = self.g
        self.extra_words = []

        def walk(x):
            if isinstance(x, Atom):
                if x.name.startswith("W?") and not _unspellable(x.name[2:]):
                    self.extra_words.append(word_text(x.name[2:]))
            elif isinstance(x, (list, tuple)):
                for y in x:
                    walk(y)
            elif isinstance(x, Hashed):
                walk(x.value)

        for rd in g.routines.values():
            walk(rd.body)
            walk(rd.params)
        for v, _ in g.globals.values():
            walk(v)
        for v, _ in g.constants.values():
            walk(v)
        for od in g.objects.values():
            walk(od.props)

    def number_vocab(self):
        img, g = self.img, self.g
        late = 10 ** 9   # verbs are entered after everything else
        counters = {"ADJECTIVE": 255, "PREPOSITION": 255, "BUZZ": 255}
        numbered = {"ADJECTIVE": img.adjs, "PREPOSITION": img.preps, "BUZZ": img.buzz}

        def add(text, pos, value, order):
            w = img.word(text)
            if pos not in w.pos:
                w.pos[pos] = (order, value)
            return w

        for order, atom, pos, extra in g.word_events:
            text = atom.name
            key = img.word(text).key
            if pos in numbered:
                table = numbered[pos]
                if key not in table:
                    if counters[pos] < 1:
                        raise BuildError(f"too many {pos.lower()}s")
                    table[key] = counters[pos]
                    counters[pos] -= 1
                add(text, pos, table[key], order)
            elif pos == "DIRECTION":
                add(text, pos, img.props[atom], order)
            elif pos == "OBJECT":
                add(text, pos, 1, order)
            elif pos == "VERB":
                pass
            else:
                img.word(text)
        # Verbs and actions, from the syntax lines.
        vnum = 255
        anum = 0
        self.action_routines = []   # action number -> (action Atom, preaction Atom or None)
        for i, sd in enumerate(g.syntaxes):
            key = img.word(sd.verb.name).key
            if key not in img.verbs:
                img.verbs[key] = vnum
                vnum -= 1
            add(sd.verb.name, "VERB", img.verbs[key], late + i)
            act = action_name(sd)
            if act not in img.actions:
                img.actions[act] = anum
                self.action_routines.append([sd.action, sd.preaction])
                anum += 1
            else:
                slot = self.action_routines[img.actions[act]]
                if slot[1] is None and sd.preaction is not None:
                    slot[1] = sd.preaction
        for t in self.extra_words:
            img.word(t)
        # Synonyms share their main word's entry.
        self.synonym_of = {}       # synonym key -> (main key, only this part of speech)
        for entry in g.synonyms:
            main, syns = entry[0], entry[1]
            only = entry[2] if len(entry) > 2 else None
            mw = img.word(main.name)
            for s in syns:
                sw = img.word(s.name)
                if sw is not mw:
                    self.synonym_of[sw.key] = (mw.key, only)
        # Verb synonyms also get the verb number (for ACT? lookups).

    def define_constants(self):
        img, g = self.img, self.g
        c = img.consts
        for name, num in img.props.items():
            c[A("P?" + name.name)] = num
        c[A("LOW-DIRECTION")] = img.low_direction
        # ZILCH filled in the number of objects, whatever the source says (Plundered
        # Hearts: <CONSTANT LAST-OBJECT 0> ;"ZILCH should stick the # of the last object
        # here"; its .zap has LAST-OBJECT=223).
        c[A("LAST-OBJECT")] = len(img.object_names) - 1
        for pos, v in PS.items():
            c[A("PS?" + pos)] = v
        for pos, v in P1.items():
            c[A("P1?" + pos)] = v
        for key, n in img.verbs.items():
            pass
        for sd in g.syntaxes:
            c[A("ACT?" + sd.verb.name)] = img.verbs[img.word(sd.verb.name).key]
        for main, syns, *_ in g.synonyms:
            k = img.word(main.name).key
            if k in img.verbs:
                for s in syns:
                    c.setdefault(A("ACT?" + s.name), img.verbs[k])
        for act, n in img.actions.items():
            c[A("V?" + act.name)] = n
        for w in img.words.values():
            if "PREPOSITION" in w.pos:
                c[A("PR?" + w.text.upper())] = w.pos["PREPOSITION"][1]
        for main, syns, *_ in g.synonyms:
            mk = img.word(main.name).key
            if mk in img.preps:
                for s in syns:
                    c.setdefault(A("PR?" + s.name), img.preps[mk])
        for e in g.word_events:
            if e[2] == "PREPOSITION":
                c.setdefault(A("PR?" + e[1].name), img.preps[img.word(e[1].name).key])

    def layout_dictionary(self):
        img = self.img
        seps = [ord(ch) for ch in ".,\""]
        keys = sorted(img.words)
        elen = 7 if self.v <= 3 else 9
        data = bytearray([len(seps)] + seps + [elen]) + bytes([len(keys) >> 8, len(keys) & 0xFF])
        img.dict_addr = img.alloc(data)
        base = len(img.mem)
        img.alloc(bytes(elen * len(keys)))
        for i, k in enumerate(keys):
            w = img.words[k]
            w.addr = base + i * elen
            img.word_by_addr[w.addr] = w
        for i, k in enumerate(keys):
            w = img.words[k]
            src = w
            if k in self.synonym_of:
                # A synonym gets its main word's parts of speech on top of its own
                # (only one of them, for VERB-SYNONYM and the like).
                mk, only = self.synonym_of[k]
                main = img.words[mk]
                src = Word(w.text, k)
                src.pos = dict(w.pos)
                src.pos.update({p_: v for p_, v in main.pos.items() if only in (None, p_)})
            a = w.addr
            img.mem[a: a + len(k)] = k
            flags = 0
            for pos in src.pos:
                flags |= PS[pos]
            ordered = sorted(src.pos.items(), key=lambda kv: kv[1][0])
            if len(ordered) > 2:
                # Only two value slots. An object word's value is never used, so it gives
                # up its slot first (Stationfall's "drill" keeps adjective and verb).
                ordered = [kv for kv in ordered if kv[0] != "OBJECT"] or ordered
            vals = [v for _, (_, v) in ordered]
            p1 = P1[ordered[0][0]] if ordered else 0
            off = len(k)
            img.mem[a + off] = flags | p1
            img.mem[a + off + 1] = (vals[0] if vals else 0) & 0xFF
            img.mem[a + off + 2] = (vals[1] if len(vals) > 1 else 0) & 0xFF
            # A synonym is a copy of its main word.
            if src is not w:
                w.pos = dict(src.pos)
        for w in img.words.values():
            img.consts[A("W?" + w.text.upper())] = w.addr
        for name, text in SPECIAL_WORDS.items():
            if text in [w.text for w in img.words.values()]:
                img.consts[A("W?" + name)] = img.word(text).addr
        # Atom spellings that differ from the stored (truncated) text
        for atom_name in list(Atom._table):
            pass

    def word_const(self, name):
        return self.img.word(name).addr

    # ------------------------------------------------------------ values
    def resolve(self, x, ctx="value"):
        """A compile-time value (global initialiser, table element, property value)."""
        img = self.img
        if isinstance(x, bool):
            return int(x)
        if isinstance(x, int):
            return x & 0xFFFF
        if isinstance(x, str):
            return img.string(x)
        if isinstance(x, Char):
            return ord(x.c)
        if isinstance(x, MFalse):
            return 0
        if isinstance(x, Atom):
            return self.resolve_atom(x)
        if isinstance(x, Form):
            if not x:
                return 0
            head = x[0]
            if head is A("GVAL") or head is A("QUOTE"):
                return self.resolve(x[1], ctx)
            if isinstance(head, Atom) and head.name in TABLE_FORMS:
                return self.table(x)
            try:
                v = self.g.mdl.eval(x, self.g.global_env)
            except MDLError as e:
                raise BuildError(f"{x.loc}: can't work out {mdl_repr(x)} when loading: {e}")
            return self.resolve(v, ctx)
        if isinstance(x, Hashed):
            return self.resolve(x.value, ctx)
        if isinstance(x, ReadEval):
            return self.resolve(self.g.mdl.eval(x.obj, self.g.global_env), ctx)
        raise BuildError(f"can't use {mdl_repr(x)} as a value")

    def resolve_atom(self, a):
        img = self.img
        if a is A("T"):
            return 1
        if a in img.objects:
            return img.objects[a]
        if a in img.routine_addr:
            return img.routine_addr[a]
        if a in self.g.globals:
            # A global's name inside data means its (initial) value.
            return self.global_value(a)
        if a in img.consts:
            return img.consts[a]
        if a in self.g.constants:
            v = self.resolve(self.g.constants[a][0])
            img.consts[a] = v
            return v
        if a.name.startswith("A?"):
            # A?word: the word's adjective number (v3 ADJECTIVE properties hold these)
            key = img.word(word_text(a.name[2:])).key
            if key in img.adjs:
                return img.adjs[key]
        if a.name.startswith("W?") and not _unspellable(a.name[2:]):
            return img.word(word_text(a.name[2:])).addr
        mv = self.g.mdl.globals.get(a)
        if isinstance(mv, (int, str)) or isinstance(mv, MFalse):
            return self.resolve(mv)
        if a.name.startswith("P?"):
            return self.prop_number(A(a.name[2:]))
        # Never defined. ZILCH passed the name on to its assembler, which warned
        # "global undefined" and used 0 (see Deadline r28's deadline.errors).
        if a not in self.undefined:
            self.undefined.add(a)
            self.warn(f"{a.name} is never defined; using 0, as Infocom's assembler did")
        return 0

    def object_number(self, o):
        """An object named in data; one that was never defined becomes 0, as the
        assembler did with any undefined name."""
        if o in self.img.objects:
            return self.img.objects[o]
        return self.resolve_atom(o)

    def is_object(self, x):
        if isinstance(x, Form) and x and x[0] is A("GVAL"):
            x = x[1]
        return isinstance(x, Atom) and x in self.img.objects

    # ------------------------------------------------------------ tables
    def table(self, form):
        """<TABLE ...>, <LTABLE ...>, <ITABLE ...>, <PTABLE ...>: allocate, return address."""
        head = form[0].name
        items = list(form[1:])
        flags = set()
        if head in ("LTABLE", "PLTABLE"):
            flags.add("LENGTH")
        if head in ("PTABLE", "PLTABLE"):
            flags.add("PURE")
        count = None
        if head == "ITABLE":
            # <ITABLE [NONE|BYTE|WORD] count [(flags)] init...>
            old_kind = None
            if items and isinstance(items[0], Atom) and items[0].name in ("NONE", "BYTE", "WORD"):
                # Old form <ITABLE BYTE 120>: 120 words; BYTE/WORD puts the count in
                # the first byte/word (checked against Zork III r15's .zap).
                old_kind = items.pop(0).name
            count = self.resolve(items.pop(0))
        if items and isinstance(items[0], MList):
            for f in items.pop(0):
                if isinstance(f, Atom):
                    flags.add(f.name)
        default_byte = "BYTE" in flags or "STRING" in flags
        data = bytearray()

        def emit(x):
            if isinstance(x, Form) and len(x) >= 2 and x[0] in (A("BYTE"), A("WORD")):
                # newer spelling: <BYTE 0> = #BYTE 0; <BYTE ,X-S ,X-E> is one byte with
                # those bits together (Hollywood Hijinx's hedge maze table)
                v = 0
                for y in x[1:]:
                    v |= self.resolve(y)
                x = Hashed(x[0], v, x.loc)
            if isinstance(x, Hashed) and x.type.name == "BYTE":
                data.append(self.resolve(x.value) & 0xFF)
            elif isinstance(x, Hashed) and x.type.name == "WORD":
                v = self.resolve(x.value)
                data.extend([(v >> 8) & 0xFF, v & 0xFF])
            elif isinstance(x, str) and "STRING" in flags:
                data.extend(ord(c) for c in zil_text(x))
            elif default_byte:
                data.append(self.resolve(x) & 0xFF)
            else:
                v = self.resolve(x)
                data.extend([(v >> 8) & 0xFF, v & 0xFF])

        prefix = bytearray()
        if head == "ITABLE":
            pattern = items or [0]
            for _ in range(count):
                for x in pattern:
                    emit(x)
            if old_kind == "BYTE" and data:
                data[0] = count & 0xFF
            elif old_kind == "WORD" and len(data) > 1:
                data[0:2] = bytes([(count >> 8) & 0xFF, count & 0xFF])
            if "LEXV" in flags:
                prefix = bytearray([count & 0xFF, 0])
            elif "LENGTH" in flags:
                prefix = bytearray([count & 0xFF]) if default_byte else bytearray([count >> 8, count & 0xFF])
        else:
            n = 0
            for x in items:
                emit(x)
                n += 1
            if "STRING" in flags:
                n = len(data)       # (LENGTH STRING): the length counts characters
            if "LENGTH" in flags:
                prefix = bytearray([n & 0xFF]) if default_byte else bytearray([n >> 8, n & 0xFF])
        label = mdl_repr(form)[:60]
        return self.img.alloc(prefix + data, label, form.loc)

    # ------------------------------------------------------------ objects
    def prop_defaults(self):
        img = self.img
        for name, (spec, loc) in self.g.propdefs.items():
            num = self.prop_number(name)
            if spec and not isinstance(spec[0], MList):
                img.ww(self.objtab + 2 * (num - 1), self.resolve(spec[0]))

    def layout_objects(self):
        img, g = self.img, self.g
        nprops = 31 if self.v <= 3 else 63
        esize = 9 if self.v <= 3 else 14
        entries = self.objtab + 2 * nprops
        img.obj_entries = entries
        img.obj_esize = esize
        parent = {}
        children = {}
        # Each object becomes the first child of its parent, in definition order.
        for name, od in g.objects.items():
            n = img.objects[name]
            for p in od.props:
                if is_location(p):
                    where = p[1]
                    if where not in img.objects:
                        raise BuildError(f"{od.loc}: {name.name} is in unknown object {where.name}")
                    parent[n] = img.objects[where]
        for name in g.objects:                  # definition order, whatever the numbers
            n = img.objects[name]
            if n in parent:
                children.setdefault(parent[n], []).insert(0, n)   # newest first
        if g.zilch.tree_first_stays:
            # Older ZILCH: the first object defined in a container stays first.
            for p_, kids in children.items():
                kids.insert(0, kids.pop())
        sib = {}
        first_child = {}
        for p, kids in children.items():
            first_child[p] = kids[0]
            for a, b in zip(kids, kids[1:]):
                sib[a] = b
        for name, od in g.objects.items():
            n = img.objects[name]
            e = entries + (n - 1) * esize
            attrs = 0
            desc = ""
            props = []
            for p in od.props:
                pn = p[0].name
                if pn == "FLAGS":
                    for f in p[1:]:
                        attrs |= 1 << img.flags[f]
                elif pn == "DESC":
                    desc = p[1]
                elif is_location(p):
                    continue
                else:
                    props.append((self.prop_number(p[0]), self.prop_value(od, p)))
            nattr = 4 if self.v <= 3 else 6
            for i in range(nattr):
                bits = 0
                for j in range(8):
                    if attrs & (1 << (8 * i + j)):     # attribute 0 is the top bit of byte 0
                        bits |= 0x80 >> j
                img.mem[e + i] = bits
            if self.v <= 3:
                img.mem[e + 4] = parent.get(n, 0)
                img.mem[e + 5] = sib.get(n, 0)
                img.mem[e + 6] = first_child.get(n, 0)
            else:
                img.ww(e + 6, parent.get(n, 0))
                img.ww(e + 8, sib.get(n, 0))
                img.ww(e + 10, first_child.get(n, 0))
            # property table
            name_bytes = ztext.encode(zil_text(desc)) if desc else b""
            pt = bytearray([len(name_bytes) // 2]) + name_bytes
            seen = set()
            for num, data in sorted(props, key=lambda x: -x[0]):
                if num in seen:
                    continue
                seen.add(num)
                if self.v <= 3:
                    if not 1 <= len(data) <= 8:
                        raise BuildError(f"{od.loc}: property {img.prop_names[num].name} of "
                                         f"{name.name} is {len(data)} bytes (1-8 allowed)")
                    pt.append(((len(data) - 1) << 5) | num)
                else:
                    if len(data) == 1:
                        pt.append(num)
                    elif len(data) == 2:
                        pt.append(0x40 | num)
                    else:
                        pt.append(0x80 | num)
                        pt.append(0x80 | (len(data) & 0x3F))
                pt += data
            pt.append(0)
            addr = img.alloc(pt)
            img.ww(e + esize - 2, addr)

    def prop_value(self, od, p):
        """The bytes of one property: (NAME values...)."""
        img = self.img
        name = p[0]
        vals = list(p[1:])
        v3 = self.v <= 3

        def word(v):
            return bytes([(v >> 8) & 0xFF, v & 0xFF])

        if name in self.g.directions:
            return self.exit_value(od, p)
        if vals and isinstance(vals[0], Atom) and vals[0].name in ("TO", "PER", "SORRY"):
            # Exit syntax on a property that isn't a direction, e.g. (ENTER PER MIRIN):
            # ZILCH stores it the same way as an exit.
            return self.exit_value(od, p)
        n = name.name
        if n == "SYNONYM":
            return b"".join(word(img.word(_txt(w)).addr) for w in vals)
        if n == "ADJECTIVE":
            if v3:
                return bytes(img.adjs[img.word(_txt(w)).key] for w in vals)
            return b"".join(word(img.word(_txt(w)).addr) for w in vals)
        if n == "GLOBAL":
            if v3:
                return bytes(self.object_number(o) for o in vals)
            return b"".join(word(self.object_number(o)) for o in vals)
        if n == "PSEUDO" and len(vals) % 2 == 0 and vals and isinstance(vals[0], str):
            out = b""
            for i in range(0, len(vals), 2):
                out += word(img.word(_txt(vals[i])).addr) + word(self.resolve(vals[i + 1]))
            return out
        if not vals:
            return word(0)
        out = b""
        for x in vals:
            if isinstance(x, Hashed) and x.type.name == "BYTE":
                out += bytes([self.resolve(x.value) & 0xFF])
            elif isinstance(x, Hashed) and x.type.name == "WORD":
                out += word(self.resolve(x.value))
            elif len(vals) == 1 and self.is_object(x) and v3:
                out += bytes([self.resolve(x)])
            else:
                out += word(self.resolve(x))
        return out

    def exit_value(self, od, p):
        """(DIR TO ROOM), (DIR "msg"), (DIR PER ROUTINE), (DIR TO ROOM IF FLAG [ELSE "msg"]),
        (DIR TO ROOM IF DOOR IS OPEN [ELSE "msg"]), (DIR SORRY "msg")."""
        img = self.img
        vals = list(p[1:])
        v3 = self.v <= 3

        def word(v):
            return bytes([(v >> 8) & 0xFF, v & 0xFF])

        def obj(o):
            n = self.object_number(o)
            return bytes([n]) if v3 else word(n)

        if vals and isinstance(vals[0], str):
            # (EAST "message") -- Hollywood Hijinx also writes (EAST "message" CR)
            return word(img.string(vals[0]))
        if len(vals) == 1 and isinstance(vals[0], int):
            # A direction property used to hold a number, e.g. Cutthroats' (NORTH 1)
            # "price - placeholder": ZILCH stored a plain word.
            return word(vals[0] & 0xFFFF)
        kw = vals[0].name if isinstance(vals[0], Atom) else None
        if kw == "SORRY":
            return word(img.string(vals[1]))
        if kw == "PER":
            return word(img.routine_addr[vals[1]]) + b"\0"
        if kw == "TO":
            room = vals[1]
            if len(vals) == 2:
                return obj(room)
            if vals[2] is A("IF"):
                cond = vals[3]
                msg = 0
                if len(vals) > 4 and vals[4] is A("IS"):
                    # door: IF DOOR IS OPEN [ELSE "msg"]
                    rest = vals[6:]
                    if rest and rest[0] is A("ELSE"):
                        msg = img.string(rest[1])
                    return obj(room) + obj(cond) + word(msg) + b"\0"
                rest = vals[4:]
                if rest and rest[0] is A("ELSE"):
                    msg = img.string(rest[1])
                flag = img.global_num[cond]
                return obj(room) + bytes([flag]) + word(msg)
        raise BuildError(f"{p.loc or od.loc}: can't understand exit {mdl_repr(p)}")

    # ------------------------------------------------------------ syntax
    def layout_syntax(self):
        img, g = self.img, self.g
        by_verb = {}
        for sd in g.syntaxes:
            by_verb.setdefault(img.verbs[img.word(sd.verb.name).key], []).append(sd)
        default_loc = 0
        LOCBITS = {"HELD": 128, "CARRIED": 64, "IN-ROOM": 32, "ON-GROUND": 16, "TAKE": 8,
                   "MANY": 4, "HAVE": 2}
        verb_tables = {}
        for vnum in sorted(by_verb, reverse=True):
            # ZILCH stored a verb's syntax lines last-defined first (see ST?PUSH in
            # Zork II r63's and Zork III r15's data assembly). The old parser takes the
            # first line that fits, so the order matters.
            lines = list(reversed(by_verb[vnum]))
            data = bytearray([len(lines)])
            for sd in lines:
                objs = [x for x in sd.parts if x[0] == "obj"]
                preps = [0, 0]
                fwim = [0, 0]
                locs = [default_loc, default_loc]
                k = 0
                for part in sd.parts:
                    if part[0] == "prep":
                        if k < 2:
                            preps[k] = img.preps[img.word(part[1].name).key]
                    else:
                        if part[1] is not None:
                            fwim[k] = img.flags[part[1]]
                        if part[2] is not None:
                            bits = 0
                            for b in part[2]:
                                bits |= LOCBITS[b.name]
                            locs[k] = bits
                        else:
                            locs[k] = DEFAULT_LOC
                        k += 1
                act = img.actions[action_name(sd)]
                data += bytes([len(objs), preps[0], preps[1], fwim[0], fwim[1], locs[0], locs[1],
                               act])
            verb_tables[vnum] = img.alloc(data, f"syntax for {img.word_by_addr and ''}{vnum}")
        lowest = min(verb_tables) if verb_tables else 255
        verbs = bytearray()
        for vnum in range(255, lowest - 1, -1):
            verbs += bytes([(verb_tables.get(vnum, 0) >> 8) & 0xFF, verb_tables.get(vnum, 0) & 0xFF])
        img.consts[A("VERBS")] = img.alloc(verbs, "VERBS")
        acts = bytearray()
        pre = bytearray()
        for action, preaction in self.action_routines:
            a = img.routine_addr.get(action, 0)
            if action not in img.routine_addr:
                self.warn(f"action routine {action.name} is not defined")
            acts += bytes([a >> 8, a & 0xFF])
            p_ = img.routine_addr.get(preaction, 0) if preaction else 0
            pre += bytes([p_ >> 8, p_ & 0xFF])
        img.consts[A("ACTIONS")] = img.alloc(acts, "ACTIONS")
        img.consts[A("PREACTIONS")] = img.alloc(pre, "PREACTIONS")
        preps = bytearray()
        count = 0
        for w in sorted(img.words.values(), key=lambda w: w.addr):
            if "PREPOSITION" in w.pos and w.key not in self.synonym_of:
                count += 1
                preps += bytes([w.addr >> 8, w.addr & 0xFF, 0, w.pos["PREPOSITION"][1]])
        img.consts[A("PREPOSITIONS")] = img.alloc(bytes([count >> 8, count & 0xFF]) + preps,
                                                  "PREPOSITIONS")

    # ------------------------------------------------------------ globals
    def resolve_constant_tables(self):
        for name, (value, loc) in self.g.constants.items():
            if name not in self.img.consts:
                self.img.consts[name] = self.resolve(value)

    def global_value(self, name):
        """A global's initial value, worked out once (so its table is built once)."""
        cache = self.__dict__.setdefault("_global_values", {})
        if name not in cache:
            value, loc = self.g.globals[name]
            cache[name] = None          # guards against a global defined by itself
            try:
                cache[name] = self.resolve(value)
            except BuildError as e:
                raise BuildError(f"{loc}: GLOBAL {name.name}: {e}")
        if cache[name] is None:
            raise BuildError(f"GLOBAL {name.name} refers to itself")
        return cache[name]

    def init_globals(self):
        img = self.img
        img.globals_addr = self.globals_addr
        for name in self.g.globals:
            n = img.global_num[name]
            img.ww(self.globals_addr + 2 * (n - 16), self.global_value(name))

    def write_header(self, serial):
        img, g = self.img, self.g
        m = img.mem
        m[0] = self.v
        if getattr(g, "time_game", False):
            m[1] |= 0x02
        rel = g.release or 0
        img.ww(2, rel)
        img.ww(8, img.dict_addr)
        img.ww(0x0A, self.objtab)
        img.ww(0x0C, self.globals_addr)
        img.ww(0x0E, len(m))
        s = (serial or g.serial or "000000")[:6].ljust(6, "0")
        m[0x12:0x18] = s.encode("ascii")


DEFAULT_LOC = 0

# Words that can't be spelled as atoms: ZILCH names them W?PERIOD etc.
SPECIAL_WORDS = {"PERIOD": ".", "COMMA": ",", "QUOTE": '"'}


def _unspellable(text):
    """Punctuation words like ".". W?. names the "." word only if the game's dictionary
    has one (Suspended's does); otherwise it was undefined (Deadline's errors file says
    "W?. global undefined"), so a W?. reference mustn't add the word."""
    return bool(text) and all(c in '.,"' for c in text)


def word_text(name):
    return SPECIAL_WORDS.get(name, name)


def is_location(p):
    """(IN ROOM) or (LOC ROOM) -- but (IN TO KITCHEN) is an exit."""
    return p[0].name in ("IN", "LOC") and len(p) == 2 and isinstance(p[1], Atom)


def action_name(sd):
    if sd.action_name is not None:
        return sd.action_name
    n = sd.action.name
    if n.startswith("V-"):
        n = n[2:]
    return A(n)


def _txt(w):
    if isinstance(w, int):
        return str(w)
    return w if isinstance(w, str) else w.name


TABLE_FORMS = {"TABLE", "LTABLE", "ITABLE", "PTABLE", "PLTABLE"}
