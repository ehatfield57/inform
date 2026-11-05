#!/usr/bin/env python3
"""zilplay.py - play an Infocom game straight from its ZIL source.

Plays in the terminal, like zplay.py, but from Infocom's source code instead of a
story file: the source is read, its macros run, its data laid out the way Infocom's
compiler did, and its routines run as written. Give it a folder of .zil files or
one of the zips in sources/. For the browser version with a debugger and map, see
zilserve.py. More in zil/README.md.

Examples:
  python3 zilplay.py sources/zork1-r119.zip
  python3 zilplay.py sources/zork3-mac-r15.zip --seed 1
  python3 zilplay.py sources/zork1-r119.zip --warnings      # what the loader noticed

Checking it against the real game (same release), as for every finished Zork:
  W=played/zork1/walkthrough.txt
  python3 zilplay.py sources/zork1-r119.zip --script $W --seed 1 --no-status --width 80 --serial 880429 > /tmp/zil.txt
  python3 zplay.py games/zork1.z3 --script $W --seed 1 --no-status --width 80 > /tmp/zplay.txt
  diff /tmp/zplay.txt /tmp/zil.txt                          # no output = identical
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

    # the upper window, handled by zplay's Screen
    @property
    def width(self):
        return self.screen.width

    @property
    def height(self):
        return self.screen.height

    def split(self, lines):
        self.screen.split(lines)

    def erase_upper(self):
        self.screen.erase_upper()

    def upper_write(self, text):
        self.screen.upper_write(text)

    def set_cursor(self, row, col):
        self.screen.cur_row, self.screen.cur_col = row, col

    def get_cursor(self):
        return self.screen.cur_row, self.screen.cur_col

    def erase_line(self):
        self.screen.erase_line()

    def show_upper(self):
        self.screen.show_upper()

    def key_ready(self, seconds):
        return self.screen.key_ready(seconds)

    def ask_filename(self, purpose, default):
        self.screen.write("%s file name (default %s): " % (purpose, default))
        name = self.read_line().strip()
        return name or default


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="folder of .zil files, or a zip of them")
    ap.add_argument("--script", help="text file of commands to type, one per line")
    ap.add_argument("--no-status", action="store_true", help="don't print the status line")
    ap.add_argument("--width", type=int, help="screen width (default: terminal width)")
    ap.add_argument("--seed", type=int, help="random seed, for reproducible runs")
    ap.add_argument("--serial", help="serial number to report (the source doesn't record it)")
    ap.add_argument("--warnings", action="store_true", help="show warnings from loading")
    ap.add_argument("--zilch", choices=["old", "new"],
                    help="which compiler generation to copy (normally worked out from the "
                         "source; 'old' is the early-1980s ZILCH)")
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
        game = open_game(args.source, seed=args.seed, serial=args.serial, zilch=args.zilch)
    except (LoadError, BuildError, ZilError) as e:
        print("[Could not load %s: %s]" % (args.source, e))
        sys.exit(1)
    except Exception as e:      # a bug in the loader: say so plainly
        print("[Could not load %s: %s: %s]" % (args.source, type(e).__name__, e))
        sys.exit(1)
    if args.warnings:
        print("[%r]" % game.game.zilch)
        for w in game.warnings:
            print("[warning] " + w)
    elif game.compile_errors:
        print("[%d routine(s) couldn't be compiled and will stop the game if called; "
              "--warnings shows them]" % len(game.compile_errors), file=sys.stderr)
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
