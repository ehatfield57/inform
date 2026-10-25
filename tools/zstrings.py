#!/usr/bin/env python3
"""zstrings.py - dump the readable text in a Z-machine story file.

Infocom games store their text compressed ("Z-strings"), so you can't just grep the file.
This tool decodes every spot in the file that looks like English text and prints it with
its address, so you can search the game's messages for clues: what a puzzle expects, what
an object's description says, where a death message lives.

The scan is a heuristic: it tries to decode a string at every byte, keeps the ones that look
like words, and skips over them. You'll see some garbage lines; the real text is easy to spot.
Text printed by game code ("inline" strings) is found too, so the address of a message is
usually inside the routine that prints it, which is a good place to point zdis.py.

Examples:
  python3 tools/zstrings.py lurking/lurking.z3 | less
  python3 tools/zstrings.py wishbringer/wishbringer.z5 --grep troll
  python3 tools/zstrings.py amfv/amfv.z4 --grep "must be cancelled" --context 3
"""

import argparse
import re
import sys

import zinfo


def scan(story, min_len):
    """Yield (address, text) for everything that decodes to plausible English."""
    mem = story.mem
    good = re.compile(r"[A-Za-z0-9 ,.'\"!?;:()\-\n&/%*$+=_]+")
    addr, end = 0x40, len(mem) - 2
    while addr < end:
        try:
            text, after = story.decode(addr)
        except Exception:
            addr += 1
            continue
        letters = sum(c.isalpha() for c in text)
        if (len(text) >= min_len and good.fullmatch(text) and text.count(" ") >= 2
                and letters > 0.7 * len(text)):
            yield addr, " ".join(text.split())
            addr = after
        else:
            addr += 1


def main():
    ap = argparse.ArgumentParser(
        description="Dump the readable text in a Z-machine story file, with addresses.",
        epilog="Example: python3 tools/zstrings.py wishbringer/wishbringer.z5 --grep troll")
    ap.add_argument("story", help="story file (.z3, .z4, .z5 ...)")
    ap.add_argument("--grep", metavar="TEXT",
                    help="only show strings containing TEXT (case doesn't matter; a regular "
                         "expression is fine)")
    ap.add_argument("--context", type=int, default=0, metavar="N",
                    help="with --grep, also show N strings before and after each match")
    ap.add_argument("--min-len", type=int, default=12, metavar="N",
                    help="ignore strings shorter than N characters (default 12)")
    ap.add_argument("--width", type=int, default=0, metavar="N",
                    help="cut each line to N characters (default: no limit)")
    args = ap.parse_args()

    story = zinfo.Story(args.story)
    rows = list(scan(story, args.min_len))
    keep = range(len(rows))
    if args.grep:
        pat = re.compile(args.grep, re.I)
        hits = [i for i, (_, t) in enumerate(rows) if pat.search(t)]
        keep = sorted({j for i in hits
                       for j in range(max(0, i - args.context), min(len(rows), i + args.context + 1))})
    for i in keep:
        a, t = rows[i]
        line = "%05x  %s" % (a, t)
        print(line[:args.width] if args.width else line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
