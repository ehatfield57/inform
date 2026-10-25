#!/usr/bin/env python3
"""zrun.py - play a list of commands in a game, optionally starting from a save, and see
what happens: the game's output, the room after each move, the score, which variables
changed, and what the game checked while a command ran.

This is the tool used to test hints: try a few commands from a saved position, look at the
result, save, try the next few. Nothing is sent to a model; you supply the commands.

Commands come from the command line (one argument per command; quote ones with spaces), from
--script FILE (one per line), or both (the script first). "[Hit any key]" pauses are answered
automatically, so they don't use up a command.

Starting point:
  (default)        a fresh game
  --from FILE      a save made with "save" in zplay.py, a <story>.auto.sav from
                   zplay_auto.py, or a file written by zrun.py --save
Ending:
  --save FILE      when the commands run out, save the position (autoplayer format) so a
                   later zrun.py --from FILE (or zplay_auto.py --load FILE) carries on there.

Examples:
  python3 tools/zrun.py lurking/lurking.z3 "sit on chair" "turn on pc" --save /tmp/a.sav
  python3 tools/zrun.py lurking/lurking.z3 --from /tmp/a.sav "login 872325412" look
  python3 tools/zrun.py wishbringer/wishbringer.z5 --script wishbringer/walkthrough.txt --quiet --moves
  python3 tools/zrun.py amfv/amfv.z4 --from x.sav --watch-global 190 --watch-global 19 record west
  python3 tools/zrun.py amfv/amfv.z4 --from x.sav --trace "go to sim mode" "go to sim mode" 1234

Tracing (for finding out how a puzzle works; see also zdis.py):
  --watch-global N   print whenever global variable GN changes, with the code address.
                     G numbers are as zdis.py shows them (G0 = variable 16).
  --trace CMD        while CMD runs, print every comparison and attribute/containment test
                     the game makes (je, jl, jg, jz, test_attr, jin), with values and
                     addresses. Typing a wrong code and tracing it is how the AMFV security
                     codes were found. Repeat --trace for several commands.
  --trace-from ADDR  only show traced lines whose code address is at least ADDR (hex), to
                     skip the parser's own checks (they run in low memory in most games).
"""

import argparse
import sys

import zinfo
from zinfo import zplay


class Done(Exception):
    """Raised when the game asks for input and there are no commands left."""


def build(args):
    cmds = []
    if args.script:
        with open(args.script) as fh:
            cmds += [l.rstrip("\n") for l in fh]
    cmds += args.commands
    return cmds


class Screen(zplay.Screen):
    """Screen that types our commands, answers key presses itself, and stops cleanly."""

    def __init__(self, cmds, quiet, width):
        super().__init__(width, 50, False, list(cmds) or ["\x00"])
        self.script = list(cmds)
        self.quiet = quiet
        self.typed = []                 # (command, output that followed)
        self.buf = ""

    def write(self, s):
        self.buf += s
        if not self.quiet:
            super().write(s)

    def read_line(self):
        if self.typed:
            self.typed[-1][1] = self.buf
        self.buf = ""
        if not self.script:
            if not self.quiet:
                self.flush()
            raise Done
        line = self.script.pop(0)
        self.typed.append([line, ""])
        if self.quiet:
            return line
        return super().read_line() if False else self._echo(line)

    def _echo(self, line):
        self.flush()
        sys.stdout.write(line + "\n")
        self.col = 0
        return line

    def read_char(self):
        if not self.quiet:
            self.flush()
            sys.stdout.write("\n")
        return "\n"                    # "press any key": just carry on


class Machine(zplay.ZMachine):
    """ZMachine that remembers where it last asked for input (so it can be saved there),
    and can watch variables and trace comparisons."""

    def setup(self, args, screen):
        self.args = args
        self.scr = screen
        self.read_state = None
        self.watch = {16 + n for n in args.watch_global}
        self.trace_cmds = set(args.trace)
        self.trace_from = int(args.trace_from, 16) if args.trace_from else 0
        self.tracing = False

    # remember the position at each input prompt, and switch tracing on/off per command
    def op_read(self, text, parse=0, *rest):
        self.read_state = self.snapshot() + (text, parse)
        super().op_read(text, parse, *rest)

    def finish_read(self, text, parse, line):
        self.tracing = line in self.trace_cmds
        if self.tracing:
            print("  ---- tracing %r ----" % line)
        return super().finish_read(text, parse, line)

    def _t(self, what):
        if self.tracing and self.pc >= self.trace_from:
            print("  .. %-40s at %05x" % (what, self.pc))

    def op_je(self, a, *rest):
        self._t("je %d in %s" % (a, list(rest)))
        return super().op_je(a, *rest)

    def op_jl(self, a, b):
        self._t("jl %d < %d" % (zplay.s16(a), zplay.s16(b)))
        return super().op_jl(a, b)

    def op_jg(self, a, b):
        self._t("jg %d > %d" % (zplay.s16(a), zplay.s16(b)))
        return super().op_jg(a, b)

    def op_jz(self, a):
        self._t("jz %d" % a)
        return super().op_jz(a)

    def op_test_attr(self, o, at):
        self._t("test_attr object %d attribute %d" % (o, at))
        return super().op_test_attr(o, at)

    def op_jin(self, a, b):
        self._t("jin object %d in %d" % (a, b))
        return super().op_jin(a, b)

    def write_var(self, v, x):
        if v in self.watch:
            old = self.read_var(v)
            if old != (x & 0xFFFF):
                print("  ** G%d: %d -> %d   (code at %05x)" % (v - 16, old, x & 0xFFFF, self.pc))
        return super().write_var(v, x)


def save_position(zm, path):
    """Write the position from the last input prompt, in the autoplayer's save format."""
    import base64
    import json
    import zlib
    dyn, frames, pc, text, parse = zm.read_state
    d = {"format": "zplay-auto-1", "story": list(zm.story_id()),
         "dynamic": base64.b64encode(zlib.compress(dyn)).decode(),
         "frames": [[f.ret_pc, f.locals, f.store, f.stack, f.argc] for f in frames],
         "pc": pc, "read": [text, parse]}
    with open(path, "w") as fh:
        json.dump(d, fh)


def start_from(zm, path):
    """Put the game at a saved position. Returns the first command to type, if any."""
    d = zinfo.read_save(path)
    if list(d["story"]) != list(zm.story_id()):
        sys.exit("%s was saved from a different game." % path)
    frames = [zplay.Frame(r, l, s, a, st) for r, l, s, st, a in d["frames"]]
    zm.restore_snapshot(d["dynamic"], frames, d["pc"])
    if d["format"] == "zplay-auto-1":
        # saved at an input prompt: answer that prompt with our first command
        text, parse = d["read"]
        return text, parse
    # a zplay.py "save": finish that save instruction as if it were a successful restore
    zm.result(2 if zm.version >= 4 else 1)
    return None


def room_and_score(zm):
    """(room name, status text, None) from the v3 status-line variables (score and moves,
    or the time of day in games that show a clock); status is None for v4+ games."""
    loc = zm.read_var(16)
    name = ""
    try:
        st = zinfo.Story.__new__(zinfo.Story)
        st.zm, st.mem, st.version = zm, zm.mem, zm.version
        if zm.version <= 3:
            st.ndefaults, st.entry, st.attr_bytes = 31, 9, 4
        else:
            st.ndefaults, st.entry, st.attr_bytes = 63, 14, 6
        st.objtab = st.rw(0x0A) + 2 * st.ndefaults
        st.globals = st.rw(0x0C)
        name = st.name(loc) if loc else ""
    except Exception:
        pass
    if zm.version <= 3:
        a, b = zplay.s16(zm.read_var(17)), zplay.s16(zm.read_var(18))
        if zm.mem[1] & 0x02:                 # a "time game": the status line shows a clock
            return name, "time %d:%02d" % (a, b), None
        return name, "score %d, move %d" % (a, b), None
    return name, None, None


def main():
    ap = argparse.ArgumentParser(
        description="Play commands in a Z-machine game and report what happens.",
        epilog="See the top of this file (or tools/README.md) for more examples.")
    ap.add_argument("story", help="story file")
    ap.add_argument("commands", nargs="*", help="commands to type, in order")
    ap.add_argument("--script", metavar="FILE", help="file of commands, one per line (typed first)")
    ap.add_argument("--from", dest="start", metavar="SAVE", help="start from this save file")
    ap.add_argument("--save", metavar="FILE", help="save the position when the commands run out")
    ap.add_argument("--seed", type=int, default=1,
                    help="random seed (default 1; the same seed and commands give the same game)")
    ap.add_argument("--quiet", action="store_true", help="don't print the game's output")
    ap.add_argument("--moves", action="store_true",
                    help="at the end, list each command with the room it left you in (v1-3 "
                         "games also get the score); handy for writing hints")
    ap.add_argument("--width", type=int, default=80, help="screen width (default 80)")
    ap.add_argument("--watch-global", type=int, action="append", default=[], metavar="N",
                    help="report changes to global variable GN (repeatable)")
    ap.add_argument("--trace", action="append", default=[], metavar="CMD",
                    help="trace the game's checks while this command runs (repeatable)")
    ap.add_argument("--trace-from", metavar="ADDR",
                    help="only trace code at or above this address (hex)")
    args = ap.parse_args()

    cmds = build(args)
    screen = Screen(cmds, args.quiet, args.width)
    zm = Machine(zplay.load_story(args.story), screen, args.story, args.seed)
    zm.setup(args, screen)
    moves = []

    # record the room/score after every command, for --moves
    orig = zm.finish_read

    def finish(text, parse, line):
        if moves:
            moves[-1][1:] = room_and_score(zm)
        moves.append([line, "", None, None])
        return orig(text, parse, line)
    zm.finish_read = finish

    try:
        if args.start:
            pending = start_from(zm, args.start)
            if pending:
                if not screen.script:
                    raise Done
                line = screen.script.pop(0)
                screen.typed.append([line, ""])
                if not args.quiet:
                    screen._echo(">" + line if False else line)
                zm.finish_read(pending[0], pending[1], line)
        zm.run()
    except Done:
        pass
    except zplay.Quit:
        pass
    if moves:
        moves[-1][1:] = room_and_score(zm)
    if args.save:
        if zm.read_state:
            save_position(zm, args.save)
            print("[saved to %s]" % args.save, file=sys.stderr)
        else:
            print("[nothing to save: the game never asked for input]", file=sys.stderr)
    if args.moves:
        print()
        for line, room, score, mv in moves:
            extra = "" if score is None else "   " + score
            print("%-40s %s%s" % (line, room, extra))
    return 0


if __name__ == "__main__":
    sys.exit(main())
