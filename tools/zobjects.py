#!/usr/bin/env python3
"""zobjects.py - look at the objects and rooms inside a Z-machine story file.

Everything in an Infocom game is an object: rooms, things, people, even "you". Objects sit
inside each other in a tree (a lamp inside a room, a key inside a coat). This tool shows
that tree, one object in detail, or the rooms and their exits.

Give it a save file (--save) to see the tree as it was at that point in a game: where every
item had been carried, which flags were set. Both zplay.py saves and the autoplayer's
<story>.auto.sav work.

Examples:
  python3 tools/zobjects.py starcross/starcross.z5                 # the whole object tree
  python3 tools/zobjects.py starcross/starcross.z5 --find rod      # which objects match
  python3 tools/zobjects.py starcross/starcross.z5 --where "red rod" --save starcross/starcross.auto.sav
  python3 tools/zobjects.py amfv/amfv.z4 --object 373              # one object in detail
  python3 tools/zobjects.py lurking/lurking.z3 --rooms             # every room and its exits
  python3 tools/zobjects.py starcross/starcross.z5 --route "Red Hall" "Weapons Deck"

Words you'll see:
  attributes  numbered on/off flags on an object (open, lit, takeable ...). Their meaning
              isn't stored in the file; compare an object before and after an action.
  properties  numbered values on an object. Rooms keep their exits in the highest-numbered
              properties; which number is which direction is read from the game's dictionary.
"""

import argparse
import collections
import sys

import zinfo


def label(s, o):
    return "%d %s" % (o, s.name(o) or "(no name)")


def print_tree(s, o, depth, out):
    out.append("  " * depth + label(s, o))
    for c in s.children(o):
        print_tree(s, c, depth + 1, out)


def find(s, text):
    t = text.lower()
    return [o for o in range(1, s.count() + 1) if t in s.name(o).lower()]


def exact_or_find(s, text, rooms_only=False):
    """Object number for a name or number given on the command line. With rooms_only,
    objects that have exits are preferred (a game can have a "lighthouse" object and a
    "Lighthouse" room)."""
    if text.isdigit():
        return int(text)
    exact = [o for o in range(1, s.count() + 1) if s.name(o).lower() == text.lower()]
    if rooms_only:
        dirs = s.directions()
        exact = [o for o in exact if is_room(s, o, dirs)] or exact
    hits = exact or find(s, text)
    if not hits:
        sys.exit("No object called %r." % text)
    if len(hits) > 1 and not exact:
        print("(%r matches %s; using the first)" % (text, ", ".join(label(s, h) for h in hits[:8])),
              file=sys.stderr)
    return hits[0]


def is_room(s, o, dirs):
    return any(n in dirs for n in s.props(o))


def show_object(s, o, dirs):
    print(label(s, o))
    p = s.parent(o)
    print("  inside:     %s" % (label(s, p) if p else "nothing (top level)"))
    kids = s.children(o)
    print("  contains:   %s" % (", ".join(label(s, k) for k in kids) if kids else "nothing"))
    print("  attributes: %s" % (" ".join(map(str, s.attrs(o))) or "none"))
    print("  properties:")
    for num, data in sorted(s.props(o).items(), reverse=True):
        extra = ""
        if num in dirs:
            extra = "   <- exit %s" % "/".join(dirs[num][:3])
        print("    %2d: %s%s" % (num, " ".join("%d" % b for b in data), extra))
    ex = s.exits(o, dirs)
    if ex:
        print("  exits:")
        for words, target, kind in ex:
            print("    %-10s %-12s %s" % (words[0], kind, label(s, target) if target else ""))


def all_rooms(s, dirs):
    return [o for o in range(1, s.count() + 1) if is_room(s, o, dirs)]


def route(s, dirs, a, b):
    """Shortest list of (direction, room) from a to b using exits that always work or
    depend on a door/variable. Exits handled by game code ("routine") are skipped, so a
    real route may exist even when none is found."""
    prev: dict = {a: None}
    q = collections.deque([a])
    while q:
        r = q.popleft()
        if r == b:
            break
        for words, t, kind in s.exits(r, dirs):
            if t and t not in prev:
                prev[t] = (r, words[0], kind)
                q.append(t)
    if b not in prev:
        return None
    path, r = [], b
    while prev[r]:
        r0, w, kind = prev[r]
        path.append((w, r, kind))
        r = r0
    return list(reversed(path))


def main():
    ap = argparse.ArgumentParser(
        description="Show the objects, rooms and exits inside a Z-machine story file.",
        epilog="With no options, prints the whole object tree.")
    ap.add_argument("story", help="story file (.z3, .z4, .z5 ...)")
    ap.add_argument("--save", metavar="FILE",
                    help="read objects as they are in this save file (a zplay.py save or a "
                         "<story>.auto.sav)")
    ap.add_argument("--find", metavar="TEXT", help="list objects whose name contains TEXT")
    ap.add_argument("--object", metavar="N|NAME", help="show one object in detail")
    ap.add_argument("--where", metavar="N|NAME",
                    help="show where an object is: the chain of objects it sits inside")
    ap.add_argument("--rooms", action="store_true", help="list every room with its exits")
    ap.add_argument("--route", nargs=2, metavar=("FROM", "TO"),
                    help="shortest walk between two rooms (names or numbers)")
    ap.add_argument("--dirs", action="store_true",
                    help="show which property number holds which direction")
    args = ap.parse_args()

    s = zinfo.Story(args.story, args.save)
    dirs = s.directions()

    if args.dirs:
        for num in sorted(dirs, reverse=True):
            print("%2d: %s" % (num, ", ".join(dirs[num])))
    elif args.find:
        for o in find(s, args.find):
            p = s.parent(o)
            print("%-34s inside %s" % (label(s, o), label(s, p) if p else "-"))
    elif args.object:
        show_object(s, exact_or_find(s, args.object), dirs)
    elif args.where:
        o = exact_or_find(s, args.where)
        chain = [label(s, o)]
        while s.parent(o):
            o = s.parent(o)
            chain.append(label(s, o))
        print(" <- inside ".join(chain))
    elif args.rooms:
        for r in all_rooms(s, dirs):
            ex = s.exits(r, dirs)
            parts = ["%s>%s" % (w[0], s.name(t) if t else "(%s)" % k) for w, t, k in ex]
            print("%-30s %s" % (label(s, r), "; ".join(parts)))
    elif args.route:
        a, b = (exact_or_find(s, x, rooms_only=True) for x in args.route)
        path = route(s, dirs, a, b)
        if path is None:
            print("No route found from %s to %s using fixed exits (some exits are decided by "
                  "game code and can't be followed here)." % (label(s, a), label(s, b)))
            return 1
        for w, r, kind in path:
            note = "" if kind == "always" else "   (%s)" % kind
            print("%-10s -> %s%s" % (w, s.name(r), note))
    else:
        out = []
        for r in s.roots():
            print_tree(s, r, 0, out)
        print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
