#!/usr/bin/env python3
"""zplaymap.py - draw the autoplayer's map by playing a walkthrough through it.

The autoplayer (zplay_auto.py) draws a map as it plays: every room it walks into, the exits
it tries and the things it sees. Normally a language model picks the commands. This tool
plays a walkthrough instead, one command per turn, using a stand-in "model" that just
answers with the next line of the file. No Ollama is needed, and the map shows exactly the
route the walkthrough takes.

It runs in a temporary folder holding a copy of the story file, so the autoplayer starts
fresh and none of its working files (.auto.json, .auto.sav, .auto.log) land next to your
game. When it's done only the two map files are copied out:

    <story>.auto.map.json   the map data
    <story>.auto.map.pdf    the printable map

They go next to the story file unless you give --out-dir. Use --keep-log to copy the
autoplayer's log too (the whole game text, turn by turn).

The walkthrough is a text file with one command per line (blank lines are skipped), the same
file zplay.py --script plays. After the last line the stand-in model types "wait" until the
turns run out, so set --turns to the number of commands or a few more (the default is the
number of commands plus 10). Repeated commands are allowed; a real model would be stopped
from repeating itself, but walkthroughs often need to.

Use the same --seed the walkthrough was made with (default 1), or a random game may go a
different way.

Examples:
  python3 tools/zplaymap.py played/plundered_hearts/walkthrough.txt played/plundered_hearts/plundered_hearts.z5
  python3 tools/zplaymap.py played/zork2/walkthrough.txt played/zork2/zork2.z5 --seed 1 --out-dir /tmp/maps
  python3 tools/zplaymap.py played/witness/walkthrough.txt played/witness/witness.z5 --keep-log
"""

import argparse
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.normpath(os.path.join(HERE, os.pardir))   # where zplay_auto.py lives
sys.path.insert(0, PROJECT)


def play(commands, story, turns, seed, quiet):
    """Run zplay_auto.py on story (inside the current folder) with a scripted model."""
    import zplay_llm

    state = {"i": 0}

    def chat(self, messages):
        # The autoplayer reads the command from a "COMMAND: ..." line in the reply.
        i = state["i"]
        state["i"] += 1
        return "COMMAND: " + (commands[i] if i < len(commands) else "wait")

    zplay_llm.Ollama.chat = chat
    zplay_llm.Ollama.check = lambda self: None        # no Ollama server to look for

    import zplay_auto
    zplay_auto.Player.check = lambda self, cmd: None  # allow repeated commands

    argv = ["zplay_auto.py", story, "--model", "walkthrough", "--fresh",
            "--turns", str(turns), "--seed", str(seed)]
    if quiet:
        argv.append("--no-status")
    sys.argv = argv
    try:
        zplay_auto.main()
    except SystemExit as e:                           # main() may sys.exit() at the end
        if e.code not in (None, 0):
            raise


def main():
    ap = argparse.ArgumentParser(
        description="Play a walkthrough through the autoplayer (no model needed) to draw "
                    "its map: <story>.auto.map.json and .pdf.",
        epilog="See the top of this file (or tools/README.md) for more examples.")
    ap.add_argument("walkthrough", help="text file, one command per line")
    ap.add_argument("story", help="story file (.z3, .z5 ...)")
    ap.add_argument("--seed", type=int, default=1,
                    help="random seed; use the one the walkthrough was made with (default 1)")
    ap.add_argument("--turns", type=int,
                    help="turns to play (default: the number of commands plus 10)")
    ap.add_argument("--out-dir", help="where to put the map files (default: next to the story)")
    ap.add_argument("--keep-log", action="store_true",
                    help="also copy <story>.auto.log, the full text of the run")
    ap.add_argument("--quiet", action="store_true", help="don't print the status line")
    args = ap.parse_args()

    with open(args.walkthrough, encoding="utf-8") as fh:
        commands = [line.strip() for line in fh if line.strip()]
    turns = args.turns or len(commands) + 10
    out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.story))
    os.makedirs(out_dir, exist_ok=True)

    name = os.path.basename(args.story)
    stem = os.path.splitext(name)[0]
    wanted = [stem + ".auto.map.json", stem + ".auto.map.pdf"]
    if args.keep_log:
        wanted.append(stem + ".auto.log")

    start = os.getcwd()
    with tempfile.TemporaryDirectory(prefix="zplaymap-") as tmp:
        shutil.copyfile(args.story, os.path.join(tmp, name))
        os.chdir(tmp)
        try:
            play(commands, name, turns, args.seed, args.quiet)
        finally:
            os.chdir(start)
        copied = []
        for f in wanted:
            src = os.path.join(tmp, f)
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(out_dir, f))
                copied.append(os.path.join(out_dir, f))

    if not copied:
        sys.exit("No map was written (did the game start?).")
    print("\nWrote " + ", ".join(copied), flush=True)


if __name__ == "__main__":
    main()
