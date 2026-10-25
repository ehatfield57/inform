#!/usr/bin/env python3
"""amfv_codes.py - A Mind Forever Voyaging's Simulation Mode security codes.

"go to sim mode" asks for the code for a color and a number, e.g. "ORANGE 29". In the
original box you turned a cardboard decoder to find it. This tool knows all 512 answers
(16 colors x 32 numbers), saved in amfv_codes.json next to it.

How the table was made (--build): the game keeps the answers in a word table in its memory,
and the challenge it shows depends on the random number generator. So the tool starts the
game with many different seeds, asks for Simulation Mode each time, types a wrong code, and
reads which table entry the game compared it with. Run it again only if you want to check
the table; it takes several minutes.

Examples:
  python3 tools/amfv_codes.py ORANGE 29          # -> 84
  python3 tools/amfv_codes.py "dark blue" 28
  python3 tools/amfv_codes.py --table            # the whole table, one line per color
  python3 tools/amfv_codes.py --build --seeds 40000   # writes amfv_codes_new.json
"""

import argparse
import contextlib
import io
import json
import os
import re
import sys

from zinfo import zplay          # zinfo puts ../zplay.py on the import path

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, "amfv_codes.json")
STORY = os.path.join(os.path.dirname(HERE), "amfv", "amfv.z4")
ANSWERS = 0x7AF3          # address of the answer table in release 77 of the story file


def build(story, seeds):
    """Return {"COLOR NUMBER": code} by trying `seeds` random seeds."""

    class M(zplay.ZMachine):
        index = None

        def op_loadw(self, arr, i):
            if arr == ANSWERS:
                self.index = i
            return super().op_loadw(arr, i)

    class Stop(Exception):
        pass

    class Screen(zplay.Screen):
        # stop as soon as the commands run out, instead of waiting for the keyboard
        def read_line(self):
            if not self.script:
                raise Stop
            return super().read_line()

    found = {}
    for seed in range(1, seeds + 1):
        cmds = ["", "wait", "wait", "wait", "wait", "wait", "go to sim mode", "54321"]
        zm = M(zplay.load_story(story), Screen(80, 24, False, cmds), story, seed)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                zm.run()
            except BaseException:
                pass
        m = re.search(r"corresponding to: ([A-Z][A-Z ]*?) (\d+)", buf.getvalue().replace("\n", " "))
        if m and zm.index is not None:
            found["%s %s" % (m.group(1), m.group(2))] = zm.rw(ANSWERS + 2 * zm.index)
        if seed % 2000 == 0:
            print("  %d seeds tried, %d codes found" % (seed, len(found)), file=sys.stderr)
    return found


def main():
    ap = argparse.ArgumentParser(
        description="Look up A Mind Forever Voyaging security codes.",
        epilog="Example: python3 tools/amfv_codes.py ORANGE 29")
    ap.add_argument("color", nargs="?", help="the color shown, e.g. ORANGE or \"dark blue\"")
    ap.add_argument("number", nargs="?", type=int, help="the number shown, e.g. 29")
    ap.add_argument("--table", action="store_true", help="print the whole table")
    ap.add_argument("--build", action="store_true",
                    help="rebuild amfv_codes.json by playing the game (slow)")
    ap.add_argument("--seeds", type=int, default=40000,
                    help="with --build, how many seeds to try (default 40000)")
    ap.add_argument("--story", default=STORY, help="path to amfv.z4 (default ../amfv/amfv.z4)")
    ap.add_argument("--out", metavar="FILE",
                    help="with --build, where to write the table (default: amfv_codes_new.json "
                         "next to this tool, so the real table isn't replaced by a short test run)")
    args = ap.parse_args()

    if args.build:
        codes = build(args.story, args.seeds)
        out = args.out or os.path.join(HERE, "amfv_codes_new.json")
        with open(out, "w") as fh:
            json.dump(codes, fh, indent=0, sort_keys=True)
        print("wrote %d codes to %s (the full table has 512; copy it over amfv_codes.json "
              "to use it)" % (len(codes), out))
        return 0
    with open(TABLE) as fh:
        codes = json.load(fh)
    if args.table:
        by = {}
        for k, v in codes.items():
            c, n = k.rsplit(" ", 1)
            by.setdefault(c, {})[int(n)] = v
        for c in sorted(by):
            print("%-11s %s" % (c + ":", " ".join("%d=%d" % (n, by[c][n]) for n in sorted(by[c]))))
        return 0
    if not args.color or args.number is None:
        ap.error("give a color and a number, or --table")
    key = "%s %d" % (args.color.upper(), args.number)
    if key not in codes:
        print("No code for %s. Colors: %s" % (
            key, ", ".join(sorted({k.rsplit(" ", 1)[0] for k in codes}))))
        return 1
    print(codes[key])
    return 0


if __name__ == "__main__":
    sys.exit(main())
