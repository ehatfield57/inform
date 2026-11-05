#!/usr/bin/env python3
"""zilplay.py - play an Infocom game straight from its ZIL source.

The source is read, its macros run, its data laid out like the compiled game,
and its routines interpreted as they are written. Give it a folder of .zil
files or one of the zips in sources/.

Examples:
  python3 zilplay.py sources/zork1-r119.zip
  python3 zilplay.py sources/zork1-r119.zip --script played/zork1/walkthrough.txt --seed 1 --no-status --width 80
"""

import argparse
import shutil
import sys

from zplay import Screen, Quit as ZQuit
from zil.runtime import open_game, IO, ZilError, Quit, describe_error
from zil.loader import LoadError
from zil.image import BuildError


class ScreenIO(IO):
    """Terminal input/output, using zplay's screen so transcripts match zplay's."""

    def __init__(self, screen):
        self.screen = screen

    def write(self, text):
        self.screen.write(text)

    def read_line(self):
        try:
            return self.screen.read_line()
        except ZQuit:
            raise Quit()

    def read_char(self):
        try:
            return self.screen.read_char()
        except ZQuit:
            raise Quit()

    def status(self, left, right):
        if not self.screen.show_status:
            return
        w = self.screen.width - 1
        left, right = " " + left, right + " "
        self.screen.status_row(left[: w - len(right) - 1].ljust(w - len(right)) + right)

    def ask_filename(self, purpose, default):
        self.screen.write("%s file name (default %s): " % (purpose, default))
        name = self.read_line().strip()
        return name or default


def main():
    ap = argparse.ArgumentParser(description="Play an Infocom game from its ZIL source.")
    ap.add_argument("source", help="folder of .zil files, or a zip of them")
    ap.add_argument("--script", help="text file of commands to type, one per line")
    ap.add_argument("--no-status", action="store_true", help="don't print the status line")
    ap.add_argument("--width", type=int, help="screen width (default: terminal width)")
    ap.add_argument("--seed", type=int, help="random seed, for reproducible runs")
    ap.add_argument("--serial", help="serial number to report (the source doesn't record it)")
    ap.add_argument("--warnings", action="store_true", help="show warnings from loading")
    args = ap.parse_args()

    size = shutil.get_terminal_size((80, 24))
    script = None
    if args.script:
        with open(args.script) as fh:
            script = [l.rstrip("\n") for l in fh]
    if sys.stdin.isatty():
        try:
            import readline  # noqa: F401
        except ImportError:
            pass
    try:
        game = open_game(args.source, seed=args.seed, serial=args.serial)
    except (LoadError, BuildError, ZilError) as e:
        print("[Could not load %s: %s]" % (args.source, e))
        sys.exit(1)
    if args.warnings:
        for w in game.warnings:
            print("[warning] " + w)
    screen = Screen(args.width or size.columns, size.lines, not args.no_status, script)
    try:
        game.run(ScreenIO(screen))
    except KeyboardInterrupt:
        print()
    except Exception as e:
        screen.flush()
        print("\n[ZIL error: %s]" % describe_error(e))
        sys.exit(1)
    finally:
        screen.flush()


if __name__ == "__main__":
    main()
