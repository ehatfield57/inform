#!/usr/bin/env python3
"""zgamemap.py - draw a map of a game straight from its own room data.

The autoplayer (zplay_auto.py) maps a game by playing it: it only knows the rooms it has
walked through. This tool reads every room and exit stored in the story file instead, so
it maps the whole game at once, without playing a single move. That's useful when:

  - the player never moves (in Suspended you stay in a capsule and send robots), so a
    played map would show only a handful of rooms;
  - you want the whole layout before you start, or a map of rooms a walkthrough skips.

It writes a map file in the same format the autoplayer uses (<story>.auto.map.json style),
which zmap_pdf.py turns into a PDF. With --pdf it does that step for you.

Each room's box lists the things that start in it (people, robots, items, scenery). Give a
save file (--save) to show where everything is at that point in a game instead.

Exits are the ones the file stores directly. Exits worked out by a routine (a door that
needs a password, a maze that changes) can't be read without playing, so they're left
out; directions that can never be taken are marked as blocked.

Examples:
  python3 tools/zgamemap.py suspended/suspended.z5 --pdf
  python3 tools/zgamemap.py zork1/zork1.z3 -o /tmp/zork1.map.json --pdf --title "Zork I"
  python3 tools/zgamemap.py starcross/starcross.z5 --save starcross/starcross.auto.sav --pdf
  python3 tools/zgamemap.py witness/witness.z5 --no-items      # just rooms and exits
"""

import argparse
import json
import os
import subprocess
import sys

import zinfo
import zobjects

HERE = os.path.dirname(os.path.abspath(__file__))
ZMAP_PDF = os.path.join(HERE, os.pardir, "zmap_pdf.py")


def build(story, save=None, items=True):
    """The map as a dict in zmap_pdf.py's format: rooms with exits, plus items by room."""
    s = zinfo.Story(story, save)
    dirs = s.directions()
    rooms = zobjects.all_rooms(s, dirs)
    room_set = set(rooms)
    data = {"story": [s.rw(2), bytes(s.mem[0x12:0x18]).decode("latin-1"), s.rw(0x1C)],
            "rooms": {}, "items": {}, "player": 0, "here": None}
    for r in rooms:
        exits, blocked = {}, []
        for words, target, kind in s.exits(r, dirs):
            if target in room_set:
                exits[words[0]] = str(target)        # always / if-variable / if-door
            elif kind == "never":
                blocked.append(words[0])             # "you can't go that way"
            # kind == "routine": decided while playing; can't be read from the file
        data["rooms"][str(r)] = {"name": s.name(r) or "Room %d" % r, "exits": exits,
                                 "blocked": blocked, "mentioned": [], "guess": {}}
        if items:
            for c in s.children(r):
                if c not in room_set and s.name(c):
                    data["items"][str(c)] = {"name": s.name(c), "room": str(r), "where": "here",
                                             "carried": False, "missing": False, "words": []}
    return data


def main():
    ap = argparse.ArgumentParser(
        description="Draw a map of a game from the rooms and exits stored in its story file.",
        epilog="See the top of this file (or tools/README.md) for more examples.")
    ap.add_argument("story", help="story file (.z3, .z5 ...)")
    ap.add_argument("-o", "--out", help="map file to write (default: <story>.game.map.json "
                    "next to the story, so a played <story>.auto.map.json is never overwritten)")
    ap.add_argument("--save", help="show items where they are in this save file "
                    "(a zplay.py save or a <story>.auto.sav) instead of where they start")
    ap.add_argument("--no-items", action="store_true", help="rooms and exits only")
    ap.add_argument("--pdf", action="store_true", help="also draw the PDF with zmap_pdf.py "
                    "(written next to the map file, same name ending in .pdf)")
    ap.add_argument("--title", help="title for the PDF (default: the story's name)")
    args = ap.parse_args()

    out = args.out or os.path.splitext(args.story)[0] + ".game.map.json"
    data = build(args.story, args.save, items=not args.no_items)
    with open(out, "w") as fh:
        json.dump(data, fh, indent=1)
    print("Wrote %s: %d rooms, %d items." % (out, len(data["rooms"]), len(data["items"])),
          flush=True)

    if args.pdf:
        title = args.title or os.path.splitext(os.path.basename(args.story))[0].capitalize()
        pdf = os.path.splitext(out)[0] + ".pdf"          # x.map.json -> x.map.pdf
        sys.exit(subprocess.call([sys.executable, ZMAP_PDF, out, "-o", pdf, "--title", title]))


if __name__ == "__main__":
    main()
