#!/usr/bin/env python3
"""
zplay_auto.py - let a local LLM (via Ollama) play an Infocom/Inform game by itself.

RUNNING IT
    python3 zplay_auto.py zork1.z3                     # play up to 300 turns
    python3 zplay_auto.py zork1.z3 --turns 1000        # play longer
    python3 zplay_auto.py zork1.z3 --delay 1           # pause 1 second per turn, to watch
    python3 zplay_auto.py zork1.z3 --fair              # no peeking at hidden objects
    python3 zplay_auto.py zork1.z3 --restart           # start the game over, keep notes and map
    python3 zplay_auto.py zork1.z3 --fresh             # forget what earlier runs learned
    python3 zplay_auto.py zork1.z3 --load zork1.sav    # start from a save you made
    python3 zplay_auto.py zork1.z3 --model qwen3:8b    # try another installed model
    python3 zplay_auto.py --help                       # all options, then this guide
Needs zplay.py and zplay_llm.py in the same folder, and Ollama running.

PAUSING AND STOPPING
    p or space          pause. While paused, type commands for the game yourself (Enter
                        sends each one), or just press Enter to let the model carry on.
                        You can also edit the hints then.
    q                   stop (while paused: q then Enter)
    Ctrl-C              stop at once
Keys take effect when the model is next asked for a command, so allow a few seconds.
Stopping saves everything and prints a summary (turns, rooms, score, hints, notes).
The next run carries on from the same spot in the game (it starts by typing "look"),
unless you give --restart, --fresh or --load.

STARTING FROM YOUR OWN SAVE (--load)
When a game's opening is fiddly, play it yourself and let the model take over from there:
  1. Play in the normal player:   python3 zplay.py starcross/starcross.z5
  2. At the point you want, type "save" and give a file name (the default is
     starcross/starcross.sav). Type "quit" to leave.
  3. Start the model from it:
       python3 zplay_auto.py starcross/starcross.z5 --load starcross/starcross.sav
The model starts by typing "look" so it sees where it is. Your save file is only read,
never changed; the model's own position still goes to <story>.auto.sav each turn.
--load also takes a copy of a <story>.auto.sav, so you can keep a good spot from a model
run as a checkpoint:  cp starcross/starcross.auto.sav starcross/good.sav
Notes and map are kept as usual (add --fresh to clear them). The model knows nothing about
how you got there, so add a hint saying where it is and what you've done, e.g. "You have
reached the artifact; you are in the couch with the seat belt fastened."

HINTS
To tell the model something, add it to the "hints" list in <story>.auto.json:
    "hints": [
     "The bird is afraid of the black rod: drop the rod before catching the bird with the cage."
    ],
Hints are shown to the model every turn as true, and are never trimmed, replaced or dropped
the way its own notes are (--fresh keeps them too). Only edit the file while the game is
paused or not running: at other times it is rewritten every turn and your change is lost.
Use the game's own words (the model copies them, and unknown words are refused).
Watch the commas: a list item must not end with one. If the file can't be read, the run
stops before it starts and says which line is wrong.

WHAT YOU SEE
    game text           scrolls by as usual
    dim text            the model's reasoning before each command
    bright command      what it typed
    [note] (purple)     a note it wrote for itself; [note done] when it drops one
    [yellow message]    a command that was refused, and why; it then tries again

WHAT THE MODEL KNOWS EACH TURN
No walkthroughs, only what the game shows it, plus any hints you give it:
  - your hints (see HINTS)
  - the latest game text, the last 10 moves, and which room it is in (with how many
    times it has been there)
  - its own notes (clues, puzzles, dangers: "Clearing: grating is locked, need a key")
  - the map, built as it plays: rooms, exits, routes, where items were seen
  - THINGS NOT YET TRIED, exits first: directions mentioned here but not tried, the
    nearest other room with untried exits and the route there, then up to 5 things here
    it hasn't examined (including nouns from the room description, using the game
    dictionary's noun markers). In a room whose description names no exits at all, the
    usual directions it hasn't tried there are listed as long shots.
  - ALREADY TRIED IN THIS ROOM: what it typed here before, on any visit or run, and the
    start of what the game said, marked when it changed something or when things have
    changed since
  - the room's objects and what it carries, read from the game's own data, like
    zplay's --debug view. This peeks: it can reveal hidden things (in tests it found a
    canary inside a closed egg). --fair turns it off.

RULES IT PLAYS BY
  - It sends "verbose" at the start of each run, so rooms are always described in full.
  - Every word of a command is checked against the game's dictionary first.
  - A command the game already didn't understand, or one that keeps getting the same
    answer, is refused and the model must try something else. "wait" and "z" may get
    the same answer up to 6 times, since waiting for something to happen is often needed.
  - A command it already typed in this room, on any visit, is refused if it changed
    nothing then and nothing has changed since: same score, same things carried, every
    object in the room and on the player in the same state, and the game's variables
    the same (like whether a seat belt is fastened). Variables that change even on
    "look", "examine" or "wait" (the move count, timers) are left out of this, and
    until a few such commands have been seen nothing is refused this way. A command
    that did something (like "take lamp") is never refused this way, so after a
    restart it can do the same things again.
  - It is told that time matters in these games, and to wait several turns when
    something is coming or nothing else works.
  - quit, restart, restore and save are not allowed.
  - It is told to explore first: try every exit and visit every room before working on
    puzzles, examining only what looks important along the way.
  - After 6 turns in one room with no score or new item, while the map still has
    untried exits, it is told to go and explore them, with the route.
  - When its last 8 moves between rooms were among 3 rooms or fewer, with no score or
    new item meanwhile, it is told it is going back and forth and pointed somewhere new.
  - After 15 turns with no new room, score or item, it is told so and pointed to
    unexplored exits, or to wait a few turns.
  - When it dies and the game offers to restart, it restarts, keeping its notes and map.
    If the game-over screen shows a full score or says congratulations, the run stops.
    What it tried in each room is forgotten whenever the game starts over (also with
    --restart or --load): those answers came from the old game.
  - Notes about where an item is are dropped once it carries that item.
  - A note that says nearly the same as an older one replaces it, so one idea can't fill
    the list. Notes that start with different places ("Red Dock: ...") are kept apart.
  - Exits are spotted in room descriptions: the compass directions, fore, aft, port and
    starboard (for ships), and up, down, in and out when the text is about exits.
  - A move refused for a reason that can change ("You'll have to stand up first", "The
    door is closed") isn't marked on the map as leading nowhere.

FILES (next to the story file; a later run carries on from them)
    <story>.auto.json       your hints, the model's notes, statistics (runs, turns, deaths,
                            best score), per room: visits and what it tried there, and
                            which game variables are noise (see RULES)
    <story>.auto.sav        where the game had got to, saved every turn (not the same as a
                            save you make with "save" in zplay.py; see --load)
    <story>.auto.map.json   its map, kept apart from your own <story>.map.json
    <story>.auto.map.pdf    the map, printable: redrawn whenever the map changes and when
                            the run stops, so it's always up to date (zmap_pdf.py makes
                            the same PDF by hand)
    <story>.auto.log        every run: game text, reasoning, replies and commands
    If the .auto.json or .auto.map.json files hold a different game (zork1.z3 and zork1.z5
    in one folder), they are left alone and this game's go in files with the release and
    serial added, e.g. zork1-r88-840726.auto.map.json.

WHAT TO EXPECT
About 4-6 seconds a turn with gemma4. It examines things thoroughly but wanders, revisits
places and can cling to a wrong idea for a while; in a 100-turn test of Zork it took the
jewelled egg (5 points) and found the grating. --think (the model reasons first) took
about 12 seconds a turn and played no better. A larger model should play better.

HOW THE CODE IS ORGANISED
  AutoScreen    the zplay screen, but each line of input comes from the Player
  AutoZMachine  remembers the game state at each prompt; save_position and
                resume_position write it out and put it back on the next run;
                load_save starts from a save file made in zplay.py (--load)
  Keys          single key presses (pause, stop) without Enter, in a terminal
  Player        builds each prompt, asks the model, checks the reply, keeps notes,
                handles game over, and saves its state
  parse_reply   pulls THINK / COMMAND / NOTE / DONE out of the model's answer
  From zplay_llm.py it reuses Ollama (the model client), Translator (the game's
  vocabulary and word checks), Tracker (the map) and LLMZMachine (the interpreter hooks).
"""

import argparse
import base64
import hashlib
import json
import os
import re
import select
import shutil
import sys
import time
import zlib
try:
    import termios
    import tty
except ImportError:                 # not a Unix terminal: no single-key controls
    termios = tty = None

import zplay
import zmap_pdf
from zplay_llm import (COMPASS, PARSER_FAILURES, SHIP_DIRS, LLMZMachine, Ollama, OllamaError, Tracker,
                       Translator, game_file)

HISTORY = 10            # recent moves shown to the model
OUTPUT_CHARS = 1500     # longest piece of game text kept per move
MAX_NOTES = 40          # notes kept (oldest dropped first)
WAIT_COMMANDS = {"wait", "z"}
WAIT_REPEATS = 6        # identical answers to "wait" before it's refused (others: 2)
STUCK_TURNS = 15        # turns without progress before the model is nudged to move on
LINGER_TURNS = 6        # turns in one room (no score, no new item) before it's told to explore
EXAMINE_SHOWN = 5       # unexamined things listed per turn
TRIED_KEPT = 40         # commands remembered per room
TRIED_SHOWN = 12        # of those, shown to the model each turn
BOUNCE_ARRIVALS = 8     # room arrivals looked at for going back and forth...
BOUNCE_ROOMS = 3        # ...among this many rooms or fewer, with no progress meanwhile
QUIET_VERBS = {"look", "l", "examine", "x", "read", "inventory", "i", "wait", "z", "score"}
QUIET_NEEDED = 3        # such commands seen before a repeat can be judged "nothing changed"
NOT_RECORDED = {"look", "l", "inventory", "i", "wait", "z", "verbose", "again", "g", "score",
                "brief", "superbrief"}
STOPWORDS = {"a", "an", "the", "to", "of", "in", "on", "at", "for", "and", "or", "it", "is",
             "be", "it's", "i", "my", "me", "then", "with", "from", "this", "that", "here",
             "now", "need", "try", "first", "still", "may", "might", "could", "should", "so"}
# Nouns too general to be worth suggesting.
DULL_NOUNS = {"all", "it", "them", "me", "myself", "you", "yourse", "yourself", "here", "room",
              "ground", "floor", "sky", "wall", "walls", "hands", "hand", "air", "light"}
EXAMINE_VERBS = ("examine", "x", "look at", "look in", "look under", "read", "search", "open")
FORBIDDEN = {"quit", "q", "restart", "restore", "save", "script", "unscript", "load"}
GAME_OVER = ("restart, restore, or quit", "restart, restore or quit", "restore, restart or quit",
             "restore, restart, or quit",    # Moonmist: "[Type RESTORE, RESTART, or QUIT.]"
             "restore your place from where you saved it",   # Moonmist's last screen
             "would you like to restart", "do you want to restart",
             "start the game again",         # Enchanter and other early Infocom games
             "reached a complete solution")  # Witness and the other mysteries: a win
# Words in a game-over question that wants a plain yes or no (answer "y", not "restart").
YES_NO = ("(y is affirmative)", "(y/n)", "yes or no")
# Notes about how far the player got: untrue once the game starts over.
PROGRESS_NOTE = re.compile(r"^\s*step\s*\d|\b(done|next|now|took|have|carrying|got|finished)\b", re.I)

# The score on a game's last screen: "350 out of 400", "7 of a possible 7",
# "Your score would be 400 (total of 400 points)" (Zork II),
# "Your score would be 80 (out of 80 points)" (Planetfall),
# "Your score is 80 (of 80 points)" (Stationfall).
SCORE_PATTERNS = (re.compile(r"(\d+) (?:points )?(?:out )?of (?:a possible )?(\d+)"),
                  re.compile(r"(\d+) \((?:total of|out of|of) (\d+) points\)"))


def final_score(output):
    """(score, maximum) from a game's score line, or None."""
    for pat in SCORE_PATTERNS:
        m = pat.search(output)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


SYSTEM_PROMPT = """\
You are playing the interactive fiction game "{title}" by typing commands, like an \
experienced player of Infocom-style adventures. There are no walkthroughs: work \
everything out from what the game tells you. If you are given HINTS FROM AN EXPERIENCED \
PLAYER, they are true: follow them. Your goal is to \
explore, solve puzzles and raise your score as far as you can.

How these games work:
- Commands are short: "north", "take lamp", "open mailbox", "examine rug", "read leaflet", \
"put coin in bag", "turn on lamp", "unlock door with key", "give fish to cat", "inventory".
- Directions: north, south, east, west, northeast, northwest, southeast, southwest, up, \
down, in, out. Room descriptions mention most exits, but not always all of them.
- Explore first: before working on any puzzle, visit every room you can reach and try \
every exit. Map the game out, then solve puzzles with everything you have seen.
- In a new room, examine only what looks important, read what's readable and take what's \
useful, then move on. Note puzzles (locked doors, strange machines) and come back to \
them once you run out of exits to try.
- Take things that could be useful: treasures, light sources, tools, weapons, keys, \
containers, food. Dropping things you don't need can help if you are carrying too much.
- Dark places need a light source: turn it on before going in, and off when you don't need it.
- When the score goes up, you did something right; note what it was.
- Some actions are deadly. If something seems dangerous, prepare first.
- When no exits are left to try, go back to unsolved puzzles: examine things closely, \
open containers, look under and behind things, and use what you carry.
- Time matters: things happen on their own (journeys, countdowns, people or creatures \
arriving, machines finishing). When the game hints that something is coming, or nothing \
else is working, type "wait" several times in a row. Repeating "wait" is fine.
- If the game doesn't understand you, use different, simpler words. Never repeat a \
command that just failed in the same situation; try something different.
- Check CARRYING before going after something: don't chase things you already have.
- Never use: quit, restart, restore, save.
- Use only words from the vocabulary below (it lists only the first {nletters} letters of \
longer words, which is all the game checks).

Rooms, exits and where items are, are tracked for you in MAP NOTES. Use NOTE only for \
what the map can't show: unsolved puzzles, locked or blocked things and what they might \
need, clues, dangers, and what earned points. Never note room descriptions or exits, and \
never note something you haven't actually seen happen.

Reply in exactly this format, and nothing else. Start with the COMMAND line; don't restate \
the hints or think out loud before it:
COMMAND: the one command to type next
THINK: one short sentence: what you are trying to do now and why
NOTE: (optional, at most one) e.g. "Clearing: grating is locked, need a key"
DONE: (optional) a few words from one of your notes that is no longer true

Vocabulary: {vocab}
"""


class AutoScreen(zplay.Screen):
    """The zplay screen, with input supplied by the Player instead of the keyboard."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.player: "Player" = None  # type: ignore[assignment]
        self.since_input = ""           # game text since the last command (the Tracker reads it)
        self.last_line = ""
        self.raw_next = False           # set by LLMZMachine before a file-name prompt

    def style(self, s, code):
        return "\x1b[%sm%s\x1b[0m" % (code, s) if self.ansi else s

    def note(self, s, code="2;36"):
        if self.col > 0 or self.pending:
            self.flush()
            sys.stdout.write("\n")
            self.col = 0
        sys.stdout.write(self.style(s, code) + "\n")
        sys.stdout.flush()

    def write(self, s):
        self.since_input += s
        super().write(s)

    def read_line(self):
        if self.raw_next:               # a file name; shouldn't happen, but never hang on it
            self.raw_next = False
            self.flush()
            sys.stdout.write("\n")
            return ""
        output, self.since_input = self.since_input, ""
        cmd = self.player.next_command(output)
        self.flush()
        sys.stdout.write(self.style(cmd, "1;36") + "\n")
        self.col = 0
        self.last_line = cmd
        return cmd

    def read_char(self):
        self.flush()                    # "press any key": just carry on
        sys.stdout.write("\n")
        self.col = 0
        return "\n"


class AutoZMachine(LLMZMachine):
    """Remembers the game's state each time it asks for a command, so the position can be
    saved and the next run can carry on from it."""
    read_state = None

    def op_read(self, text, parse=0, *rest):
        self.read_state = self.snapshot() + (text, parse)
        super().op_read(text, parse, *rest)


def save_position(zm, path):
    """Write the game's position (as it was when it last asked for a command) to path."""
    if not zm.read_state:
        return
    dyn, frames, pc, text, parse = zm.read_state
    d = {"format": "zplay-auto-1", "story": list(zm.story_id()),
         "dynamic": base64.b64encode(zlib.compress(dyn)).decode(),
         "frames": [[f.ret_pc, f.locals, f.store, f.stack, f.argc] for f in frames],
         "pc": pc, "read": [text, parse]}
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(d, fh)
        os.replace(tmp, path)
    except OSError:
        pass


def resume_position(zm, path):
    """Put the game back where a saved position left it, answering the command prompt it
    was waiting at with "look". Returns True if it did."""
    try:
        with open(path) as fh:
            d = json.load(fh)
        if d.get("format") != "zplay-auto-1" or d["story"] != list(zm.story_id()):
            return False
        dyn = zlib.decompress(base64.b64decode(d["dynamic"]))
        frames = [zplay.Frame(r, l, s, a, st) for r, l, s, st, a in d["frames"]]
        text, parse = d["read"]
        pc = d["pc"]
    except (OSError, ValueError, KeyError, TypeError, IndexError, zlib.error):
        return False
    zm.restore_snapshot(dyn, frames, pc)
    zm.finish_read(text, parse, "look")
    return True


def unreadable(path):
    """What is wrong with a JSON file, or None if it reads (or isn't there)."""
    try:
        with open(path) as fh:
            json.load(fh)
    except FileNotFoundError:
        return None
    except OSError as e:
        return e.strerror or str(e)
    except ValueError as e:
        return str(e)
    return None


def load_save(zm, path):
    """Start the game from a save file: one made with "save" in zplay.py, or a copy of a
    <story>.auto.sav. Returns (problem, look): problem is None if it worked, and look is
    True if "look" still needs typing to show where the player is."""
    try:
        with open(path) as fh:
            d = json.load(fh)
    except OSError as e:
        return e.strerror or str(e), False
    except ValueError:
        return "it isn't a zplay save file", False
    try:
        fmt = d.get("format") if isinstance(d, dict) else None
        if fmt == "zplay-auto-1":
            ok = resume_position(zm, path)        # answers its prompt with "look" itself
            return (None if ok else "it is from a different game"), False
        if fmt != "zplay-1":
            return "it isn't a zplay save file", False
        if list(d["story"]) != list(zm.story_id()):
            return "it is from a different game", False
        dyn = zlib.decompress(base64.b64decode(d["dynamic"]))
        frames = [zplay.Frame(r, l, s, a, st) for r, l, s, st, a in d["frames"]]
        pc = d["pc"]
    except (ValueError, KeyError, TypeError, IndexError, zlib.error) as e:
        return "it can't be read (%s)" % e, False
    # the save was made inside the game's "save" command: finish that command as a
    # successful restore would, and the game carries on from there
    zm.restore_snapshot(dyn, frames, pc)
    zm.result(2 if zm.version >= 4 else 1)
    return None, True


class Keys:
    """Single key presses while the game plays. Only works in a terminal."""

    def __init__(self):
        self.fd = self.old = None
        try:
            if termios and sys.stdin.isatty():
                fd = sys.stdin.fileno()
                self.old = termios.tcgetattr(fd)
                tty.setcbreak(fd)           # keys arrive at once, unechoed; Ctrl-C still works
                self.fd = fd
        except (termios.error, OSError, ValueError):
            pass

    def pressed(self):
        """The keys pressed since the last call ("" if none)."""
        keys = ""
        try:
            while self.fd is not None and select.select([self.fd], [], [], 0)[0]:
                b = os.read(self.fd, 1)
                if not b:
                    break
                keys += b.decode("latin-1")
        except OSError:
            pass
        return keys

    def wait(self):
        """Wait for one key."""
        if self.fd is None:
            return ""
        return os.read(self.fd, 1).decode("latin-1")

    def read_line(self, prompt):
        """Read a typed line, with echo and editing, then go back to single keys."""
        if self.fd is None:
            return ""
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
        try:
            return input(prompt).strip()
        except EOFError:
            return ""
        finally:
            tty.setcbreak(self.fd)

    def close(self):
        if self.fd is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
            self.fd = None


class Player:
    """Decides each command by asking the model."""

    def __init__(self, zm, llm, title, args, state_path, log, pos_path=None, keys=None):
        self.zm = zm
        self.pos_path = pos_path        # where the game position is saved each turn
        self.keys = keys
        self.llm = llm
        self.title = title
        self.args = args
        self.state_path = state_path
        self.log = log
        self.screen = zm.screen
        self.vocab = Translator(llm, zm, title)     # used for the dictionary and word checks
        self.tracker = zm.tracker
        self.history = []               # [(command, output)]
        self.notes = []
        self.hints = []                 # the user's own hints: always shown, never trimmed
        self.stats = {"runs": 0, "turns": 0, "deaths": 0, "best_score": None}
        self.turn = 0
        self.pending_cmd = None         # the command whose output we are waiting for
        self.last_progress = 0
        self.linger_room = None         # the room the model is in, and the turn it got there
        self.linger_start = 0
        self.rooms = {}                 # room -> {"visits": n, "tried": {cmd: {...}}}; saved
        self.arrivals = []              # [(turn, room)] each time it entered a room
        self.cmd_room = self.cmd_sig = None     # where the pending command was typed, and
                                                # the state of things then
        self.map_sig = None             # what the map PDF was last drawn from
        self.cmd_globals = None         # the game's variables when the command was typed
        self.noisy = set()              # variables that change even when nothing happens
        self.quiet_turns = 0            # (seen on look, examine, wait ...), and how many
                                        # such turns that was learned from; saved
        self.progress_mark = None
        self.after_restart = False
        self.examined = set()           # (room, word) pairs the model has looked at
        self.descs = {}                 # room -> its latest full description
        self.started = False
        self.system = None
        self.paused = False             # paused: the user types the commands
        self.queued = []                # commands to send before asking the model
        self.load(hints_only=args.fresh)
        self.stats["runs"] += 1

    # ---- persistence
    def load(self, hints_only=False):
        """Read hints, notes and stats from the state file. Returns a message saying what
        was wrong with the file, or None if it was fine (or not there yet)."""
        try:
            with open(self.state_path) as fh:
                d = json.load(fh)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            return str(e)
        if not isinstance(d, dict) or d.get("story") != list(self.zm.story_id()):
            return None
        hints, notes = d.get("hints", []), d.get("notes", [])
        if not isinstance(hints, list) or not isinstance(notes, list):
            return '"hints" and "notes" must each be a list of strings in quotes'
        self.hints = [str(h).strip() for h in hints if str(h).strip()]
        if not hints_only:
            self.notes = [str(n) for n in notes][-MAX_NOTES:]
            if isinstance(d.get("stats"), dict):
                self.stats.update(d["stats"])
            if isinstance(d.get("rooms"), dict):
                self.rooms = d["rooms"]
            noise = d.get("noise", {})
            if isinstance(noise, dict) and isinstance(noise.get("globals"), list):
                self.noisy = set(noise["globals"])
                self.quiet_turns = int(noise.get("learned_from", 0))
        return None

    def save(self):
        d = {"story": list(self.zm.story_id()), "hints": self.hints, "notes": self.notes,
             "stats": self.stats, "rooms": self.rooms,
             "noise": {"globals": sorted(self.noisy), "learned_from": self.quiet_turns}}
        try:
            tmp = self.state_path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(d, fh, indent=1)
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    # ---- reading the game
    def score(self):
        """(score, moves) from the status-line variables in v3 games; None otherwise."""
        zm = self.zm
        if zm.version > 3 or zm.mem[1] & 0x02:      # v4+ or a game that shows time instead
            return None
        g = lambda n: zplay.s16(zm.rw(zm.globals + 2 * n))
        return g(1), g(2)

    def objects_here(self):
        """The current room's contents from the game's own data (like zplay --debug)."""
        tk, zm = self.tracker, self.zm
        loc = tk.location()[2]
        if not loc:
            return "", ""
        here, carried = [], []

        def walk(o, depth, out):
            for c in tk.children(o):
                name = zm.obj_name(c)
                if c == tk.player:
                    walk(c, 0, carried)
                    continue
                if not name or len(out) >= 40:
                    continue
                out.append("  " * depth + "- " + name)
                if depth < 3:
                    walk(c, depth + 1, out)
        walk(loc, 0, here)
        return "\n".join(here), "\n".join(carried)

    def nouns(self):
        """Dictionary words marked as nouns. Infocom's and Inform's dictionaries both flag
        nouns with the top bit of an entry's first data byte."""
        if not hasattr(self, "_nouns"):
            zm = self.zm
            keylen = 4 if zm.version <= 3 else 6
            self._nouns = {zm.decode(e)[0] for e in zm.load_dict(zm.dict_addr)[1].values()
                           if zm.mem[e + keylen] & 0x80}
        return self._nouns

    def mentioned_nouns(self, text):
        n = 6 if self.zm.version <= 3 else 9
        nouns, out = self.nouns(), []
        for w in re.findall(r"[a-z][a-z-]*", text.lower()):
            if w[:n] in nouns and w not in DULL_NOUNS and w[:n] not in DULL_NOUNS and w not in out:
                out.append(w)
        return out

    def progress(self):
        s = self.score()
        carried = sum(1 for it in self.tracker.items.values() if it.get("carried"))
        return (len(self.tracker.rooms), s[0] if s else 0, carried)

    # ---- the prompt
    def system_prompt(self):
        v = self.vocab
        v.refresh_vocab()
        return SYSTEM_PROMPT.format(title=self.title, nletters=v.nletters, vocab=" ".join(v.vocab))

    def build_prompt(self, output, feedback=None):
        parts = []
        if self.hints:
            parts.append("HINTS FROM AN EXPERIENCED PLAYER (true; follow them):\n"
                         + "\n".join("- " + h for h in self.hints))
        parts.append("YOUR NOTES:\n" + ("\n".join("- " + n for n in self.notes) or "(none yet)"))
        mapnotes = self.tracker.context()
        if mapnotes:
            parts.append(mapnotes)
        if not self.args.fair:
            here, carried = self.objects_here()
            if here:
                parts.append("OBJECTS IN THIS LOCATION (from the game's data; some may be "
                             "hidden, part of the scenery, or inside closed things):\n" + here)
            parts.append("CARRYING (from the game's data):\n" + (carried or "- nothing"))
        s = self.score()
        status = "TURN %d of %d" % (self.turn, self.args.turns)
        if s:
            status += "   SCORE %d   MOVES %d" % s
        if self.stats["deaths"]:
            status += "   DEATHS SO FAR %d" % self.stats["deaths"]
        parts.append(status)
        if self.history:
            lines = []
            for cmd, out in self.history[-HISTORY:-1]:
                lines.append("> %s\n%s" % (cmd, clip(out, 600)))
            if lines:
                parts.append("EARLIER MOVES (oldest first):\n" + "\n\n".join(lines))
        last = self.history[-1][0] if self.history else None
        here = self.tracker.here
        if here:
            visits = self.rooms.get(here, {}).get("visits", 0)
            parts.append("YOU ARE IN: %s%s" % (self.tracker.rname(here),
                         " (visit %d: you have been here before)" % visits if visits > 1 else ""))
        parts.append("LATEST:\n" + ("> %s\n" % last if last else "") + clip(output, OUTPUT_CHARS))
        tried = self.tried_here()
        if tried:
            parts.append(tried)
        todo = self.things_to_try()
        if todo:
            parts.append("THINGS NOT YET TRIED:\n" + todo)
        if self.turn - self.last_progress >= STUCK_TURNS:
            parts.append(self.stuck_hint())
        else:
            move_on = self.bounce_hint() or self.linger_hint()
            if move_on:
                parts.append(move_on)
        if feedback:
            parts.append("PROBLEM WITH YOUR LAST ANSWER: " + feedback)
        parts.append("What is your next command?")
        return "\n\n".join(parts)

    def object_names(self):
        """Names of the things in the current room (not the player or what it carries)."""
        tk = self.tracker
        if not self.args.fair:
            loc = tk.location()[2]
            names, todo = [], list(tk.children(loc)) if loc else []
            while todo and len(names) < 40:
                o = todo.pop(0)
                if o == tk.player:
                    continue
                name = self.zm.obj_name(o)
                if name:
                    names.append(name)
                todo += tk.children(o)
            return names
        return [it["name"] for it in tk.items.values()
                if it.get("room") == tk.here and not it.get("carried")]

    def note_examined(self, cmd):
        c = cmd.lower()
        for verb in EXAMINE_VERBS:
            if c.startswith(verb + " "):
                for w in c[len(verb) + 1:].split():
                    self.examined.add((self.tracker.here, w))

    def untried_exits(self, room):
        d = self.tracker.rooms.get(room or "", {})
        return [m for m in d.get("mentioned", [])
                if m not in d.get("exits", {}) and m not in d.get("blocked", [])]

    def long_shots(self, room):
        """For a room whose description names no directions at all: the usual directions
        not yet tried there. Exits are often there without being mentioned."""
        d = self.tracker.rooms.get(room or "", {})
        if d.get("mentioned"):
            return []
        ship = tuple(w for w in SHIP_DIRS if self.vocab.is_known(w))
        order = ("north", "south", "east", "west", "up", "down") + ship + COMPASS[:4]
        return [c for c in order
                if c not in d.get("exits", {}) and c not in d.get("blocked", [])][:8]

    def nearest_unexplored(self):
        """(room, route, exits) for the closest other room with untried exits, or None."""
        best = None
        for r, path in self.tracker.routes().items():
            left = self.untried_exits(r)
            if left and path and (best is None or len(path) < len(best[1])):
                best = (r, path, left)
        return best

    def things_to_try(self):
        tk = self.tracker
        lines = []
        untried = self.untried_exits(tk.here)
        if untried:
            lines.append("- exits here not yet tried: " + ", ".join(untried))
        best = self.nearest_unexplored()
        if best:
            lines.append("- nearest unexplored exits elsewhere: %s (%s) - route: %s" % (
                tk.rname(best[0]), ", ".join(best[2]), ", ".join(best[1])))
        elif not untried:
            shots = self.long_shots(tk.here)
            if shots:
                lines.append("- the description names no exits, so try the usual directions "
                             "(long shots): " + ", ".join(shots))
        names = self.object_names()
        known = " ".join(names).lower()
        names += [w for w in self.mentioned_nouns(self.descs.get(tk.here, "")) if w not in known]
        fresh = [n for n in names
                 if not any((tk.here, w) in self.examined for w in n.lower().split())]
        if fresh:
            lines.append("- things here you haven't examined: " + ", ".join(fresh[:EXAMINE_SHOWN])
                         + (" (and %d more)" % (len(fresh) - EXAMINE_SHOWN)
                            if len(fresh) > EXAMINE_SHOWN else ""))
        return "\n".join(lines)

    def linger_hint(self):
        """A push to explore when the model has stayed in one room a while and the map
        still has exits nobody has tried."""
        stay = self.turn - max(self.linger_start, self.last_progress)
        if stay < LINGER_TURNS:
            return None
        tk = self.tracker
        untried = self.untried_exits(tk.here)
        if untried:
            where = "try the exits here: %s." % ", ".join(untried)
        else:
            best = self.nearest_unexplored()
            if not best:
                return None     # the known map is used up: puzzles are the way on
            where = "go to %s and try %s. Route: %s." % (
                tk.rname(best[0]), ", ".join(best[2]), ", ".join(best[1]))
        return ("You have spent %d turns in this room without scoring or finding anything. "
                "Exploring comes first, so %s Come back to this room's puzzles later." % (stay, where))

    def bounce_hint(self):
        """A push when the model keeps going back and forth between the same few rooms."""
        last = self.arrivals[-BOUNCE_ARRIVALS:]
        if len(last) < BOUNCE_ARRIVALS or last[0][0] < self.last_progress:
            return None
        rooms = {r for _, r in last}
        if len(rooms) > BOUNCE_ROOMS:
            return None
        tk = self.tracker
        names = sorted({tk.rname(r) for r in rooms})
        names = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]
        best = self.nearest_unexplored()
        if best and best[0] not in rooms:
            where = "Go somewhere new: %s (untried: %s). Route: %s." % (
                tk.rname(best[0]), ", ".join(best[2]), ", ".join(best[1]))
        elif self.untried_exits(tk.here):
            where = "Try the exits here: %s." % ", ".join(self.untried_exits(tk.here))
        else:
            where = ("Stop walking between them: pick one unsolved puzzle from your notes and "
                     "try something you haven't tried on it.")
        return ("You keep going back and forth between %s (%d moves between rooms) without "
                "scoring or finding anything. %s" % (names, len(last), where))

    def read_globals(self):
        zm = self.zm
        return [zm.rw(zm.globals + 2 * i) for i in range(240)]

    def learn_noise(self, cmd):
        """After a command that can't change anything (look, examine, wait ...), any game
        variable that changed is noise: the parser's own records, the move count, timers."""
        before, self.cmd_globals = self.cmd_globals, None
        words = self.cmd_key(cmd).split()
        if not before or not words or words[0] not in QUIET_VERBS:
            return
        try:
            now = self.read_globals()
        except (IndexError, zplay.ZError):
            return
        self.noisy |= {i for i, (a, b) in enumerate(zip(before, now)) if a != b}
        self.quiet_turns += 1

    def steady_globals(self):
        """The game's variables that hold real state (like whether a seat belt is fastened)."""
        if self.quiet_turns < QUIET_NEEDED:
            self.unsure = getattr(self, "unsure", 0) + 1
            return ["unsure", self.unsure]      # not learned yet: never matches, so nothing
                                                # counts as unchanged and nothing is refused
        return [v for i, v in enumerate(self.read_globals()) if i not in self.noisy]

    def state_sig(self):
        """A short fingerprint of everything a command here could change: the score, what
        is carried, the game's variables (like whether a seat belt is fastened), and every
        object (with its state) in the room and on the player."""
        tk, zm = self.tracker, self.zm
        try:
            parts = [self.score()[0] if self.score() else None, self.steady_globals()]
            loc = tk.location()[2]
            objs = set()
            if loc:
                objs = tk.subtree(loc, depth=5)
            if tk.player:
                objs |= tk.subtree(tk.player, depth=5) | {tk.player}
            parts += [(o, zm.orel(o, 0), tuple(zm.attrs(o))) for o in sorted(objs)]
            parts.append(sorted(k for k, it in tk.items.items() if it.get("carried")))
        except (IndexError, zplay.ZError):
            return None
        return hashlib.md5(repr(parts).encode()).hexdigest()[:12]

    @staticmethod
    def cmd_key(cmd):
        return " ".join((cmd or "").lower().split())

    def recordable(self, cmd):
        """Commands remembered per room: everything but looking, waiting and the like.
        Moves are remembered only when they went nowhere."""
        key = self.cmd_key(cmd)
        return bool(key) and key not in NOT_RECORDED

    def record_tried(self, cmd, output):
        """Remember what cmd did in the room it was typed in, and whether it changed anything."""
        room = self.cmd_room
        if not room or not self.recordable(cmd) or self.cmd_sig is None:
            return
        if Tracker.norm(cmd)[1] and self.tracker.here != room:
            return                  # a move that worked: the map has it
        lines = [ln.strip() for ln in output.strip().splitlines()
                 if ln.strip() and ln.strip() != ">"]
        answer = clip_start(" ".join(lines), 90)
        tried = self.rooms.setdefault(room, {"visits": 0}).setdefault("tried", {})
        key = self.cmd_key(cmd)
        tried.pop(key, None)                        # newest last
        tried[key] = {"answer": answer, "before": self.cmd_sig, "after": self.state_sig()}
        for old in list(tried)[:-TRIED_KEPT]:
            del tried[old]

    def forget_tried(self):
        """Forget what was typed in each room. Call when the game starts over: the answers
        belong to the old game, and the model would take them as true for the new one."""
        for d in self.rooms.values():
            d.pop("tried", None)

    def tried_here(self):
        """What the model has already typed in this room, on any visit, and what it got."""
        tried = self.rooms.get(self.tracker.here or "", {}).get("tried", {})
        if not tried:
            return ""
        now = self.state_sig()
        lines = []
        for cmd, t in list(tried.items())[-TRIED_SHOWN:]:
            mark = ""
            if t["before"] != t["after"]:
                mark = " (this changed something)"
            elif t["before"] != now:
                mark = " (things have changed since; might work now)"
            lines.append('- %s -> "%s"%s' % (cmd, t["answer"], mark))
        more = len(tried) - TRIED_SHOWN
        return ("ALREADY TRIED IN THIS ROOM (on any visit; don't repeat these unless something "
                "has changed%s):\n" % ("; %d older ones not shown" % more if more > 0 else "")
                + "\n".join(lines))

    def stuck_hint(self):
        tk = self.tracker
        d = tk.rooms.get(tk.here or "", {})
        ship = tuple(w for w in SHIP_DIRS if self.vocab.is_known(w))
        untried = [c for c in COMPASS + ship + ("up", "down")
                   if c not in d.get("exits", {}) and c not in d.get("blocked", [])]
        mentioned = [m for m in d.get("mentioned", []) if m in untried]
        return ("You have made no progress (no new rooms, score or items) for %d turns. "
                "Try something new: %s Or go back to a place with an unsolved puzzle, or wait a "
                "few turns in case something is about to happen."
                % (self.turn - self.last_progress,
                   ("directions mentioned here but not tried: %s." % ", ".join(mentioned))
                   if mentioned else ("untried directions here: %s." % ", ".join(untried[:6]))
                   if untried else "every direction here has been tried."))

    # ---- one turn
    @staticmethod
    def won(output):
        """A short reason if a game-over screen looks like a win, else None: the score shown
        is the full score, or the text says so ("congratulations", "you have won")."""
        got = final_score(output)
        if got and got[0] == got[1] and got[1] > 0:
            return "full score, %s of %s" % got
        low = output.lower()
        for phrase in ("you have won", "you've won", "congratulations",
                       "reached a complete solution",        # Witness
                       "you successfully completed your task"):  # Suspended
            if phrase in low:
                return '"%s"' % phrase
        return None

    def next_command(self, output):
        if self.pending_cmd is not None:
            self.history.append((self.pending_cmd, output))
            del self.history[:-HISTORY]
            self.learn_noise(self.pending_cmd)
            self.record_tried(self.pending_cmd, output)
        self.log_text(output)
        low = output.lower()

        # game over or an "are you sure?" after restarting: answer for the player
        if any(p in low for p in GAME_OVER):
            won = self.won(output)
            if won:
                # finished the story: stop here instead of starting a new game
                self.screen.note("  [the story is finished: %s - stopping]" % won, "1;32")
                self.log_text("[auto] story finished (%s), stopping\n" % won)
                got = final_score(output)
                if got and (self.stats["best_score"] is None or got[0] > self.stats["best_score"]):
                    self.stats["best_score"] = got[0]
                raise zplay.Quit()
            self.stats["deaths"] += 1
            last = " ".join(output.split())[-200:]
            self.forget_progress()
            self.add_note("Died once after: %s" % (self.pending_cmd or "?"))
            self.add_note("The game started over from the very beginning after that death: "
                          "nothing from before is done or carried any more.")
            self.screen.note("  [game over (%s) - restarting; notes and map are kept]" % last[-60:])
            self.log_text("[auto] game over, restarting\n")
            self.forget_tried()
            self.started = False                    # send "verbose" again after restarting
            if any(p in low[-120:] for p in YES_NO):
                return self.sent("y")               # "start again? (Y is affirmative)"
            self.after_restart = True
            return self.sent("restart")
        if self.after_restart and "?" in output[-80:]:
            self.after_restart = False
            return self.sent("y")
        self.after_restart = False

        here = self.tracker.here
        first = output.strip().splitlines()[0].strip() if output.strip() else ""
        if here and first == self.tracker.rname(here) and len(output.strip()) > len(first) + 20:
            self.descs[here] = output               # the room's full description

        # make the game always describe rooms in full (Infocom/Inform "verbose")
        if not self.started:
            self.started = True
            if self.vocab.is_known("verbose"):
                self.screen.note("  [asking the game for full room descriptions]")
                return self.sent("verbose")
        if self.queued:
            return self.sent(self.queued.pop(0))

        if self.pos_path:
            save_position(self.zm, self.pos_path)
        self.turn += 1
        self.stats["turns"] = self.stats.get("turns", 0) + 1
        mark = self.progress()
        if mark != self.progress_mark:
            self.progress_mark, self.last_progress = mark, self.turn
        if self.tracker.here != self.linger_room:
            self.linger_room, self.linger_start = self.tracker.here, self.turn
            if self.tracker.here:
                r = self.rooms.setdefault(self.tracker.here, {"visits": 0})
                r["visits"] = r.get("visits", 0) + 1
                self.arrivals.append((self.turn, self.tracker.here))
                del self.arrivals[:-BOUNCE_ARRIVALS * 2]
        self.draw_map()
        s = self.score()
        if s and (self.stats["best_score"] is None or s[0] > self.stats["best_score"]):
            self.stats["best_score"] = s[0]
        if self.turn > self.args.turns:
            self.screen.note("  [turn limit reached]")
            raise zplay.Quit()

        cmd = self.check_keys()
        if cmd:                     # the user's own command; don't save over their edits
            return self.sent(cmd)
        self.forget_carried()
        cmd = self.ask(output)
        self.save()
        if self.args.delay:
            time.sleep(self.args.delay)
        return self.sent(cmd)

    def sent(self, cmd):
        self.pending_cmd = cmd
        self.cmd_room = self.tracker.here
        self.cmd_sig = self.state_sig() if self.recordable(cmd) else None
        try:
            self.cmd_globals = self.read_globals()
        except (IndexError, zplay.ZError):
            self.cmd_globals = None
        self.note_examined(cmd)
        self.log_text("> %s\n" % cmd)
        return cmd

    def ask(self, output):
        feedback, cmd = None, ""
        for _ in range(3):
            prompt = self.build_prompt(output, feedback)
            if self.system is None:
                self.system = self.system_prompt()
            if self.args.show_prompt:
                self.screen.note(prompt, "2")
            try:
                reply = self.llm.chat([{"role": "system", "content": self.system},
                                       {"role": "user", "content": prompt}])
            except OllamaError as e:
                self.screen.note("  [model error: %s; waiting 5s]" % e, "33")
                time.sleep(5)
                continue
            think, notes, done, cmd = parse_reply(reply)
            self.log_text("[think] %s\n[reply] %s\n" % (think, reply.strip().replace("\n", " | ")))
            if think:
                self.screen.note("  " + think)
            for n in done:
                self.drop_note(n)
            for n in notes[:1]:
                self.add_note(n)
            problem = self.check(cmd)
            if not problem:
                return cmd
            feedback = problem
            self.screen.note("  [%s]" % problem, "2;33")
        return cmd if cmd and cmd.split()[0] not in FORBIDDEN else "look"

    def check(self, cmd):
        """Why cmd shouldn't be sent, or None if it's fine."""
        if not cmd:
            return ("No COMMAND line (long replies get cut off). Make the very first line of your "
                    "reply 'COMMAND: <command>', then one short THINK line.")
        if cmd.split()[0] in FORBIDDEN:
            return "'%s' is not allowed here. Choose a command that plays the game." % cmd
        bad = self.vocab.unknown_words(cmd)
        if bad:
            return ("The game doesn't know these words: %s. Use words from the vocabulary."
                    % ", ".join(bad))
        here = self.tracker.here
        for prev, out in self.history[-12:]:
            if prev == cmd and self.history and any(p in out.lower() for p in PARSER_FAILURES):
                return ("'%s' was already tried and the game didn't understand it. "
                        "Use different words." % cmd)
        t = self.rooms.get(here or "", {}).get("tried", {}).get(self.cmd_key(cmd))
        if (t and self.recordable(cmd) and t["before"] == t["after"]
                and t["before"] == self.state_sig()):
            return ('You already tried \'%s\' here and the game said: "%s" Nothing has changed '
                    "since (same score, same things carried, nothing here changed), so it would "
                    "do the same. Try something else, or go somewhere else." % (cmd, t["answer"]))
        same = [out for prev, out in self.history[-8:] if prev == cmd]
        limit = WAIT_REPEATS if cmd in WAIT_COMMANDS else 2
        if len(same) >= limit and here and len(set(same[-limit:])) == 1:
            return ("You have already tried '%s' and got the same answer each time. "
                    "Do something different." % cmd)
        return None

    # ---- pausing
    def check_keys(self):
        """p or space pauses, q stops. While paused the user can type commands for the game
        and edit the state file, which is read again before the model carries on. Returns
        the user's command, or None to let the model choose."""
        keys = self.keys.pressed().lower() if self.keys else ""
        if "q" in keys:
            self.screen.note("[stopping]", "1;33")
            raise zplay.Quit()
        if not self.paused:
            if "p" not in keys and " " not in keys:
                return None
            self.save()
            self.paused = True
            self.screen.note("[paused. Type a command for the game and press Enter to play it "
                             "yourself, as many as you like. Just Enter lets the model carry "
                             "on; q stops. You can edit the hints and notes in %s now.]"
                             % self.state_path, "1;33")
        while True:
            self.screen.flush()
            line = self.keys.read_line(self.screen.style("you> ", "1;33"))
            if line.lower() == "q":
                self.load()                 # keep any edits to the file
                self.screen.note("[stopping]", "1;33")
                raise zplay.Quit()
            if line:
                if line.split()[0].lower() in FORBIDDEN:
                    self.screen.note("['%s' isn't allowed here]" % line, "1;33")
                    continue
                if self.screen.ansi:        # the command is echoed again by the screen
                    sys.stdout.write("\x1b[1A\r\x1b[K")
                self.log_text("[you typed this one]")
                return line.lower()
            problem = self.load()
            if not problem:
                break
            self.screen.note("[can't read %s: %s. Fix it and press Enter (q stops; the file "
                             "will then be overwritten).]" % (self.state_path, problem), "1;33")
        self.paused = False
        self.screen.note("[carrying on: %d hints, %d notes]" % (len(self.hints), len(self.notes)),
                         "1;33")
        return None

    # ---- notes
    @staticmethod
    def note_words(n):
        """A note's place ("Red Dock" in "Red Dock: door locked") and its content words."""
        place = n.split(":", 1)[0].strip().lower() if ":" in n[:30] else None
        words = {w.rstrip("s") if len(w) > 3 else w
                 for w in re.findall(r"[a-z0-9]+", n.lower()) if w not in STOPWORDS}
        return place, words

    def add_note(self, n):
        """Add a note. One that says nearly the same as an older note replaces it, so one
        idea can't fill the list: notes about different places are always kept apart."""
        n = n.strip()
        if not n or n.lower() in (x.lower() for x in self.notes):
            return
        place, words = self.note_words(n)
        for old in list(self.notes):
            oplace, ow = self.note_words(old)
            if place and oplace and place != oplace:
                continue
            shared = len(words & ow)
            if words and ow and (shared / len(words | ow) >= 0.5
                                 or (shared >= 4 and shared * 2 >= min(len(words), len(ow)))):
                self.notes.remove(old)
        self.notes.append(n)
        del self.notes[:-MAX_NOTES]
        self.screen.note("  [note] " + n, "2;35")

    def forget_progress(self):
        """When the game starts over, notes saying how far the player got ("Step 3 done",
        "took the lamp") are no longer true. Notes about the world are kept."""
        for n in list(self.notes):
            if PROGRESS_NOTE.search(n):
                self.notes.remove(n)
        self.screen.note("  [progress notes dropped: the game is starting over]", "2;35")

    def forget_carried(self):
        """Notes about where an item is go stale once the player carries it."""
        carried = [it["name"].lower().split()[-1] for it in self.tracker.items.values()
                   if it.get("carried")]
        for n in list(self.notes):
            low = n.lower()
            # only notes about WHERE an item is: "lamp is in the living room", "get the lamp"
            if any(re.search(r"\b%s\b(\s+\w+){0,2}\s+(in|on|at|inside|under|near)\b" % re.escape(w), low)
                   or re.search(r"\b(find|get|take|fetch|grab)\b(\s+\w+){0,2}\s+%s\b" % re.escape(w), low)
                   for w in carried):
                self.notes.remove(n)
                self.screen.note("  [note dropped: you carry it now] " + n, "2;35")

    def drop_note(self, words):
        w = words.strip().lower()
        if len(w) < 3:
            return
        for n in list(self.notes):
            if w in n.lower():
                self.notes.remove(n)
                self.screen.note("  [note done] " + n, "2;35")

    def pdf_path(self):
        path = self.tracker.path
        return (path[:-len(".json")] if path.endswith(".json") else path) + ".pdf"

    def draw_map(self, force=False):
        """Redraw <story>.auto.map.pdf when the map has changed (new rooms, exits, items)."""
        tk = self.tracker
        if not tk.rooms:
            return
        sig = repr((sorted((r, sorted(d.get("exits", {}).items()), sorted(d.get("blocked", [])),
                            sorted(d.get("mentioned", []))) for r, d in tk.rooms.items()),
                    sorted((k, it.get("room"), it.get("carried")) for k, it in tk.items.items())))
        if sig == self.map_sig and not force:
            return
        self.map_sig = sig
        try:
            data = json.loads(json.dumps({"rooms": tk.rooms, "items": tk.items, "here": tk.here}))
            gm = zmap_pdf.GameMap(data)
            gm.layout()
            title = "%s map" % self.title
            zmap_pdf.write_pdf(self.pdf_path(), [zmap_pdf.draw_map(gm, title)]
                               + list(zmap_pdf.list_pages(gm, title)), title)
        except Exception as e:      # a drawing problem must never stop the game
            self.log_text("[map PDF not written: %s]" % e)

    def end_of_story(self, output):
        """The game stopped on its own: log the text it printed last, and record a win."""
        self.screen.since_input = ""
        if not output.strip():
            return
        self.log_text(output)
        won = self.won(output)
        if won:
            self.screen.note("  [the story is finished: %s - stopping]" % won, "1;32")
            self.log_text("[auto] story finished (%s), stopping\n" % won)
            got = final_score(output)
            if got and (self.stats["best_score"] is None or got[0] > self.stats["best_score"]):
                self.stats["best_score"] = got[0]
        else:
            self.screen.note("  [the game stopped by itself]")
            self.log_text("[auto] the game stopped by itself\n")

    def log_text(self, s):
        if self.log and s:
            self.log.write(s if s.endswith("\n") else s + "\n")
            self.log.flush()

    def summary(self):
        s = self.score()
        lines = ["", "=== %s: %d turns this run, %d rooms on the map, %d deaths so far ===" % (
            self.title, self.turn, len(self.tracker.rooms), self.stats["deaths"])]
        if s:
            lines.append("Score now %d (best ever %s) in %d moves." % (s[0], self.stats["best_score"], s[1]))
        if self.tracker.rooms:
            lines.append("Map: %s" % self.pdf_path())
        if self.hints:
            lines.append("Your hints:")
            lines += ["  - " + h for h in self.hints]
        if self.notes:
            lines.append("The model's notes:")
            lines += ["  - " + n for n in self.notes]
        return "\n".join(lines)


def clip_start(text, n):
    """The first n characters of text, cut at a word."""
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "..."


def clip(text, n):
    text = text.strip()
    return text if len(text) <= n else "..." + text[-n:]


def parse_reply(text):
    """Pull THINK, NOTE, DONE and COMMAND out of the model's reply."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    if "</think>" in text:              # reasoning with only a closing tag (glm-5.3 does this)
        text = text.rsplit("</think>", 1)[1]
    # put each KEY: on its own line, even when a model runs them together on one line
    text = re.sub(r"\s*\b(THINK|NOTE|DONE|COMMAND)\s*:", r"\n\1:", text)
    think, notes, done, cmd = "", [], [], ""
    for line in text.splitlines():
        line = line.strip().strip("*").strip()
        m = re.match(r"(THINK|NOTE|DONE|COMMAND)\s*:\s*(.*)", line, re.I)
        if not m:
            continue
        key, val = m.group(1).upper(), m.group(2).strip().rstrip("|").strip()
        if key == "THINK":
            think = val
        elif key == "NOTE" and val and not val.startswith("("):
            notes.append(val)
        elif key == "DONE" and val and not val.startswith("("):
            done.append(val)
        elif key == "COMMAND":
            cmd = val
    if not cmd:                                     # fall back to the last short line
        for line in reversed(text.strip().splitlines()):
            if line.strip() and len(line.split()) <= 6 and ":" not in line:
                cmd = line.strip()
                break
    cmd = cmd.strip().strip("`\"'").lstrip(">").strip().rstrip(".!").lower()
    return think, notes, done, cmd


def main():
    ap = argparse.ArgumentParser(
        description="Let a local Ollama model play a Z-machine game on its own.",
        # the user guide from the top of this file, minus the notes on the code
        epilog="RUNNING IT" + __doc__.split("RUNNING IT", 1)[1].split("HOW THE CODE")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("story", help="story file (.z3, .z5, .z8, .zblorb ...)")
    ap.add_argument("--turns", type=int, default=300, help="turns to play (default 300)")
    ap.add_argument("--delay", type=float, default=0, help="seconds to pause after each turn")
    ap.add_argument("--fair", action="store_true",
                    help="don't show the model the game's object data (no peeking)")
    ap.add_argument("--fresh", action="store_true",
                    help="forget notes and map from earlier runs and start the game over "
                         "(your hints are kept)")
    ap.add_argument("--restart", action="store_true",
                    help="start the game over instead of carrying on where the last run "
                         "stopped; notes, map and hints are kept")
    ap.add_argument("--load", metavar="FILE",
                    help="start from a save file made with \"save\" in zplay.py (or a copy "
                         "of <story>.auto.sav) instead of where the last run stopped")
    ap.add_argument("--model", default=os.environ.get("ZPLAY_MODEL", "gemma4:latest"),
                    help="Ollama model (default: gemma4:latest)")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
                    help="Ollama server (default: http://localhost:11434)")
    ap.add_argument("--think", action="store_true", help="let the model 'think' first (slower)")
    ap.add_argument("--max-reply", type=int, default=300, metavar="N",
                    help="most tokens the model may write per reply (default 300; a normal "
                         "reply needs under 100). Stops models that reason at length in their "
                         "replies from getting slow and expensive. 0 means no limit.")
    ap.add_argument("--show-prompt", action="store_true", help="print each prompt sent to the model")
    ap.add_argument("--no-status", action="store_true", help="don't print the status line")
    ap.add_argument("--width", type=int, help="screen width (default: terminal width)")
    ap.add_argument("--seed", type=int, help="random seed for the game, for reproducible runs")
    args = ap.parse_args()

    if not args.host.startswith("http"):
        args.host = "http://" + args.host
    llm = Ollama(args.host, args.model, args.think, args.max_reply or None)
    problem = llm.check()
    if problem:
        sys.exit("Can't play: %s" % problem)

    stem = os.path.splitext(args.story)[0]
    title = os.path.splitext(os.path.basename(args.story))[0]
    size = shutil.get_terminal_size((80, 24))
    screen = AutoScreen(args.width or size.columns, size.lines, not args.no_status)
    log = open(stem + ".auto.log", "a", encoding="utf-8")
    log.write("\n===== %s  %s  model %s%s =====\n" % (
        time.strftime("%Y-%m-%d %H:%M"), title, args.model, "  (fair)" if args.fair else ""))

    player = zm = keys = None
    try:
        zm = AutoZMachine(zplay.load_story(args.story), screen, args.story, args.seed)
        key = list(zm.story_id())
        for suffix in (".auto.json", ".auto.map.json", ".auto.sav"):
            problem = unreadable(stem + suffix)
            if problem:     # otherwise it would look like another game's file and be skipped
                print(screen.style("[can't read %s: %s. Fix it (or move it away) and run "
                                   "again.]" % (stem + suffix, problem), "1;33"))
                return
        files = [game_file(stem, suffix, key) for suffix in (".auto.json", ".auto.map.json", ".auto.sav")]
        (state_path, _), (map_path, _), (pos_path, _) = files
        moved = [path for path, m in files if m]
        if moved:
            print(screen.style("[%s.auto.* files belong to another game, so this game's are "
                               "kept in %s]" % (stem, ", ".join(moved)), "2;36"))
        zm.tracker = Tracker(zm, map_path, fresh=args.fresh)
        keys = Keys()
        player = screen.player = Player(zm, llm, title, args, state_path, log, pos_path, keys)
        print(screen.style("[%s is playing %s for up to %d turns%s.]" % (
            args.model, title, args.turns, "" if args.fair else ", seeing the game's object data"),
            "2;36"))
        print(screen.style("[%s]" % ("Keys: p or space pauses, q stops (Ctrl-C works too)"
                                     if keys.fd is not None else "Ctrl-C to stop"), "2;36"))
        if args.fresh:
            print(screen.style("[--fresh: starting the game over with no notes or map; "
                               "kept your %d hints]" % len(player.hints), "2;36"))
        elif player.notes or player.hints:
            print(screen.style("[carrying on from earlier runs: %d hints, %d notes, %d rooms "
                               "mapped]" % (len(player.hints), len(player.notes),
                                            len(zm.tracker.rooms)), "2;36"))
        if args.load:
            problem, look = load_save(zm, args.load)
            if problem:
                print(screen.style("[can't load %s: %s]" % (args.load, problem), "1;33"))
                return
            player.forget_tried()
            print(screen.style("[starting from your save %s]" % args.load, "2;36"))
            if look:
                player.queued.append("look")
            else:
                print(screen.style("look", "1;36"))
        elif args.restart and not args.fresh:
            player.forget_tried()
            print(screen.style("[--restart: starting the game over]", "2;36"))
        elif not args.fresh and resume_position(zm, pos_path):
            print(screen.style("[carrying on from where the last run stopped "
                               "(--restart starts the game over)]", "2;36"))
            print(screen.style("look", "1;36"))
        print()
        zm.run()
        # The game quit by itself (some, like Enchanter, quit straight after the ending):
        # log its last words and say if it was a win.
        player.end_of_story(screen.since_input)
    except KeyboardInterrupt:
        screen.flush()
        print("\n[stopped]")
    except zplay.ZError as e:
        screen.flush()
        print("\n[Z-machine error: %s]" % e)
    finally:
        if keys:
            keys.close()
        if player:
            player.save()
            player.draw_map(force=True)
            text = player.summary()
            print(text)
            log.write(text + "\n")
        log.close()

if __name__ == "__main__":
    main()
