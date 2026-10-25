#!/usr/bin/env python3
"""zdiff.py - compare two saved positions of the same game: what moved, which flags and
which variables changed.

This is the quickest way to learn what an action really did inside the game. Save before,
do the thing, save after, then compare:

  python3 tools/zrun.py wishbringer/wishbringer.z5 --from a.sav --save b.sav "push bunk" up
  python3 tools/zdiff.py wishbringer/wishbringer.z5 a.sav b.sav

The output lists objects that changed place, attributes (numbered flags) that went on or
off, and global variables that changed. A variable that keeps climbing over time is often a
timer or a counter; one that changes only after your action is the interesting kind.

Saves can be zplay.py saves, <story>.auto.sav files, or files from zrun.py --save.
"""

import argparse
import sys

import zinfo


def main():
    ap = argparse.ArgumentParser(description="Compare two saved positions of the same game.")
    ap.add_argument("story", help="story file")
    ap.add_argument("before", help="first save file")
    ap.add_argument("after", help="second save file")
    ap.add_argument("--globals-only", action="store_true", help="only show global variables")
    ap.add_argument("--objects-only", action="store_true", help="only show objects")
    args = ap.parse_args()

    a = zinfo.Story(args.story, args.before)
    b = zinfo.Story(args.story, args.after)
    n = a.count()

    def lab(s, o):
        return "%d %s" % (o, s.name(o) or "(no name)") if o else "nowhere"

    if not args.globals_only:
        print("Objects that moved:")
        for o in range(1, n + 1):
            if a.parent(o) != b.parent(o):
                print("  %-30s %s  ->  %s" % (lab(a, o), lab(a, a.parent(o)), lab(b, b.parent(o))))
        print("Attributes that changed:")
        for o in range(1, n + 1):
            on = set(b.attrs(o)) - set(a.attrs(o))
            off = set(a.attrs(o)) - set(b.attrs(o))
            if on or off:
                parts = (["+%d" % x for x in sorted(on)] + ["-%d" % x for x in sorted(off)])
                print("  %-30s %s" % (lab(a, o), " ".join(parts)))
        print("Properties that changed:")
        for o in range(1, n + 1):
            pa, pb = a.props(o), b.props(o)
            for k in sorted(set(pa) | set(pb)):
                if pa.get(k) != pb.get(k):
                    print("  %-30s property %d: %s -> %s" % (lab(a, o), k,
                          list(pa.get(k, b"")), list(pb.get(k, b""))))
    if not args.objects_only:
        print("Global variables that changed:")
        for g in range(240):
            if a.glob(g) != b.glob(g):
                print("  G%-4d %6d -> %d" % (g, zinfo.zplay.s16(a.glob(g)), zinfo.zplay.s16(b.glob(g))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
