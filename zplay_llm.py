#!/usr/bin/env python3
"""
zplay_llm.py - play Infocom/Inform games in plain English, with a local LLM
(via Ollama) translating what you say into commands the game's parser understands.

    python3 zplay_llm.py zork1.z3                    # play, with gemma4 translating
    python3 zplay_llm.py zork1.z3 --show-llm         # also show the model's traffic
    python3 zplay_llm.py zork1.z3 --no-model         # no model: plain play plus the map
    python3 zplay_llm.py --help                      # all options and in-game commands

Uses the interpreter in zplay.py (keep the two files in the same folder).
Standard library only; needs Ollama running locally (https://ollama.com).
Type /help while playing for the in-game commands (the same text as HELP_TEXT below).

How it works
------------
  LLMZMachine   the zplay interpreter, with two hooks: before each command is read it
                lets the Tracker look at the game, and save/restore file names are
                passed to the game untranslated.
  LLMScreen     the zplay screen, but each line of input goes through read_line here:
                /commands are handled locally, "!" lines go to the game as typed, and
                everything else is translated. A request that turns into several
                commands is queued and fed to the game one at a time.
  Translator    builds the prompt (rules + the game's own dictionary + recent game text
                + map notes), asks the model, and checks every word of the reply against
                the dictionary, asking once more if a word is unknown. If the game then
                says it didn't understand, LLMScreen asks again (up to MAX_RETRIES).
  Tracker       the map. It reads the game's object tree (location, player, items) but
                only records what the player has been shown. Saved to <story>.map.json.
  Ollama        a small client for Ollama's /api/chat, using only urllib.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request

import zplay

MAX_COMMANDS = 12       # most commands accepted from one request (long enough for routes)
MAX_RETRIES = 2         # automatic re-asks after the game's parser rejects a command
HISTORY_TURNS = 8       # earlier exchanges kept in the model's context
OUTPUT_CHARS = 2500     # game text sent with each request (most recent part)

# Phrases games print when the *parser* (not the world) rejects a command.
PARSER_FAILURES = (
    "i don't know the word", "i don't understand", "isn't one i recognize",
    "there was no verb", "you used the word", "i beg your pardon", "i didn't understand",
    "not a verb i recogni", "i only understood you as far as", "there seems to be a noun missing",
    "i couldn't find a verb", "you can't use multiple", "that's not a verb",
)

# Shown by /help, and at the end of --help.
HELP_TEXT = """\
HOW TO PLAY
  Type what you want to do in your own words, for example:
      see what's inside that little mailbox
      grab the leaflet and read it
      go back to the kitchen and get the lamp
  The model turns it into game commands and shows them, like:  → open mailbox
  One- or two-word commands the game already knows (north, take lamp) go
  straight to the game. If the game doesn't understand a translated command,
  the model tries other words (marked ↻), up to twice.
  To save, restore or quit, just say so ("save my game"). File names typed at
  the save/restore prompt go to the game exactly as typed.

SENDING COMMANDS YOURSELF
  !<command>        send one command exactly as typed, e.g.  !look under rug
  /direct           turn translation off or on (off: works like plain zplay)

THE MAP  (built only from what you have seen, so it gives nothing away)
  /map              every room visited: its exits, blocked directions, items,
                    and what you are carrying
  /here             the same, for the room you are in
  /where <item>     where an item was last seen, and the route there
                    (any word the game knows works: /where lamp)
  /route <room>     the commands that get you to a room you have visited
  Exits are learned by walking them; "guess" marks an untried way back.
  When following a route, the rest is dropped if a move fails, and the
  model's own plans never move past the edge of the known map. The map is
  kept in <story>.map.json between sessions (start over with --fresh-map).
  If that file holds a different game's map (zork1.z3 and zork1.z5 in one
  folder), it is left alone and this game's map goes in a file with the
  release and serial added, e.g. zork1-r88-840726.map.json.

FOR TINKERING
  /show             show what is sent to the model and what it answers
  /debug            show the room's object tree and the map's state before
                    each prompt (this reveals hidden objects)
  /help             show this text
"""

SYSTEM_PROMPT = """\
You are the interface between a player and a classic Infocom-style text adventure ({title}). \
The player tells you in plain English what they want to do. You translate it into the short \
commands the game's parser understands.

Rules:
- Reply with game commands only, one per line. No explanations, numbering, quotes or punctuation.
- Each command is short: a verb and its objects, e.g. "take lamp", "open trap door", \
"put sword in case", "give garlic to bat", "ask butler about key", "turn on lamp".
- Movement uses directions: north, south, east, west, northeast, northwest, southeast, \
southwest, up, down, in, out.
- You only know the map through the MAP NOTES sent with each request. To reach a known place, \
send the commands of its route, in order. For anywhere else, use a direction only if the \
game's text or the player says which way leads there; otherwise ask which direction.
- Only use a route that the MAP NOTES list. If the place the player wants is listed under \
"NO known route", or isn't in the notes at all, do not guess: ask the player which way.
- When the player asks for an item, the MAP NOTES say where it was last seen. If it is HERE, \
just take it. If it is elsewhere, send that room's route and then take it.
- Use only words from the vocabulary below, and call things by the names the game's text uses.
- Prefer the simplest common verbs: look, examine, take, drop, open, close, read, push, pull, \
turn, move, enter, climb, put, give, ask, wait. Never use violent or destructive verbs \
(break, attack, kill, burn, cut) unless the player clearly asked for that.
- Do what the player asks, in order. Split a request with several steps into several \
commands (at most {max_cmds}). Never add steps the player didn't ask for, and never try to \
solve puzzles for the player.
- Game-control commands are fine to send: save, restore, restart, quit, score, wait, again, \
brief, verbose, script, unscript, undo.
- "what am I carrying?" -> inventory. "where am I?" or "look around" -> look. \
"tell me about the X" -> examine X.
- If the game has just asked a question (such as "What do you want to open?", \
"Do you wish to leave the game?", or asking for a name), reply with just the answer.
- If the player's message is already a valid command, repeat it unchanged.
- If you truly cannot tell what the player wants, reply with a single line starting with "?" \
followed by a short question for the player.

Examples:
Player: I wonder what's inside that mailbox -> open mailbox
Player: grab the leaflet and read it -> take leaflet / read leaflet
Player: head up the stairs -> up
Player: what do I have with me? -> inventory
Player: smash the window with the hammer -> break window with hammer
Player: try to pry the lid open -> open lid
Player: save my game please -> save
Player: hang on a moment -> wait
Player: fetch the lamp (notes: brass lantern in Living Room; route: west) -> west / take lamp
Player: pick up the coin (notes: gold coin is HERE) -> take coin

Vocabulary ({nwords} words; the parser only looks at the first {nletters} letters of a word, \
so longer words are shown cut short):
{vocab}
"""


# --------------------------------------------------------------------------- ollama

class OllamaError(Exception):
    pass


class Ollama:
    def __init__(self, host, model, think=False, max_reply=None):
        self.host = host.rstrip("/")
        self.model = model
        self.think = think
        self.max_reply = max_reply      # most tokens the model may write per reply (None: no limit)

    def _post(self, path, body, timeout):
        req = urllib.request.Request(self.host + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                msg = json.load(e).get("error", str(e))
            except Exception:
                msg = str(e)
            raise OllamaError(msg)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise OllamaError("can't reach Ollama at %s (%s)" % (self.host, e))

    def check(self):
        """Return an error message if Ollama or the model isn't available, else None."""
        try:
            req = urllib.request.Request(self.host + "/api/tags")
            with urllib.request.urlopen(req, timeout=5) as r:
                names = [m["name"] for m in json.load(r).get("models", [])]
        except Exception as e:
            return "can't reach Ollama at %s (%s). Is it running? (ollama serve)" % (self.host, e)
        want = self.model if ":" in self.model else self.model + ":latest"
        if want not in names and self.model not in names:
            return "model %r is not installed. Try: ollama pull %s" % (self.model, self.model)
        return None

    def chat(self, messages):
        body = {"model": self.model, "messages": messages, "stream": False,
                "think": self.think, "keep_alive": "30m",
                "options": {"temperature": 0.2, "num_ctx": 16384}}
        if self.max_reply:
            # Some models reason at length in their reply even with thinking off, and every
            # word costs time and money. Cut them off; a well-formed reply is far shorter.
            body["options"]["num_predict"] = self.max_reply
        try:
            data = self._post("/api/chat", body, timeout=180)
        except OllamaError as e:
            if "think" not in str(e).lower():
                raise
            del body["think"]                   # model without a thinking switch
            data = self._post("/api/chat", body, timeout=180)
        return data.get("message", {}).get("content", "")


# --------------------------------------------------------------------------- translator

class Translator:
    """Turns the player's English into game commands, checking words against the game's dictionary."""

    def __init__(self, llm, zm, title, show=False, log=None):
        self.llm = llm
        self.zm = zm
        self.title = title
        self.show = show
        self.log = log or (lambda s: None)
        self.history = []               # [(user message, assistant reply)]
        self.vocab_addr = None

    # vocabulary, read from the story's own dictionary
    def refresh_vocab(self):
        zm = self.zm
        if self.vocab_addr == zm.dict_addr:
            return
        self.vocab_addr = zm.dict_addr
        self.seps, self.lookup = zm.load_dict(zm.dict_addr)
        words = set()
        for e in self.lookup.values():
            w = zm.decode(e)[0].strip()
            if w and not w.startswith(("#", "$")) and any(ch.isalpha() for ch in w):
                words.add(w)
        self.vocab = sorted(words)
        self.nletters = 6 if zm.version <= 3 else 9
        self.system = SYSTEM_PROMPT.format(
            title=self.title, max_cmds=MAX_COMMANDS, nwords=len(self.vocab),
            nletters=self.nletters, vocab=" ".join(self.vocab))

    def words(self, command):
        """Split a command the way the game's tokeniser does (quoted text is left out)."""
        command = re.sub(r'"[^"]*"', " ", command)
        sep = "".join(re.escape(chr(c)) for c in self.seps)
        return [w for w in re.split(r"[\s%s]+" % sep, command) if w]

    def unknown_words(self, command):
        bad = []
        for w in self.words(command):
            if w.isdigit():
                continue
            key = self.zm.encode_word([self.zm.to_zscii(ch) for ch in w.lower()])
            if key not in self.lookup:
                bad.append(w)
        return bad

    def is_known(self, text):
        self.refresh_vocab()
        return bool(self.words(text)) and not self.unknown_words(text)

    @staticmethod
    def parse_reply(text):
        """Pull commands (and an optional '?' question for the player) out of the model's reply."""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
        commands, question = [], None
        for line in text.replace(" / ", "\n").splitlines():
            line = line.strip().strip("`").strip()
            if not line:
                continue
            if line.startswith("?"):
                question = line.lstrip("? ").strip()
                continue
            line = re.sub(r"^(\d+[.)]|[-*•>]|command:|player:)\s*", "", line, flags=re.I)
            if "->" in line:                    # model echoed an example's format
                line = line.split("->")[-1]
            line = line.strip().strip("\"'").rstrip(".!").strip().lower()
            if line and len(line) <= 80:
                commands.append(line)
        return commands[:MAX_COMMANDS], question

    def ask(self, messages):
        if self.show:
            self.log("[to model] " + messages[-1]["content"].replace("\n", "\n           ") + "\n")
        reply = self.llm.chat([{"role": "system", "content": self.system}] + messages)
        if self.show:
            self.log("[model] " + reply.strip().replace("\n", " / ") + "\n")
        return reply

    def translate(self, game_text, request, feedback=None, notes=""):
        """Return (commands, question). feedback explains why an earlier attempt failed."""
        self.refresh_vocab()
        game_text = game_text.strip()[-OUTPUT_CHARS:]
        user = "GAME OUTPUT:\n%s\n\nPLAYER: %s" % (game_text, request)
        if feedback:
            user = "GAME OUTPUT:\n%s\n\n%s\nThe player's request was: %s" % (game_text, feedback, request)
        msgs = []
        for u, a in self.history[-HISTORY_TURNS:]:
            msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
        msgs.append({"role": "user", "content": (notes + "\n\n" + user) if notes else user})

        commands, question = self.parse_reply(self.ask(msgs))
        bad = sorted({w for c in commands for w in self.unknown_words(c)})
        if bad:                                 # one chance to fix words the game won't know
            reply1 = "\n".join(commands)
            msgs += [{"role": "assistant", "content": reply1},
                     {"role": "user", "content":
                      "The game does not know these words: %s. Rewrite the commands using only "
                      "vocabulary words. If a word is a name or an answer the game asked for, "
                      "keep it." % ", ".join(bad)}]
            fixed, q2 = self.parse_reply(self.ask(msgs))
            if fixed:
                commands, question = fixed, q2 or question
        reply = "\n".join(commands) or ("? " + question if question else "")
        self.history.append((user, reply))
        del self.history[:-HISTORY_TURNS]
        return commands, question


# --------------------------------------------------------------------------- map tracker

DIRECTIONS = {
    "n": "north", "s": "south", "e": "east", "w": "west", "ne": "northeast", "nw": "northwest",
    "se": "southeast", "sw": "southwest", "u": "up", "d": "down",
}
# Spaceship and seagoing games (Starcross, Planetfall) use these instead of the compass.
SHIP_DIRS = ("fore", "aft", "port", "starboard")
# A move refused for a reason that can change: the exit may well be there, so it isn't
# marked as leading nowhere.
TEMPORARY = re.compile(r"stand up|get up|get out of|first\b|is closed|are closed|is locked|"
                       r"too dark|can't see|seat ?belt|strapped|won't let you|in your way|blocks")
for _d in list(DIRECTIONS.values()) + ["in", "out"] + list(SHIP_DIRS):
    DIRECTIONS[_d] = _d
# Commands that move you without walking anywhere; never recorded as exits.
NOT_MOVES = {"restore", "restart", "undo", "load", "quit", "save", "script", "unscript"}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east",
            "northeast": "southwest", "southwest": "northeast", "northwest": "southeast",
            "southeast": "northwest", "up": "down", "down": "up", "in": "out", "out": "in",
            "fore": "aft", "aft": "fore", "port": "starboard", "starboard": "port"}
# What Infocom and Inform games usually call the player object.
PLAYER_NAMES = {"yourself", "you", "cretin", "me", "myself", "self", "player"}
COMPASS = ("northeast", "northwest", "southeast", "southwest", "north", "south", "east", "west")


def game_file(stem, suffix, key):
    """The file to keep this game's data in: <stem><suffix>, unless that file belongs to a
    different game (say zork1.z3 and zork1.z5 in one folder). Then the name gets this game's
    release and serial number added, e.g. zork1-r88-840726.map.json, so the other game's
    file is never overwritten. Returns (path, True if it had to use the longer name)."""
    path = stem + suffix
    try:
        with open(path) as fh:
            if json.load(fh).get("story") == key:
                return path, False
    except FileNotFoundError:
        return path, False
    except (OSError, ValueError, AttributeError):
        pass                        # unreadable or not ours: leave it alone
    serial = re.sub(r"\W", "", str(key[1])) or str(key[2])     # some serials are blank
    return "%s-r%s-%s%s" % (stem, key[0], serial, suffix), True


class Tracker:
    """Builds a map from play: rooms visited, the commands that lead between them, and
    where items were last seen. It reads the game's object tree, but only records what the
    player has actually been shown, so it gives nothing away. Kept in <story>.map.json."""

    def __init__(self, zm, path, fresh=False):
        self.zm = zm
        self.path = path
        self.rooms = {}             # id -> {"name", "exits": {cmd: id}, "guess": {dir: id},
                                    #        "blocked": [], "mentioned": []}
        self.items = {}             # id -> {"name", "room", "where", "carried", "missing"}
        self.player = None          # object number of the player, once worked out
        self.cands = None           # player candidates: objects that moved with us so far
        self.last_tree = None       # objects in the previous room, to see what moved with us
        self.here = None
        self.prev = None
        self.last_cmd = None
        self.expected = None
        self.surprise = False       # last move didn't go where the map said it would
        if not fresh:
            self.load()

    # ---- persistence
    def story_key(self):
        return list(self.zm.story_id())

    def load(self):
        try:
            with open(self.path) as fh:
                d = json.load(fh)
            if d.get("story") != self.story_key():
                return
            self.rooms, self.items, self.player = d["rooms"], d["items"], d.get("player")
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def save(self):
        d = {"story": self.story_key(), "rooms": self.rooms, "items": self.items,
             "player": self.player, "here": self.here}
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w") as fh:
                json.dump(d, fh, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass

    # ---- reading the game
    def children(self, o):
        out, c, guard = [], self.zm.orel(o, 2), 0
        while c and guard < 300:
            out.append(c)
            c = self.zm.orel(c, 1)
            guard += 1
        return out

    def location(self):
        """(room id, room name, object number or None)."""
        zm = self.zm
        try:
            g0 = zm.rw(zm.globals)
            name = zm.obj_name(g0) if 0 < g0 < 2000 else ""
        except (IndexError, zplay.ZError):
            g0, name = 0, ""
        if zm.version <= 3:
            return (str(g0), name, g0) if name else (None, None, None)
        # v4+: no fixed location variable. Trust global 0 if the status line shows its name,
        # otherwise go by the room name on the status line.
        status = "".join(zm.screen.grid[0]).strip() if zm.screen.grid else ""
        if name and name.lower() in status.lower():
            return str(g0), name, g0
        room = re.split(r"\s{2,}", status)[0].strip() if status else ""
        return ("s:" + room, room, None) if room else (None, None, None)

    def synonyms(self, o):
        """Words the game accepts for object o: any property holding only dictionary entries."""
        zm = self.zm
        entries = set(zm.load_dict(zm.dict_addr)[1].values())
        words = []
        try:
            for _, a, ln in zm.props(o):
                if ln % 2 or not ln:
                    continue
                vals = [zm.rw(a + i) for i in range(0, ln, 2)]
                if all(v in entries for v in vals):
                    words += [zm.decode(v)[0] for v in vals]
        except (IndexError, zplay.ZError):
            pass
        return sorted(set(words))

    def match_items(self, text):
        """Items whose name or game synonyms match the words in text."""
        q = [w for w in re.findall(r"[a-z0-9'-]+", text.lower()) if w not in ("the", "a", "an")]
        hits = []
        for k, it in self.items.items():
            names = it["name"].lower().split() + it.get("words", [])
            if q and all(any(n.startswith(w) or w.startswith(n) and len(n) >= 3 for n in names)
                         for w in q):
                hits.append(it)
        return hits

    @staticmethod
    def norm(cmd):
        """Canonical form of a command: 'go n' -> 'north'."""
        c = " ".join(cmd.lower().split())
        m = re.fullmatch(r"(?:go|walk|run|head|move|travel|climb)\s+(?:to\s+(?:the\s+)?)?(\w+)", c)
        if m and m.group(1) in DIRECTIONS:
            c = m.group(1)
        return DIRECTIONS.get(c, c), c in DIRECTIONS

    # ---- per turn
    def command(self, cmd):
        """Called with each line the game reads."""
        cmd = (cmd or "").strip()
        if cmd.lower() in ("again", "g") and self.last_cmd:
            cmd = self.last_cmd
        self.last_cmd = cmd or None
        self.prev = self.here
        key = self.norm(cmd)[0] if cmd else None
        room = self.rooms.get(self.here or "")
        self.expected = None
        if room and key:
            self.expected = room["exits"].get(key) or room.get("guess", {}).get(key)

    def observe(self, output):
        """Called before each line is read, with the game's output since the last one."""
        loc, name, obj = self.location()
        if loc is None:
            return
        changed = False
        if loc not in self.rooms:
            self.rooms[loc] = {"name": name, "exits": {}, "blocked": [], "mentioned": []}
            changed = True
        room = self.rooms[loc]
        room["name"] = name
        room.setdefault("guess", {})
        moved = self.prev is not None and loc != self.prev
        self.surprise = False
        if self.prev is not None and self.last_cmd:
            key, is_dir = self.norm(self.last_cmd)
            first = key.split()[0] if key else ""
            if moved:
                died = re.search(r"you (have )?died|you are dead|\*\*\*", output.lower())
                if first not in NOT_MOVES and not died and self.prev in self.rooms:
                    p = self.rooms[self.prev]
                    if p["exits"].get(key) != loc:
                        p["exits"][key] = loc
                        changed = True
                    if key in p["blocked"]:
                        p["blocked"].remove(key)
                    p.get("guess", {}).pop(key, None)
                    back = OPPOSITE.get(key)        # guess the way back, until it's tried
                    if back and back not in room["exits"] and back not in room["blocked"]:
                        if room["guess"].get(back) != self.prev:
                            room["guess"][back] = self.prev
                            changed = True
                self.surprise = self.expected is not None and self.expected != loc
            else:
                if (is_dir and key not in room["exits"] and key not in room["blocked"]
                        and not TEMPORARY.search(output.lower())):
                    room["blocked"].append(key)
                    room["guess"].pop(key, None)
                    changed = True
                self.surprise = is_dir or self.expected is not None     # the move went nowhere
        if moved or self.prev is None or (self.last_cmd or "").lower() in ("look", "l"):
            changed |= self.note_mentioned(room, output)
        if obj:
            changed |= self.update_player(obj, moved)
            changed |= self.update_items(loc, obj, output)
        changed |= loc != self.here
        self.here = loc
        if changed:
            self.save()

    def note_mentioned(self, room, text):
        t = text.lower()
        found = [d for d in COMPASS + SHIP_DIRS if re.search(r"\b%s\b" % d, t)]
        # up, down, in and out are everyday words: count them only in a sentence about
        # exits ("stairs lead up"), or when quoted as an exit's name ('"Out."')
        exit_talk = [s for s in re.split(r"[.!?]\s", t)
                     if re.search(r"\bexits?\b|\blead|\bstair|\bladder|\bpassage", s)]
        for d in ("up", "down", "in", "out"):
            if re.search(r"\"%s\b" % d, t) or (
                    d in ("up", "down") and any(re.search(r"\b%s\b" % d, s) for s in exit_talk)):
                found.append(d)
        found = [d for d in found if not any(d != o and d in o and o in found for o in found)]
        if sorted(found) != sorted(room["mentioned"]) and found:
            room["mentioned"] = found
            return True
        return False

    def subtree(self, o, depth=4):
        out, level = set(), self.children(o)
        while level and depth:
            out.update(level)
            level = [c for x in level for c in self.children(x) if c not in out]
            depth -= 1
        return out

    def update_player(self, room_obj, moved):
        """The player is the object that comes along when we change rooms (with whatever
        it carries); of the objects that moved with us, it's the one at the top."""
        if self.player:
            return False
        tree, last = self.subtree(room_obj), self.last_tree
        self.last_tree = tree
        named = [o for o in tree if self.zm.obj_name(o).lower() in PLAYER_NAMES]
        if len(named) == 1:
            self.cands = set(named)
        elif not moved or last is None:
            return False
        else:
            common = tree & last
            top = {o for o in common if self.zm.orel(o, 0) not in common}
            if not top:
                return False
            self.cands = top if self.cands is None else (self.cands & top) or top
        if len(self.cands) == 1:
            self.player = next(iter(self.cands))
            for k in [k for k in self.items if int(k) == self.player]:
                del self.items[k]
            return True
        return False

    def update_items(self, loc, room_obj, output):
        zm, low, changed = self.zm, output.lower(), False
        seen = set()
        todo, depth = [(c, room_obj) for c in self.children(room_obj)], 0
        while todo and depth < 4:
            nxt = []
            for o, parent in todo:
                if o != self.player:
                    seen.add(o)
                    changed |= self.record_item(o, parent, loc, room_obj, low)
                nxt += [(c, o) for c in self.children(o)]
            todo, depth = nxt, depth + 1
        for k, it in self.items.items():           # known items no longer where we left them
            if int(k) in seen:
                continue
            if it["carried"] or (it["room"] == loc and not it["missing"]):
                if it["carried"]:
                    it["room"] = loc
                it.update(carried=False, missing=True, where="gone (last seen here)")
                changed = True
        return changed

    def record_item(self, o, parent, loc, room_obj, low):
        key = str(o)
        known = key in self.items
        name = self.zm.obj_name(o)
        if not name:
            return False
        if not known:
            last = name.lower().split()[-1]         # "kitchen table" is often just "the table"
            pats = [name.lower()] + ([last] if len(last) >= 3 else [])
            if not any(re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(x), low) for x in pats):
                return False
        carried, chain, p = False, [], parent
        while p and p != room_obj and len(chain) < 6:
            if p == self.player:
                carried = True
                break
            chain.append(self.zm.obj_name(p))
            p = self.zm.orel(p, 0)
        where = "carried" if carried else ("in/on the " + chain[0] if chain else "here")
        words = self.items[key].get("words") if known else None
        new = {"name": name, "room": None if carried else loc, "where": where,
               "carried": carried, "missing": False,
               "words": words if words is not None else self.synonyms(o)}
        if self.items.get(key) != new:
            self.items[key] = new
            return True
        return False

    # ---- questions
    def plan_length(self, cmds):
        """How many of cmds to keep: a plan may take one step into the unknown, but no
        further moves after that, since nobody knows where it would lead."""
        pos, off_map = self.here, False
        for i, c in enumerate(cmds):
            key, is_dir = self.norm(c)
            if not is_dir:
                continue
            if off_map:
                return i
            d = self.rooms.get(pos or "", {})
            pos = d.get("exits", {}).get(key) or d.get("guess", {}).get(key)
            off_map = pos is None
        return len(cmds)

    def routes(self, start=None):
        """Shortest known command sequence from start to every reachable room."""
        start = start or self.here
        paths = {start: []}
        queue = [start]
        while queue:
            r = queue.pop(0)
            d = self.rooms.get(r, {})
            for cmd, dest in list(d.get("exits", {}).items()) + list(d.get("guess", {}).items()):
                if dest not in paths and dest in self.rooms:
                    paths[dest] = paths[r] + [cmd]
                    queue.append(dest)
        return paths

    def find_room(self, text):
        text = text.lower().strip()
        hits = [r for r, d in self.rooms.items() if text in d["name"].lower()]
        if not hits:
            return None
        paths = self.routes()
        return min(hits, key=lambda r: (len(paths[r]) if r in paths else 999,
                                        len(self.rooms[r]["name"])))

    def rname(self, r):
        return self.rooms.get(r, {}).get("name", "?")

    def item_line(self, it):
        if it["carried"]:
            return "%s (carried)" % it["name"]
        where = "" if it["where"] == "here" else ", " + it["where"]
        return "%s (%s%s)" % (it["name"], self.rname(it["room"]), where)

    def report(self, room_filter=None):
        if not self.rooms:
            return ["No map yet."]
        paths = self.routes()
        order = sorted(self.rooms, key=lambda r: (len(paths[r]) if r in paths else 999,
                                                  self.rooms[r]["name"]))
        if room_filter:
            order = [r for r in order if r == room_filter]
        lines = []
        if not room_filter:
            lines.append("Map: %d rooms known, you are in %s." % (len(self.rooms), self.rname(self.here)))
            carried = [it["name"] for it in self.items.values() if it["carried"]]
            lines.append("Carrying: " + (", ".join(carried) or "nothing"))
        for r in order:
            d = self.rooms[r]
            tag = "   ← you are here" if r == self.here else (
                "   (%d step%s away)" % (len(paths[r]), "" if len(paths[r]) == 1 else "s")
                if r in paths else "   (no known route from here)")
            lines.append("")
            lines.append(d["name"] + tag)
            for cmd, dest in sorted(d["exits"].items()):
                lines.append("    %-12s → %s" % (cmd, self.rname(dest)))
            for cmd, dest in sorted(d.get("guess", {}).items()):
                if cmd not in d["exits"]:
                    lines.append("    %-12s → %s  (guess: the way back, not tried)" % (cmd, self.rname(dest)))
            if d["blocked"]:
                lines.append("    blocked:     " + ", ".join(d["blocked"]))
            untried = [m for m in d["mentioned"] if m not in d["exits"] and m not in d["blocked"]]
            if untried:
                lines.append("    mentioned, not tried: " + ", ".join(untried))
            here = [it for it in self.items.values() if it["room"] == r and not it["carried"]]
            for it in here:
                extra = "" if it["where"] == "here" else " (%s)" % it["where"]
                lines.append("    item: %s%s" % (it["name"], extra))
        return lines

    def context(self):
        """A compact summary for the model."""
        if not self.here or self.here not in self.rooms:
            return ""
        d = self.rooms[self.here]
        out = ["MAP NOTES (only what the player has seen so far):",
               "You are in: %s." % d["name"]]
        if d["exits"]:
            out.append("Known exits here: " + "; ".join(
                "%s -> %s" % (c, self.rname(r)) for c, r in d["exits"].items()))
        guesses = {c: r for c, r in d.get("guess", {}).items() if c not in d["exits"]}
        if guesses:
            out.append("Probably (untried way back): " + "; ".join(
                "%s -> %s" % (c, self.rname(r)) for c, r in guesses.items()))
        if d["blocked"]:
            out.append("Tried here but led nowhere: " + ", ".join(d["blocked"]))
        untried = [m for m in d["mentioned"] if m not in d["exits"] and m not in d["blocked"]]
        if untried:
            out.append("Directions the description mentions but not yet tried: " + ", ".join(untried))
        paths = self.routes()
        far = sorted((r for r in paths if r != self.here and len(paths[r]) <= MAX_COMMANDS),
                     key=lambda r: len(paths[r]))[:25]
        if far:
            out.append("Routes to known places (send these commands in order): " + " | ".join(
                "%s: %s" % (self.rname(r), ", ".join(paths[r])) for r in far))
        cut_off = sorted({self.rname(r) for r in self.rooms if r not in paths})
        if cut_off:
            out.append("Visited but NO known route from here (ask the player the way): "
                       + ", ".join(cut_off))
        carried = [it["name"] for it in self.items.values() if it["carried"]]
        out.append("Player is carrying: " + (", ".join(carried) or "nothing"))
        here = [it for it in self.items.values()
                if it["room"] == self.here and not it["carried"] and not it["missing"]]
        if here:
            out.append("Items HERE in this room (just take them, no moving needed): " + "; ".join(
                it["name"] + ("" if it["where"] == "here" else " (" + it["where"] + ")")
                for it in here))
        away = [it for it in self.items.values()
                if it["room"] != self.here and not it["carried"]][:25]
        if away:
            parts = []
            for it in away:
                path = paths.get(it["room"])
                how = ("route: " + ", ".join(path)) if path else "no known route"
                parts.append("%s (%s; %s)" % (it["name"], self.rname(it["room"]), how))
            out.append("Items elsewhere: " + "; ".join(parts))
        return "\n".join(out)


# --------------------------------------------------------------------------- screen

class LLMScreen(zplay.Screen):
    """A zplay Screen whose line input goes through the translator."""

    def key_ready(self, timeout):
        return False                    # timed key reads: let the game's timer run

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.translator: "Translator | None" = None
        self.tracker: "Tracker | None" = None
        self.zm: "LLMZMachine | None" = None
        self.last_line = ""             # the last line handed to the game
        self.direct = False
        self.raw_next = False           # next read is a file name, not a command
        self.queue = []                 # translated commands waiting to be sent
        self.request = None             # the English request the queue came from
        self.retries = 0
        self.since_input = ""           # game text since the last line was read
        self.since_llm = ""             # game text since the model was last asked

    @property
    def tr(self) -> "Translator":
        assert self.translator is not None
        return self.translator

    def style(self, s, code):
        return "\x1b[%sm%s\x1b[0m" % (code, s) if self.ansi else s

    def note(self, s):
        """Print an interface message (not game text) on its own line. Any unprinted
        prompt is kept, so it still appears after the message."""
        if self.col > 0:
            sys.stdout.write("\n")
            self.col = 0
        sys.stdout.write(self.style(s, "2;36") + "\n")
        sys.stdout.flush()

    def write(self, s):
        self.since_input += s
        self.since_llm += s
        super().write(s)

    def send(self, cmd, echo=True, retry=False):
        """Return cmd as the line the game reads, echoing it after the game's prompt."""
        if echo:
            self.flush()
            mark = self.style("  ↻ retrying in other words", "2;36") if retry else ""
            sys.stdout.write(self.style(cmd, "36") + mark + "\n")
            self.col = 0
        self.since_llm += cmd + "\n"
        return cmd

    def read_line(self):
        if self.raw_next:
            self.raw_next = False
            return super().read_line()
        self.last_line = self.next_line()
        return self.last_line

    def next_line(self):
        game_out, self.since_input = self.since_input, ""

        # The game's parser rejected a translated command: ask the model again.
        if self.request and any(p in game_out.lower() for p in PARSER_FAILURES):
            if self.retries < MAX_RETRIES:
                self.retries += 1
                self.queue = []
                cmds, _ = self.translate(self.request, feedback=(
                    "The game did not understand the last command. Try different, simpler "
                    "words from the vocabulary for what is still left to do. Do not do "
                    "anything more drastic than the player asked."))
                if cmds:
                    return self.send(cmds[0], retry=True)
            self.request, self.queue = None, []

        # A route went somewhere unexpected (or a move was blocked): stop following it.
        if self.queue and self.tracker and self.tracker.surprise:
            self.note("  [stopped: that move didn't go as planned, so %d remaining command%s "
                      "dropped]" % (len(self.queue), "" if len(self.queue) == 1 else "s"))
            self.queue, self.request = [], None

        if self.queue:
            return self.send(self.queue.pop(0))

        while True:
            self.request, self.retries = None, 0
            text = super().read_line().strip()
            if re.fullmatch(r"/[a-z]+(\s.*)?", text, re.I):
                self.command(text)
                sys.stdout.write(">")
                continue
            if text.startswith("!"):
                return self.send(text[1:].strip(), echo=False)
            if self.direct or not text or self.translator is None:
                return self.send(text, echo=False)
            if len(text.split()) <= 2 and self.tr.is_known(text):
                self.request = text             # already a command; ask the model only if it fails
                return self.send(text, echo=False)
            self.request = text
            cmds, question = self.translate(text)
            if cmds:
                self.note("  → " + " · ".join(cmds))
                return self.send(cmds[0], echo=False)
            if not question:
                self.note("  [no command came back for that; try rewording it, "
                          "or type !command to send it to the game as is]")
            sys.stdout.write(">")

    def translate(self, request, feedback=None):
        """Ask the model; queue the commands after the first. Returns (commands, question)."""
        if self.ansi and not self.tr.show:
            sys.stdout.write(self.style("  (thinking…)", "2"))
            sys.stdout.flush()
        t0 = time.time()
        try:
            notes = self.tracker.context() if self.tracker else ""
            cmds, question = self.tr.translate(self.since_llm, request, feedback, notes)
        except OllamaError as e:
            cmds, question = [], None
            self.clear_thinking()
            self.note("[model error: %s — sending your words to the game as typed]" % e)
            cmds = [request] if not feedback else []
        else:
            self.clear_thinking()
        self.since_llm = ""
        said_dirs = re.search(r"(?<![\w'])(%s|up|down|[nsewud]|ne|nw|se|sw)(?![\w'])"
                              % "|".join(COMPASS), request.lower())
        if self.tracker and cmds and not said_dirs:   # the player's own directions always go
            keep = self.tracker.plan_length(cmds)
            if keep < len(cmds):
                self.note("  [not sending %s: those moves go past the edge of the known map]"
                          % " · ".join(cmds[keep:]))
                cmds = cmds[:keep]
        if self.tr.show:
            self.note("[%.1fs]" % (time.time() - t0))
        if question and not cmds:
            self.note("  ? " + question)
        self.queue = cmds[1:]
        return cmds, question

    def clear_thinking(self):
        if self.ansi and not self.tr.show:
            sys.stdout.write("\r\x1b[K")
            sys.stdout.flush()

    def command(self, text):
        name, _, arg = text[1:].partition(" ")
        name, arg, tk = name.lower(), arg.strip(), self.tracker
        if name in ("map", "here", "where", "route") and not (tk and tk.rooms):
            self.note("[no map yet: this game's location couldn't be read, or nothing seen yet]")
        elif name == "map":
            self.note("\n".join(tk.report()))
        elif name == "here":
            self.note("\n".join(tk.report(room_filter=tk.here)))
        elif name == "where":
            want = arg.lower()
            hits = tk.match_items(want)
            if not want:
                self.note("[usage: /where <item>]")
            elif not hits:
                self.note("[haven't seen anything called %r yet]" % arg)
            for it in hits:
                if it["carried"]:
                    self.note("  %s: you are carrying it" % it["name"])
                    continue
                path = tk.routes().get(it["room"])
                where = "" if it["where"] == "here" else ", " + it["where"]
                how = ("you are there" if path == [] else "route: " + ", ".join(path) if path
                       else "no known route from here")
                self.note("  %s: %s%s (%s)" % (it["name"], tk.rname(it["room"]), where, how))
        elif name == "route":
            dest = tk.find_room(arg) if arg else None
            if not dest:
                self.note("[usage: /route <room name>, for a room you have visited]" if not arg
                          else "[no visited room matches %r]" % arg)
            else:
                path = tk.routes().get(dest)
                if path is None:
                    self.note("  no known route from here to %s" % tk.rname(dest))
                elif not path:
                    self.note("  you are in %s" % tk.rname(dest))
                else:
                    self.note("  to %s: %s" % (tk.rname(dest), ", ".join(path)))
        elif name == "debug" and self.zm:
            self.zm.debug = not self.zm.debug
            self.note("[debug view %s]" % ("on: shows hidden objects, so it gives things away"
                                           if self.zm.debug else "off"))
            if self.zm.debug:
                self.zm.show_debug()
        elif name == "direct" and self.translator is None:
            self.note("[no model connected, so commands always go straight to the game]")
        elif name == "show" and self.translator is None:
            self.note("[no model connected]")
        elif name == "direct":
            self.direct = not self.direct
            self.note("[direct mode %s]" % ("on: your words go straight to the game" if self.direct
                                            else "off: the model translates what you type"))
        elif name == "show":
            self.tr.show = not self.tr.show
            self.note("[showing model traffic: %s]" % ("on" if self.tr.show else "off"))
        elif name == "help":
            self.flush()
            sys.stdout.write("\n" + HELP_TEXT + "\n")
        else:
            self.note("[unknown command /%s; type /help for the list]" % name)


class LLMZMachine(zplay.ZMachine):
    tracker = None

    def debug_info(self):
        lines = super().debug_info()
        tk = self.tracker
        if tk:
            lines.append("map: room %s  player object %s  candidates %s" % (
                tk.here, tk.player, sorted(tk.cands) if tk.cands and not tk.player else "-"))
            lines.append("map: last command %r  expected %s  surprise %s" % (
                tk.last_cmd, tk.rname(tk.expected) if tk.expected else "-", tk.surprise))
        return lines

    def op_read(self, *args):
        if self.tracker:
            self.tracker.observe(self.screen.since_input)
        super().op_read(*args)
        if self.tracker:
            self.tracker.command(self.screen.last_line)

    def ask_filename(self, verb):
        self.screen.raw_next = True     # file names go to the game untranslated
        return super().ask_filename(verb)


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="Play Z-machine games in plain English, translated by a local Ollama model.",
        epilog="In-game commands:\n\n" + HELP_TEXT,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("story", help="story file (.z3, .z5, .z8, .zblorb ...)")
    ap.add_argument("--model", default=os.environ.get("ZPLAY_MODEL", "gemma4:latest"),
                    help="Ollama model (default: gemma4:latest)")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
                    help="Ollama server (default: http://localhost:11434)")
    ap.add_argument("--think", action="store_true",
                    help="let the model 'think' before answering (slower)")
    ap.add_argument("--show-llm", action="store_true", help="show the model's requests and replies")
    ap.add_argument("--debug", action="store_true",
                    help="show the location's object tree and map state each turn (also: /debug)")
    ap.add_argument("--fresh-map", action="store_true",
                    help="start a new map instead of loading <story>.map.json")
    ap.add_argument("--no-model", action="store_true",
                    help="don't use a model at all (plain zplay, plus the map commands)")
    ap.add_argument("--script", help="text file of things to type, one per line")
    ap.add_argument("--no-status", action="store_true", help="don't print the status line")
    ap.add_argument("--width", type=int, help="screen width (default: terminal width)")
    ap.add_argument("--seed", type=int, help="random seed, for reproducible runs")
    args = ap.parse_args()

    if not args.host.startswith("http"):
        args.host = "http://" + args.host
    if sys.stdin.isatty():
        try:
            import readline  # noqa: F401  (line editing and history for input())
        except ImportError:
            pass

    size = shutil.get_terminal_size((80, 24))
    script = None
    if args.script:
        with open(args.script) as fh:
            script = [l.rstrip("\n") for l in fh]
    screen = LLMScreen(args.width or size.columns, size.lines, not args.no_status, script)

    llm = Ollama(args.host, args.model, args.think)
    problem = "--no-model was given" if args.no_model else llm.check()
    if args.no_model:
        print(screen.style("[No model: type commands as usual. Type /help for the map and "
                           "other commands.]", "2;36"))
        print()
    elif problem:
        print("[Warning: %s]\n[Playing without translation; type commands as usual.]\n" % problem)
    else:
        print(screen.style("[%s will translate what you type. Type /help to see how this "
                           "works and the commands for the map.]" % args.model, "2;36"))
        print()

    zm = None
    try:
        zm = LLMZMachine(zplay.load_story(args.story), screen, args.story, args.seed, args.debug)
        screen.zm = zm
        if not problem:
            title = os.path.splitext(os.path.basename(args.story))[0]
            screen.translator = Translator(llm, zm, title, args.show_llm, log=screen.note)
        map_path, moved = game_file(os.path.splitext(args.story)[0], ".map.json",
                                    list(zm.story_id()))
        if moved:
            print(screen.style("[%s.map.json is another game's map, so this game's map is "
                               "kept in %s]" % (os.path.splitext(args.story)[0], map_path),
                               "2;36"))
        zm.tracker = screen.tracker = Tracker(zm, map_path, fresh=args.fresh_map)
        zm.run()
    except zplay.ZError as e:
        screen.flush()
        print("\n[Z-machine error: %s]" % e)
        sys.exit(1)
    except KeyboardInterrupt:
        screen.flush()
        print()
    except OSError as e:
        screen.flush()
        print("\n[Error: %s]" % e)
        sys.exit(1)
    finally:
        if zm and zm.transcript:
            zm.transcript.close()


if __name__ == "__main__":
    main()
