#!/usr/bin/env python3
"""zwords.py - the game's dictionary: list it, or check commands against it.

A Z-machine game only understands words in its dictionary. The autoplayer refuses a
command with an unknown word, so every command in a hint should pass this check. Games from
Infocom's version 1-3 era keep only the first 6 letters of each word ("southe" for
southeast); this tool accounts for that.

Examples:
  python3 tools/zwords.py played/amfv/amfv.z4 --check played/amfv/walkthrough.txt
  python3 tools/zwords.py played/amfv/amfv.z4 "hvac, turn off ventilation" "wiggle toes"
  python3 tools/zwords.py played/lurking/lurking.z3 --list | column -c 120
  python3 tools/zwords.py played/wishbringer/wishbringer.z5 --list --directions
"""

import argparse
import sys

import zinfo


def checker(story):
    """A function that returns the unknown words in a command."""
    zm = story.zm
    seps, lookup = zm.load_dict(zm.dict_addr)
    sep_chars = {chr(c) for c in seps} | {" "}

    def words(cmd):
        out, cur = [], ""
        for ch in cmd.lower():
            if ch in sep_chars:
                if cur:
                    out.append(cur)
                cur = ""
            else:
                cur += ch
        if cur:
            out.append(cur)
        return out

    def unknown(cmd):
        bad = []
        for w in words(cmd):
            if w.isdigit():
                continue
            key = zm.encode_word([zm.to_zscii(c) for c in w])
            if key not in lookup:
                bad.append(w)
        return bad
    return unknown


def main():
    ap = argparse.ArgumentParser(
        description="List a game's dictionary or check commands against it.")
    ap.add_argument("story", help="story file")
    ap.add_argument("commands", nargs="*", help="commands to check")
    ap.add_argument("--check", metavar="FILE",
                    help="check every line of a command file (e.g. a walkthrough)")
    ap.add_argument("--list", action="store_true", help="print every dictionary word")
    ap.add_argument("--directions", action="store_true",
                    help="with --list, only the direction words and their exit property")
    args = ap.parse_args()

    s = zinfo.Story(args.story)
    if args.list:
        if args.directions:
            for num, ws in sorted(s.directions().items(), reverse=True):
                print("%2d: %s" % (num, " ".join(ws)))
        else:
            for w in sorted(w for w, _, _ in s.dictionary()):
                print(w)
        return 0
    unknown = checker(s)
    lines = list(args.commands)
    if args.check:
        with open(args.check) as fh:
            lines += [l.strip() for l in fh if l.strip()]
    if not lines:
        ap.error("give commands to check, --check FILE, or --list")
    bad = 0
    for cmd in lines:
        u = unknown(cmd)
        if u:
            bad += 1
            print("%-40s unknown: %s" % (cmd, ", ".join(u)))
    print("%d command(s) checked, %d with unknown words." % (len(lines), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
