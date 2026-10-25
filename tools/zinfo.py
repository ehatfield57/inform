"""Shared helpers for the tools in this folder: reading story files, save files, objects,
properties, the dictionary and Z-strings.

This is a library, not a command. The other tools import it. It uses the ZMachine class
from ../zplay.py for decoding text, so this folder has to stay next to zplay.py.

Save files: two kinds are understood.
  - "zplay-1": written by the "save" command when you play with zplay.py.
  - "zplay-auto-1": written by zplay_auto.py (<story>.auto.sav) and by zrun.py --save.
Either can be passed wherever a tool takes --save. The tools only read the game's memory
from them, except zrun.py, which can also carry on playing from them.
"""

import base64
import json
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))      # the folder with zplay.py
import zplay                                    # noqa: E402


def machine(story, seed=1, script=None, width=80):
    """A ZMachine for `story` that types the lines in `script` (or nothing) as input."""
    screen = zplay.Screen(width, 24, False, list(script) if script else ["x"])
    return zplay.ZMachine(zplay.load_story(story), screen, story, seed)


def read_save(path):
    """Read a save file. Returns the decoded JSON dict, with 'dynamic' turned into bytes."""
    with open(path) as fh:
        d = json.load(fh)
    if d.get("format") not in ("zplay-1", "zplay-auto-1"):
        raise ValueError("%s isn't a zplay save file" % path)
    d["dynamic"] = zlib.decompress(base64.b64decode(d["dynamic"]))
    return d


class Story:
    """Read-only view of a story file's memory, optionally with a save file's memory laid
    over it (so objects, flags and variables are as they were in that saved game)."""

    def __init__(self, story_path, save_path=None):
        self.path = story_path
        self.zm = machine(story_path)
        self.mem = self.zm.mem
        if save_path:
            d = read_save(save_path)
            if list(d["story"]) != list(self.zm.story_id()):
                raise ValueError("%s was saved from a different game" % save_path)
            self.mem[:len(d["dynamic"])] = d["dynamic"]
        self.version = self.mem[0]
        # object table layout differs between version 1-3 and version 4 and later
        if self.version <= 3:
            self.ndefaults, self.entry, self.attr_bytes = 31, 9, 4
        else:
            self.ndefaults, self.entry, self.attr_bytes = 63, 14, 6
        self.objtab = self.rw(0x0A) + 2 * self.ndefaults
        self.globals = self.rw(0x0C)

    # ---- memory
    def rb(self, a):
        return self.mem[a]

    def rw(self, a):
        return (self.mem[a] << 8) | self.mem[a + 1]

    def glob(self, n):
        """Value of global variable Gn (G0 is the first global, i.e. variable 16)."""
        return self.rw(self.globals + 2 * n)

    def decode(self, addr):
        """(text, next address) of the Z-string at addr."""
        return self.zm.decode(addr)

    def unpack(self, packed):
        """Byte address of a packed (routine or string) address."""
        v = self.version
        return packed * (2 if v <= 3 else 4 if v <= 5 else 8)

    # ---- objects
    def _e(self, o):
        return self.objtab + self.entry * (o - 1)

    def parent(self, o):
        e = self._e(o)
        return self.mem[e + 4] if self.version <= 3 else self.rw(e + 6)

    def sibling(self, o):
        e = self._e(o)
        return self.mem[e + 5] if self.version <= 3 else self.rw(e + 8)

    def child(self, o):
        e = self._e(o)
        return self.mem[e + 6] if self.version <= 3 else self.rw(e + 10)

    def prop_table(self, o):
        e = self._e(o)
        return self.rw(e + 7) if self.version <= 3 else self.rw(e + 12)

    def name(self, o):
        """Short name of object o ("" if it has none)."""
        p = self.prop_table(o)
        if not self.mem[p]:
            return ""
        try:
            return self.decode(p + 1)[0]
        except Exception:
            return "?"

    def attrs(self, o):
        """List of the attribute numbers set on object o."""
        e = self._e(o)
        bits = int.from_bytes(bytes(self.mem[e:e + self.attr_bytes]), "big")
        top = 8 * self.attr_bytes - 1
        return [a for a in range(top + 1) if bits & (1 << (top - a))]

    def count(self):
        """How many objects there are. The table has no length, so this counts entries
        until they run into the lowest property table seen so far (property tables come
        straight after the object entries in Infocom games)."""
        n, lowest = 0, 1 << 20
        while self.objtab + self.entry * n < lowest:
            lowest = min(lowest, self.prop_table(n + 1))
            n += 1
        return n

    def props(self, o):
        """{property number: bytes} for object o."""
        p = self.prop_table(o)
        p += 1 + 2 * self.mem[p]                      # skip the short name
        out = {}
        while self.mem[p]:
            b = self.mem[p]
            if self.version <= 3:
                num, size, p = b & 31, (b >> 5) + 1, p + 1
            elif b & 0x80:
                num, size = b & 63, (self.mem[p + 1] & 63) or 64
                p += 2
            else:
                num, size, p = b & 63, 2 if b & 0x40 else 1, p + 1
            out[num] = bytes(self.mem[p:p + size])
            p += size
        return out

    def children(self, o):
        out, c = [], self.child(o)
        while c:
            out.append(c)
            c = self.sibling(c)
        return out

    def roots(self):
        """Objects with no parent (rooms are usually children of one of these)."""
        return [o for o in range(1, self.count() + 1) if self.parent(o) == 0]

    # ---- dictionary
    def dictionary(self):
        """List of (word, address, data bytes) for every dictionary entry."""
        m = self.mem
        a = self.rw(0x08)
        a += 1 + m[a]                                 # skip word separators
        elen, n = m[a], abs(zplay.s16(self.rw(a + 1)))
        a += 3
        keylen = 4 if self.version <= 3 else 6
        out = []
        for i in range(n):
            e = a + i * elen
            out.append((self.decode(e)[0], e, bytes(m[e + keylen:e + elen])))
        return out

    def directions(self):
        """{property number: [direction words]} worked out from the dictionary.

        Infocom games mark direction words with flag 0x10 in the first data byte. The
        property number that holds that direction's exit is in the second data byte when the
        word's main part of speech is "direction" (flags & 3 == 3), otherwise in the third.
        """
        out = {}
        for word, _, data in self.dictionary():
            if len(data) >= 3 and data[0] & 0x10:
                num = data[1] if data[0] & 3 == 3 else data[2]
                if 0 < num < 64:
                    out.setdefault(num, []).append(word)
        # Exit properties are the highest-numbered ones. Drop stray low numbers (some
        # games set the flag on a few other words) by keeping only numbers at or above the
        # lowest one that belongs to a standard direction word.
        std = {"north", "south", "east", "west", "up", "down", "in", "out", "fore", "aft"}
        known = [n for n, words in out.items() if std & set(words)]
        if known:
            out = {n: w for n, w in out.items() if n >= min(known)}
        return out

    def exits(self, room, dirs=None):
        """[(direction words, target room or None, kind)] for a room's exit properties.

        Infocom exit kinds, by property size (version 1-3; one byte per object):
          1 = UEXIT  always goes to the room
          2 = NEXIT  never goes; holds a "you can't go that way" message
          3 = FEXIT  a routine decides
          4 = CEXIT  goes if a variable is set
          5 = DEXIT  goes if a door is open
        Version 4+ games use two bytes per object, so the sizes are bigger; the target room
        is read from the start of the property either way.
        """
        dirs = dirs if dirs is not None else self.directions()
        wide = self.version > 3
        kinds = ({2: "always", 3: "never", 4: "routine", 5: "if-variable", 6: "if-door"} if wide
                 else {1: "always", 2: "never", 3: "routine", 4: "if-variable", 5: "if-door"})
        out = []
        for num, data in sorted(self.props(room).items(), reverse=True):
            if num not in dirs:
                continue
            kind = kinds.get(len(data), "size %d" % len(data))
            target = None
            if kind in ("always", "if-variable", "if-door"):
                target = (data[0] << 8 | data[1]) if wide else data[0]
            out.append((self.prefer(dirs[num]), target, kind))
        return out

    @staticmethod
    def prefer(words):
        """Put the most familiar direction word first (so routes say "west", not "ccw")."""
        order = ["north", "south", "east", "west", "northeast", "northwest", "southeast",
                 "southwest", "up", "down", "in", "out", "fore", "aft", "port", "starboard"]
        # version 1-3 dictionaries keep only 6 letters ("southe"): show the full word
        full = [next((o for o in order if len(w) == 6 and o.startswith(w)), w) for w in words]
        ranked = sorted(full, key=lambda w: (order.index(w) if w in order else 99, -len(w)))
        return ranked
